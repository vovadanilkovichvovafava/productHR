"""Текст резюме из приложенного файла — БЕЗ обращения к ИИ.

Зачем: резюме, загруженное в карточку существующего кандидата, для дедупа было
невидимо. На загрузке файла (routes/entities/files.py) вызывался только рендер
страниц в картинки и извлечение фото — ни текста, ни повторного детекта. В
локальной базе из 16 кандидатов с PDF-резюме 15 не участвовали в текстовом
сравнении вообще (владелец 17.09.2026).

Здесь именно ДЕШЁВЫЙ путь: pdfplumber/python-docx через общий document_parser,
без Claude. Извлечённый текст ложится в ``extra_data.resume_text`` и с этого
момента участвует и в детекторе копипаста (resume_text_twin), и во вкладке
«Текст» окна сравнения. Контакты отсюда НЕ разбираются — это отдельная, платная
задача (resume_parser + Claude).

Скан-PDF (картинка без текстового слоя) даёт пустой результат: OCR к PDF не
подключён. Такой файл помечаем ``resume_text_source.empty = true``, чтобы было
видно, почему кандидат «молчит», и чтобы не дёргать парсер повторно.
"""

import logging
import re
from typing import Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.database import Entity

logger = logging.getLogger("hr-analyzer.resume_text")

# Форматы, из которых текст достаётся локально. Картинки сюда НЕ входят: для них
# document_parser зовёт Claude Vision (OCR), а это уже платный путь.
TEXT_EXTRACTABLE_EXTENSIONS = {".pdf", ".doc", ".docx", ".odt", ".rtf", ".txt", ".html", ".htm"}

# Короче этого — не текст резюме, а подпись под сканом или шапка. В extra_data не
# кладём: иначе «текст» из трёх слов начнёт участвовать в сравнении.
MIN_USEFUL_CHARS = 200


def is_text_extractable(file_name: str) -> bool:
    ext = ("." + file_name.rsplit(".", 1)[-1].lower()) if "." in file_name else ""
    return ext in TEXT_EXTRACTABLE_EXTENSIONS


# Служебные врезки парсера: «--- Page 2 ---», «[Table 3]». В карточке сравнения
# они выглядят мусором, а в сравнении текстов дают общие шинглы у ЛЮБЫХ двух
# многостраничных резюме — то есть немного завышают сходство.
_SERVICE_MARKERS = re.compile(r"^(?:-{2,}\s*Page\s*\d+\s*-{2,}|\[Table\s*\d+\])\s*$", re.M)


async def extract_resume_text(file_bytes: bytes, file_name: str) -> str:
    """Текст из файла резюме. Пустая строка, если текстового слоя нет."""
    from .documents import document_parser

    try:
        result = await document_parser.parse(file_bytes, file_name)
    except Exception as e:  # noqa: BLE001 — извлечение best-effort
        logger.warning(f"RESUME_TEXT: parse failed for {file_name!r}: {e}")
        return ""
    # Неразрывные пробелы и мягкие переносы — обычное дело в выгрузках резюме;
    # в сравнении и в карточке они только мешают.
    text = (result.content or "").replace("\xa0", " ").replace("\u00ad", "")
    text = _SERVICE_MARKERS.sub("", text)
    return "\n".join(line.rstrip() for line in text.splitlines() if line.strip()).strip()


async def store_resume_text(
    db: AsyncSession,
    entity: Entity,
    file_bytes: bytes,
    file_name: str,
    file_id: Optional[int] = None,
) -> Tuple[int, bool]:
    """Достать текст из файла и положить в extra_data кандидата.

    Возвращает (сколько символов, положили ли в resume_text). Не коммитит —
    вызывающий решает, когда фиксировать. Самое свежее резюме перетирает прошлое:
    поле показывает текст последнего файла, как и вкладка «Резюме» в карточке.
    """
    if not is_text_extractable(file_name):
        return 0, False

    text = await extract_resume_text(file_bytes, file_name)
    extra = dict(entity.extra_data) if isinstance(entity.extra_data, dict) else {}
    source = {"file_id": file_id, "file_name": file_name, "chars": len(text)}

    if len(text) < MIN_USEFUL_CHARS:
        # Скан или пустой файл: текста нет. Сам resume_text не трогаем (там может
        # лежать текст прошлого, нормального резюме).
        source["empty"] = True
        extra["resume_text_source"] = source
        entity.extra_data = extra
        logger.info(
            f"RESUME_TEXT: no text layer in {file_name!r} for entity {entity.id} "
            f"({len(text)} chars) — скан или защищённый файл"
        )
        return len(text), False

    extra["resume_text"] = text
    extra["resume_text_source"] = source
    set_resume_contacts(extra, text, file_id)
    entity.extra_data = extra
    logger.info(f"RESUME_TEXT: extracted {len(text)} chars from {file_name!r} for entity {entity.id}")
    return len(text), True


def set_resume_contacts(extra: dict, text: str, file_id: Optional[int] = None) -> bool:
    """Положить в extra контакты из шапки текста резюме. True — если они
    изменились (тогда стоит пересчитать дубли)."""
    from .resume_contacts import extract_header_contacts

    found = extract_header_contacts(text or "")
    prev = extra.get("resume_contacts") if isinstance(extra.get("resume_contacts"), dict) else {}
    same = all(sorted(prev.get(k) or []) == sorted(found[k]) for k in found)
    if not any(found.values()):
        if prev:
            extra.pop("resume_contacts", None)
            return True
        return False
    if same:
        return False
    extra["resume_contacts"] = {**found, "file_id": file_id}
    return True



# --- Распознавание сканов (OCR) — Tesseract, локально, без ИИ (22.09.2026) ------
#
# Скан или фото резюме текстового слоя не имеет — раньше такие файлы в сравнение
# не попадали вовсе. Теперь страницы превращаются в картинки (PyMuPDF — он уже
# рисует превью) и читаются программой tesseract (rus+eng) на нашем сервере.
# Claude Vision сюда НЕ подключаем: дорого (сторожит tests/test_dedup_no_ai.py).

import asyncio
import shutil
import subprocess

OCR_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
OCR_MAX_PAGES = 4          # резюме длиннее почти не бывает; больше — дольше и дороже
OCR_DPI = 250              # меньше — хуже читаются мелкие цифры телефона
OCR_PAGE_TIMEOUT = 60      # секунд на страницу


def _ext(file_name: str) -> str:
    return ("." + file_name.rsplit(".", 1)[-1].lower()) if "." in file_name else ""


def needs_ocr(file_name: str, extracted_chars: int) -> bool:
    """Нужно ли распознавать файл: картинка, или PDF без текстового слоя."""
    ext = _ext(file_name)
    if ext in OCR_IMAGE_EXTENSIONS:
        return True
    return ext == ".pdf" and extracted_chars < MIN_USEFUL_CHARS


def ocr_available() -> bool:
    return shutil.which("tesseract") is not None


def _page_images(file_bytes: bytes, file_name: str) -> list:
    """PNG-картинки первых страниц (PDF) или сам файл-картинка, приведённый к PNG."""
    import pymupdf

    ext = _ext(file_name)
    out = []
    if ext == ".pdf":
        doc = pymupdf.open(stream=file_bytes, filetype="pdf")
        for page in list(doc)[:OCR_MAX_PAGES]:
            out.append(page.get_pixmap(dpi=OCR_DPI).tobytes("png"))
    else:
        doc = pymupdf.open(stream=file_bytes, filetype=ext.lstrip("."))
        for page in list(doc)[:OCR_MAX_PAGES]:
            out.append(page.get_pixmap(dpi=OCR_DPI).tobytes("png"))
    return out


def _ocr_sync(file_bytes: bytes, file_name: str) -> str:
    if not ocr_available():
        logger.info("RESUME_OCR: tesseract не установлен — распознавание пропущено")
        return ""
    parts = []
    for i, png in enumerate(_page_images(file_bytes, file_name)):
        try:
            res = subprocess.run(
                ["tesseract", "stdin", "stdout", "-l", "rus+eng", "--psm", "3"],
                input=png, capture_output=True, timeout=OCR_PAGE_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            logger.warning(f"RESUME_OCR: page {i + 1} of {file_name!r} timed out")
            continue
        if res.returncode != 0:
            logger.warning(f"RESUME_OCR: tesseract failed on {file_name!r}: {res.stderr[:200]!r}")
            continue
        parts.append(res.stdout.decode("utf-8", errors="ignore"))
    text = "\n".join(parts).replace("\xa0", " ").replace("­", "")
    return "\n".join(line.rstrip() for line in text.splitlines() if line.strip()).strip()


async def ocr_resume(file_bytes: bytes, file_name: str) -> str:
    """Распознать скан. В отдельном потоке: страница — 1–3 с CPU, а сервер один
    (22.09.2026 тяжёлая работа в цикле событий уже вешала прод)."""
    try:
        return await asyncio.to_thread(_ocr_sync, file_bytes, file_name)
    except Exception as e:  # noqa: BLE001 — best-effort, загрузку не ломаем
        logger.warning(f"RESUME_OCR: failed for {file_name!r}: {e}")
        return ""


async def ocr_and_store(entity_id: int, file_id: int) -> bool:
    """Фоновая задача после загрузки: распознать скан, сохранить текст и контакты
    из шапки, пересчитать дубли. Своя сессия БД. True — текст сохранён."""
    from ..database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        return await ocr_and_store_in(db, entity_id, file_id)


async def ocr_and_store_in(db: AsyncSession, entity_id: int, file_id: int) -> bool:
    """Тело ocr_and_store на переданной сессии. Коммитит."""
    from ..models.database import EntityFile
    from .resume_text_twin import detect_resume_text_twin
    from .similarity import identity_fingerprint, recheck_duplicates_after_edit

    ef = await db.get(EntityFile, file_id)
    entity = await db.get(Entity, entity_id)
    if ef is None or entity is None or not ef.file_data:
        return False
    text = await ocr_resume(bytes(ef.file_data), ef.file_name or "")
    if len(text) < MIN_USEFUL_CHARS:
        logger.info(f"RESUME_OCR: {ef.file_name!r} (entity {entity_id}) — текста не распознано")
        return False
    before = identity_fingerprint(entity)
    extra = dict(entity.extra_data) if isinstance(entity.extra_data, dict) else {}
    extra["resume_text"] = text
    extra["resume_text_source"] = {
        "file_id": file_id, "file_name": ef.file_name, "chars": len(text), "ocr": True,
    }
    set_resume_contacts(extra, text, file_id)
    entity.extra_data = extra
    await db.flush()
    await detect_resume_text_twin(db, entity)
    if identity_fingerprint(entity) != before:
        await recheck_duplicates_after_edit(db, entity)
    await db.commit()
    logger.info(
        f"RESUME_OCR: {len(text)} chars from {ef.file_name!r} for entity {entity_id}, "
        f"contacts={extra.get('resume_contacts')}"
    )
    return True
