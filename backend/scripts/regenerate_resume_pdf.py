"""
Regenerate the AI candidate-profile PDF (+ JPEG pages) for existing entities.

WHY: old PDFs were rendered before the markdown-table fix, so they contain raw
`| ... |` / `|---|` table garbage. The source markdown is NOT stored, so the
only way to fix an old PDF is to regenerate it via AI from the candidate's data
(entity fields + extra_data). New PDFs are already clean after the resume_generator
fix; this script backfills the old ones.

SAFETY:
- Generates everything in memory FIRST; only deletes old AI files and inserts new
  ones if generation succeeded. A failure leaves the existing PDF untouched.
- Only touches AI-generated resume files (description "AI-сгенерированный профиль
  кандидата" / "AI-профиль …"). Never deletes user-uploaded resumes or photos.
- The candidate photo is reused from the already-stored photo file (no new photo
  file is created, so re-running does not duplicate photos).

USAGE (run from the backend/ directory, with DATABASE_URL + ANTHROPIC_API_KEY set):
    python -m scripts.regenerate_resume_pdf --entity-id 123          # one (verify first!)
    python -m scripts.regenerate_resume_pdf --entity-id 123 --dry-run
    python -m scripts.regenerate_resume_pdf --all                    # backfill everything
"""
import argparse
import asyncio
import os
import sys

# Make `from api...` work regardless of how the script is launched.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, or_, func  # noqa: E402

from api.database import AsyncSessionLocal  # noqa: E402
from api.models.database import Entity, EntityFile, EntityFileType  # noqa: E402
from api.services.resume_generator import (  # noqa: E402
    generate_ai_summary, generate_candidate_pdf, pdf_to_jpeg,
)

# Descriptions used by _generate_resume_files when it created the files.
AI_PDF_DESC = "AI-сгенерированный профиль кандидата"
AI_JPG_DESC_PREFIX = "AI-профиль"


def _candidate_data_from_entity(entity: Entity) -> dict:
    """Rebuild the candidate_data dict that generate_ai_summary expects."""
    ed = entity.extra_data or {}
    tg = entity.telegram_usernames or []
    return {
        "full_name": entity.name,
        "position": entity.position or ed.get("position"),
        "email": entity.email,
        "phone": entity.phone,
        "telegram": tg[0] if tg else None,
        "city": ed.get("city"),
        "age": ed.get("age"),
        "birthday": ed.get("birth_date"),
        "gender": ed.get("gender"),
        "salary": ed.get("salary"),
        "total_experience": ed.get("total_experience"),
        "experience_summary": ed.get("experience_summary"),
        "experience_descriptions": ed.get("experience_descriptions"),
        "skills": ed.get("skills"),
        "languages": ed.get("languages"),
        "education": ed.get("education"),
        "certifications": ed.get("certifications"),
        "summary": ed.get("summary"),
        "photo_url": ed.get("photo_url"),
    }


async def _existing_photo_bytes(db, entity_id: int):
    """Reuse the already-stored candidate photo (so we don't create a duplicate)."""
    res = await db.execute(
        select(EntityFile)
        .where(
            EntityFile.entity_id == entity_id,
            EntityFile.file_type == EntityFileType.other,
            EntityFile.description.like("Фото%"),
            EntityFile.file_data.isnot(None),
        )
        .order_by(EntityFile.id.asc())
        .limit(1)
    )
    pf = res.scalar_one_or_none()
    return (pf.file_data, pf.mime_type) if pf else (None, None)


async def _old_ai_resume_files(db, entity_id: int):
    res = await db.execute(
        select(EntityFile).where(
            EntityFile.entity_id == entity_id,
            EntityFile.file_type == EntityFileType.resume,
            or_(
                EntityFile.description == AI_PDF_DESC,
                EntityFile.description.like(f"{AI_JPG_DESC_PREFIX}%"),
            ),
        )
    )
    return list(res.scalars().all())


async def regenerate_one(db, entity: Entity, dry_run: bool) -> bool:
    name = entity.name or "Кандидат"
    print(f"\n[entity {entity.id}] {name}")

    candidate_data = _candidate_data_from_entity(entity)

    # 1) Generate everything in memory FIRST.
    markdown = await generate_ai_summary(candidate_data)
    if not markdown or not markdown.strip():
        print("  ! пустой markdown — пропускаю (старый PDF не тронут)")
        return False
    photo_bytes, photo_mime = await _existing_photo_bytes(db, entity.id)
    pdf_bytes = generate_candidate_pdf(markdown, name, photo_bytes=photo_bytes)
    jpeg_pages = pdf_to_jpeg(pdf_bytes, dpi=200)
    print(
        f"  markdown {len(markdown)} симв. | PDF {len(pdf_bytes)} байт | "
        f"{len(jpeg_pages)} JPEG | фото: {'есть' if photo_bytes else 'нет'}"
    )

    old_files = await _old_ai_resume_files(db, entity.id)
    print(f"  старых AI-файлов под замену: {len(old_files)}")

    if dry_run:
        print("  DRY-RUN — ничего не записано")
        return True

    # 2) Only now mutate: delete old AI files, insert fresh ones.
    for f in old_files:
        await db.delete(f)

    safe = name.replace(" ", "_")
    db.add(EntityFile(
        entity_id=entity.id, org_id=entity.org_id,
        file_type=EntityFileType.resume,
        file_name=f"Профиль_{safe}.pdf", file_path="",
        file_size=len(pdf_bytes), mime_type="application/pdf",
        description=AI_PDF_DESC, uploaded_by=entity.created_by,
        file_data=pdf_bytes,
    ))
    for i, jpg in enumerate(jpeg_pages):
        db.add(EntityFile(
            entity_id=entity.id, org_id=entity.org_id,
            file_type=EntityFileType.resume,
            file_name=f"Профиль_{safe}_стр{i+1}.jpg", file_path="",
            file_size=len(jpg), mime_type="image/jpeg",
            description=f"{AI_JPG_DESC_PREFIX} (стр. {i+1})",
            uploaded_by=entity.created_by, file_data=jpg,
        ))
    await db.commit()
    print("  ✓ перегенерирован и сохранён")
    return True


async def main():
    ap = argparse.ArgumentParser(description="Regenerate AI resume PDFs")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--entity-id", type=int, help="ID одного кандидата")
    g.add_argument("--all", action="store_true", help="все кандидаты с AI-PDF")
    ap.add_argument("--dry-run", action="store_true", help="не записывать, только показать")
    args = ap.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("WARNING: ANTHROPIC_API_KEY не задан — markdown будет fallback-без-AI")

    async with AsyncSessionLocal() as db:
        if args.entity_id:
            entity = (await db.execute(
                select(Entity).where(Entity.id == args.entity_id)
            )).scalar_one_or_none()
            if not entity:
                print(f"Entity {args.entity_id} не найден")
                return
            await regenerate_one(db, entity, args.dry_run)
        else:
            # Все entity, у которых есть AI-сгенерированный PDF.
            ids = (await db.execute(
                select(EntityFile.entity_id).where(
                    EntityFile.file_type == EntityFileType.resume,
                    EntityFile.description == AI_PDF_DESC,
                ).distinct()
            )).scalars().all()
            print(f"Найдено {len(ids)} кандидатов с AI-PDF")
            ok = 0
            for eid in ids:
                entity = (await db.execute(
                    select(Entity).where(Entity.id == eid)
                )).scalar_one_or_none()
                if entity and await regenerate_one(db, entity, args.dry_run):
                    ok += 1
            print(f"\nГотово: {ok}/{len(ids)}")


if __name__ == "__main__":
    asyncio.run(main())
