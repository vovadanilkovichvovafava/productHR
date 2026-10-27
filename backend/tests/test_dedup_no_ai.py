"""Сравнение дублей не должно ходить в платные ИИ-API (решение владельца 22.09.2026:
«сравнение вообще не должно идти через api claude — слишком затратно»).

Ядро, текст резюме и сравнение текстов работают локально: ключи + Жаккар,
pdfplumber/python-docx. Тест ловит, если кто-то подключит сюда Claude/OpenAI.
"""
import ast
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from api.services.resume_text_extract import extract_resume_text, is_text_extractable

DEDUP_MODULES = [
    "api/services/duplicate_matcher.py",
    "api/services/similarity.py",
    "api/services/resume_text_extract.py",
    "api/services/resume_text_twin.py",
]
# Модули, через которые идут платные вызовы (Claude, Claude Vision, OpenAI-эмбеддинги).
PAID_AI = {
    "anthropic", "openai", "ai", "entity_ai", "comparison_ai", "resume_parser",
    "embedding_service", "smart_search", "ai_scoring",
}


def _imported_modules(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                yield a.name.split(".")[-1], node.lineno
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module.split(".")[-1], node.lineno


@pytest.mark.parametrize("rel", DEDUP_MODULES)
def test_dedup_modules_do_not_import_paid_ai(rel):
    path = Path(__file__).resolve().parents[1] / rel
    bad = [(m, line) for m, line in _imported_modules(path) if m in PAID_AI]
    # similarity.py исторически умеет искать «похожих» по эмбеддингам через
    # similarity_search (только запрос к pgvector, без вызова API) — это не дубли.
    assert not bad, f"{rel} тянет платный ИИ: {bad}"


def test_images_are_not_sent_to_vision_ocr():
    # Для картинок document_parser зовёт Claude Vision — в сравнение они не идут.
    for name in ("resume.jpg", "scan.PNG", "photo.heic", "x.webp"):
        assert not is_text_extractable(name)


@pytest.mark.asyncio
async def test_pdf_text_extraction_never_calls_claude():
    from api.services import documents

    boom = AsyncMock(side_effect=AssertionError("Claude вызван при извлечении текста"))
    with patch.object(documents, "get_async_anthropic_client", side_effect=AssertionError("Claude")), \
         patch.object(documents.document_parser, "_ocr_with_vision", boom):
        # Пустой/битый PDF: парсер обязан вернуть пустоту, а не уйти в OCR.
        text = await extract_resume_text(b"%PDF-1.4\n%%EOF", "scan.pdf")
    assert text == ""
    boom.assert_not_called()
