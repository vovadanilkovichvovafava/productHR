"""Распознавание сканов резюме — Tesseract на сервере, без ИИ (22.09.2026).

Сама программа tesseract в тестах подменена: проверяем, КОГДА распознаём, что
делаем с текстом и что сайт не ломается, если программы нет.
"""
import subprocess
from unittest.mock import patch

import pymupdf
import pytest

from api.models.database import Entity, EntityFile, EntityFileType, EntityStatus, EntityType
from api.services import resume_text_extract as rte

OCR_TEXT = """Иванов Иван Петрович
Мужчина, 30 лет
+7 (999) 123-45-67
ivan.scan@mail.ru
Желаемая должность и зарплата
Менеджер по продажам. Опыт работы в продажах B2B, ведение ключевых клиентов,
переговоры, CRM, отчётность, планирование, обучение новых сотрудников отдела.
Опыт работы — 5 лет"""


def _scan_pdf(pages=1) -> bytes:
    doc = pymupdf.open()
    for _ in range(pages):
        page = doc.new_page()
        page.draw_rect(pymupdf.Rect(50, 50, 200, 100), color=(0, 0, 0))  # картинка без текста
    return doc.tobytes()


def _fake_tesseract(*args, **kwargs):
    return subprocess.CompletedProcess(args[0], 0, stdout=OCR_TEXT.encode(), stderr=b"")


def test_when_ocr_is_needed():
    assert rte.needs_ocr("scan.pdf", 0)
    assert rte.needs_ocr("scan.pdf", 150)            # подпись под сканом — не текст
    assert not rte.needs_ocr("resume.pdf", 2000)     # нормальный PDF — читаем как есть
    assert rte.needs_ocr("photo.JPG", 0)
    assert not rte.needs_ocr("resume.docx", 0)


def test_no_tesseract_means_no_text_and_no_crash():
    with patch.object(rte.shutil, "which", return_value=None):
        assert rte._ocr_sync(_scan_pdf(), "scan.pdf") == ""


def test_ocr_reads_at_most_four_pages_with_russian():
    calls = []

    def fake(cmd, **kw):
        calls.append(cmd)
        return _fake_tesseract(cmd, **kw)

    with patch.object(rte.shutil, "which", return_value="/usr/bin/tesseract"), \
         patch.object(rte.subprocess, "run", side_effect=fake):
        text = rte._ocr_sync(_scan_pdf(pages=6), "scan.pdf")
    assert len(calls) == rte.OCR_MAX_PAGES
    assert all("rus+eng" in c for c in calls)
    assert "Иванов Иван Петрович" in text


def test_ocr_page_timeout_is_skipped():
    with patch.object(rte.shutil, "which", return_value="/usr/bin/tesseract"), \
         patch.object(rte.subprocess, "run", side_effect=subprocess.TimeoutExpired("tesseract", 60)):
        assert rte._ocr_sync(_scan_pdf(), "scan.pdf") == ""


@pytest.mark.asyncio
async def test_ocr_text_and_header_contacts_are_stored(db_session, organization):
    e = Entity(org_id=organization.id, type=EntityType.candidate, status=EntityStatus.new,
               name="Иванов Иван", extra_data={})
    db_session.add(e)
    await db_session.flush()
    f = EntityFile(entity_id=e.id, org_id=organization.id, file_type=EntityFileType.resume,
                   file_name="scan.pdf", file_data=_scan_pdf())
    db_session.add(f)
    await db_session.commit()

    with patch.object(rte.shutil, "which", return_value="/usr/bin/tesseract"), \
         patch.object(rte.subprocess, "run", side_effect=_fake_tesseract):
        assert await rte.ocr_and_store_in(db_session, e.id, f.id) is True
    await db_session.refresh(e)
    assert e.extra_data["resume_text_source"]["ocr"] is True
    assert "Менеджер по продажам" in e.extra_data["resume_text"]
    assert e.extra_data["resume_contacts"]["phones"] == ["+79991234567"]
    assert e.extra_data["resume_contacts"]["emails"] == ["ivan.scan@mail.ru"]
