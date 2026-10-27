"""Текст резюме из приложенного PDF — без ИИ (владелец 17.09.2026).

Резюме, загруженное в карточку существующего кандидата, раньше для дедупа не
существовало: на загрузке файла текст не извлекался, в extra_data ничего не
появлялось, детектор копипаста такого кандидата не видел.
"""
import pytest

from api.models.database import Entity, EntityType, EntityStatus
from api.services.resume_text_extract import (
    MIN_USEFUL_CHARS,
    extract_resume_text,
    is_text_extractable,
    store_resume_text,
)
from api.services.resume_text_twin import (
    detect_resume_text_twin, resume_text_blob, text_shingles,
)

RESUME_BODY = (
    "Опыт работы: ведущий специалист по подбору персонала в крупной продуктовой "
    "компании, закрывал вакансии в разработке, аналитике и маркетинге. "
    "Выстраивал воронку найма с нуля, вёл отчётность по конверсии этапов, "
    "проводил скрининги и финальные интервью вместе с нанимающими менеджерами. "
    "Навыки: массовый подбор, executive search, оценка компетенций, ATS."
)


def _pdf_with_text(lines) -> bytes:
    """Минимальный валидный PDF с текстовым слоем (base-14 Helvetica, латиница)."""
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    y = 60
    for line in lines:
        page.insert_text((50, y), line, fontsize=11)
        y += 16
    return doc.tobytes()


def _scanned_pdf(lines) -> bytes:
    """PDF-скан: та же страница, но растром — текстового слоя нет."""
    import pymupdf

    src = pymupdf.open(stream=_pdf_with_text(lines), filetype="pdf")
    pix = src[0].get_pixmap(dpi=120)
    out = pymupdf.open()
    page = out.new_page(width=pix.width, height=pix.height)
    page.insert_image(page.rect, stream=pix.tobytes("png"))
    return out.tobytes()


def _lines(prefix: str = "") -> list:
    # Латиница: base-14 шрифты не кодируют кириллицу, а нам нужен именно
    # текстовый слой, который прочитает pdfplumber.
    body = (
        "Experience: lead recruiter in a product company, closed roles in "
        "engineering, analytics and marketing. Built the hiring funnel from "
        "scratch, tracked stage conversion, ran screenings and final interviews "
        "together with hiring managers. Skills: volume hiring, executive search, "
        "competency assessment, ATS administration and reporting."
    )
    return [prefix] + [body[i:i + 90] for i in range(0, len(body), 90)]


async def _mk(db, org_id, name, **kw):
    e = Entity(org_id=org_id, type=EntityType.candidate, name=name, status=EntityStatus.new, **kw)
    db.add(e)
    await db.flush()
    return e


class TestExtractable:
    def test_documents_are_extractable(self):
        assert is_text_extractable("resume.pdf")
        assert is_text_extractable("Резюме.DOCX")

    def test_images_are_not(self):
        # Картинки ушли бы в Claude Vision (платный OCR) — сюда их не берём.
        assert not is_text_extractable("scan.jpg")
        assert not is_text_extractable("photo.png")


@pytest.mark.asyncio
async def test_text_from_pdf_lands_in_extra_data(db_session, organization):
    cand = await _mk(db_session, organization.id, "Смирнов Олег")
    await db_session.commit()

    chars, stored = await store_resume_text(
        db_session, cand, _pdf_with_text(_lines("CV Oleg Smirnov")), "resume.pdf", file_id=1,
    )
    assert stored is True and chars >= MIN_USEFUL_CHARS
    assert "hiring funnel" in cand.extra_data["resume_text"]
    assert cand.extra_data["resume_text_source"]["file_name"] == "resume.pdf"


@pytest.mark.asyncio
async def test_scanned_pdf_is_marked_not_silently_empty(db_session, organization):
    """Скан без текстового слоя: OCR к PDF не подключён. Текст не выдумываем, но
    помечаем источник, чтобы было видно, ПОЧЕМУ кандидат молчит в сравнении."""
    cand = await _mk(db_session, organization.id, "Сканов Скан")
    await db_session.commit()

    chars, stored = await store_resume_text(
        db_session, cand, _scanned_pdf(_lines("CV Scan")), "scan.pdf", file_id=2,
    )
    assert stored is False
    assert chars < MIN_USEFUL_CHARS
    assert cand.extra_data["resume_text_source"]["empty"] is True
    assert "resume_text" not in cand.extra_data


@pytest.mark.asyncio
async def test_extracted_text_makes_candidate_visible_to_twin_detector(db_session, organization):
    """Двое с ОДНИМ И ТЕМ ЖЕ приложенным резюме и без общих контактов: до правки
    они не были похожи ничем, теперь ловятся детектором копипаста."""
    pdf = _pdf_with_text(_lines("CV"))
    first = await _mk(db_session, organization.id, "Первый Кандидат", email="one@x.com")
    second = await _mk(db_session, organization.id, "Второй Кандидат", email="two@x.com")
    await db_session.commit()

    # До извлечения текста сравнивать нечего.
    assert len(text_shingles(resume_text_blob(second.extra_data))) < 5
    assert await detect_resume_text_twin(db_session, second) == (None, 0.0)

    await store_resume_text(db_session, first, pdf, "resume.pdf", file_id=3)
    await store_resume_text(db_session, second, pdf, "resume.pdf", file_id=4)
    await db_session.commit()

    twin_id, sim = await detect_resume_text_twin(db_session, second)
    assert twin_id == first.id
    assert sim > 0.9


@pytest.mark.asyncio
async def test_blob_includes_attached_file_text(db_session, organization):
    """resume_text из приложенного файла обязан попадать в сравниваемый текст —
    иначе извлечение ничего не даёт."""
    blob = resume_text_blob({"resume_text": RESUME_BODY})
    assert "воронку найма" in blob


@pytest.mark.asyncio
async def test_page_markers_are_stripped(db_session, organization):
    """«--- Page 1 ---» — врезка парсера, а не текст резюме: в карточке это мусор,
    а в сравнении — общие шинглы у любых двух многостраничных резюме."""
    text = await extract_resume_text(_pdf_with_text(_lines("CV Marker Test")), "resume.pdf")
    assert text and "Page 1" not in text


@pytest.mark.asyncio
async def test_extract_does_not_crash_on_garbage(db_session, organization):
    assert await extract_resume_text(b"not a pdf at all", "broken.pdf") == ""
