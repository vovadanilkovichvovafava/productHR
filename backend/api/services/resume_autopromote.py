"""Авто-промоут присланного PDF во вкладку «Резюме», если у кандидата его ещё нет.

Кандидат может прислать своё резюме обычным файлом (через анкету или ручную
загрузку), и оно уходит в «Файлы», не попадая во вкладку «Резюме» (file_type=other).
Эта ФОНОВАЯ задача срабатывает ТОЛЬКО по факту загрузки PDF (не сканирует ничего
периодически). Логика, как просил пользователь:

  1. если у кандидата УЖЕ есть резюме (любой file_type=resume) → ничего не делаем;
  2. иначе классифицируем присланный PDF через Claude (resume_parser): если это
     НЕ резюме (счёт, договор и т.п.) → не трогаем, остаётся обычным файлом;
  3. если это резюме → помечаем файл file_type=resume и генерим страницы-превью
     (тот же путь, что при ручной загрузке с пометкой «резюме») — показываем
     ЕГО ЖЕ PDF как есть, без перегенерации.

Один раз: после промоута у кандидата появляется резюме, и гард (п.1) больше не
пропустит задачу.
"""
import logging
import tempfile
from pathlib import Path

from sqlalchemy import select

from ..database import AsyncSessionLocal
from ..models.database import EntityFile, EntityFileType
from .resume_parser import resume_parser_service

logger = logging.getLogger("hr-analyzer.resume-autopromote")


def _looks_like_resume(parsed) -> bool:
    """Эвристика «это резюме»: есть имя И хотя бы один содержательный блок
    (опыт / навыки / образование). На не-резюме resume-AI вернёт пустые поля."""
    has_name = bool((getattr(parsed, "name", None) or "").strip())
    has_exp = bool(getattr(parsed, "experience", None)) or bool(getattr(parsed, "experience_years", None))
    has_skills = bool(getattr(parsed, "skills", None))
    has_edu = bool(getattr(parsed, "education", None))
    return has_name and (has_exp or has_skills or has_edu)


async def promote_pdf_to_resume_if_needed(entity_id: int, org_id: int) -> None:
    """Фоновая задача: см. модульный docstring. Безопасна к повторам и сбоям."""
    try:
        async with AsyncSessionLocal() as db:
            # (1) Гард: у кандидата уже есть резюме → выходим.
            existing = await db.execute(
                select(EntityFile.id)
                .where(
                    EntityFile.entity_id == entity_id,
                    EntityFile.file_type == EntityFileType.resume,
                )
                .limit(1)
            )
            if existing.scalar() is not None:
                return

            # Кандидаты на промоут: PDF-файлы file_type=other, новейшие первыми.
            # Берём максимум 3 свежих — обычно резюме это только что загруженный
            # файл; так бережём вызовы Claude (это редкий edge-case).
            rows = (
                await db.execute(
                    select(EntityFile)
                    .where(
                        EntityFile.entity_id == entity_id,
                        EntityFile.file_type == EntityFileType.other,
                        EntityFile.mime_type == "application/pdf",
                    )
                    .order_by(EntityFile.id.desc())
                    .limit(3)
                )
            ).scalars().all()

            for ef in rows:
                data = ef.file_data
                if not data and ef.file_path:
                    try:
                        data = Path(ef.file_path).read_bytes()
                    except Exception:
                        data = None
                if not data:
                    continue

                # (2) Классификация через Claude. Это не резюме → пропускаем файл.
                try:
                    parsed = await resume_parser_service.parse_resume(
                        data, ef.file_name or "resume.pdf"
                    )
                except Exception as e:
                    logger.warning(f"parse_resume failed for file {ef.id}: {e}")
                    continue
                if not _looks_like_resume(parsed):
                    continue

                # (3) Промоут: файл становится резюме + страницы-превью во вкладку.
                ef.file_type = EntityFileType.resume
                await db.commit()

                tmp_path = None
                try:
                    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                        tmp.write(data)
                        tmp_path = Path(tmp.name)
                    # Ленивый импорт — избегаем цикла routes↔services.
                    from ..routes.entities.files import convert_pdf_to_images

                    await convert_pdf_to_images(
                        pdf_path=tmp_path,
                        entity_id=entity_id,
                        org_id=org_id,
                        uploaded_by=ef.uploaded_by,
                        db=db,
                    )
                except Exception as e:
                    logger.error(f"preview gen failed for promoted resume {ef.id}: {e}")
                finally:
                    if tmp_path and tmp_path.exists():
                        try:
                            tmp_path.unlink()
                        except Exception:
                            pass

                logger.info(
                    f"Promoted file {ef.id} → resume for entity {entity_id} (no prior resume)"
                )
                return  # промоутим только первый подходящий PDF
    except Exception:
        logger.exception(f"promote_pdf_to_resume_if_needed failed for entity {entity_id}")
