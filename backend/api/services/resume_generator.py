"""
AI-powered candidate resume/profile PDF generator.
Takes parsed candidate data from hh.ru (or other sources),
sends through Claude for structuring, generates a styled PDF,
converts to JPEG, and attaches both to the entity.
"""
import io
import os
import logging
import re
from datetime import datetime
from typing import Optional

import anthropic
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, Image,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.fonts import addMapping

logger = logging.getLogger("hr-analyzer.resume-generator")

# Font configuration
FONTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'fonts')
_fonts_registered = False
_use_cyrillic = False


def _register_fonts():
    global _fonts_registered, _use_cyrillic
    if _fonts_registered:
        return _use_cyrillic
    _fonts_registered = True
    font_path = os.path.join(FONTS_DIR, 'DejaVuSans.ttf')
    font_bold_path = os.path.join(FONTS_DIR, 'DejaVuSans-Bold.ttf')
    if os.path.exists(font_path) and os.path.exists(font_bold_path):
        try:
            pdfmetrics.registerFont(TTFont('DejaVuSans', font_path))
            pdfmetrics.registerFont(TTFont('DejaVuSans-Bold', font_bold_path))
            addMapping('DejaVuSans', 0, 0, 'DejaVuSans')
            addMapping('DejaVuSans', 1, 0, 'DejaVuSans-Bold')
            addMapping('DejaVuSans', 0, 1, 'DejaVuSans')
            addMapping('DejaVuSans', 1, 1, 'DejaVuSans-Bold')
            _use_cyrillic = True
        except Exception as e:
            logger.warning(f"Font registration failed: {e}")
    return _use_cyrillic


def _escape(text: str) -> str:
    """Escape HTML for ReportLab."""
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


async def generate_ai_summary(candidate_data: dict) -> str:
    """Send candidate data through Claude to get a structured summary."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("No ANTHROPIC_API_KEY, generating summary without AI")
        return _fallback_summary(candidate_data)

    # Build data description
    parts = []
    if candidate_data.get("full_name"):
        parts.append(f"ФИО: {candidate_data['full_name']}")
    if candidate_data.get("position"):
        parts.append(f"Желаемая должность: {candidate_data['position']}")
    if candidate_data.get("age"):
        parts.append(f"Возраст: {candidate_data['age']}")
    if candidate_data.get("birthday"):
        parts.append(f"Дата рождения: {candidate_data['birthday']}")
    if candidate_data.get("gender"):
        parts.append(f"Пол: {candidate_data['gender']}")
    if candidate_data.get("city"):
        parts.append(f"Город: {candidate_data['city']}")
    if candidate_data.get("email"):
        parts.append(f"Email: {candidate_data['email']}")
    if candidate_data.get("phone"):
        parts.append(f"Телефон: {candidate_data['phone']}")
    if candidate_data.get("telegram"):
        parts.append(f"Telegram: {candidate_data['telegram']}")
    if candidate_data.get("salary"):
        parts.append(f"Зарплатные ожидания: {candidate_data['salary']}")
    if candidate_data.get("total_experience"):
        parts.append(f"Общий опыт: {candidate_data['total_experience']}")
    if candidate_data.get("summary"):
        parts.append(f"О себе:\n{candidate_data['summary']}")
    if candidate_data.get("experience_summary"):
        parts.append(f"Последние места работы:\n{candidate_data['experience_summary']}")
    if candidate_data.get("experience_descriptions"):
        descs = candidate_data["experience_descriptions"]
        if isinstance(descs, list):
            for i, d in enumerate(descs[:6], 1):
                parts.append(f"Описание опыта #{i}:\n{d}")
    if candidate_data.get("skills"):
        skills = candidate_data["skills"]
        if isinstance(skills, list):
            parts.append(f"Навыки: {', '.join(skills)}")
    if candidate_data.get("languages"):
        langs = candidate_data["languages"]
        if isinstance(langs, list):
            parts.append(f"Языки: {', '.join(langs)}")
    if candidate_data.get("education"):
        edu = candidate_data["education"]
        if isinstance(edu, list):
            parts.append(f"Образование: {'; '.join(str(e) for e in edu)}")
    if candidate_data.get("certifications"):
        certs = candidate_data["certifications"]
        if isinstance(certs, list):
            parts.append(f"Лицензии и сертификаты: {'; '.join(str(c) for c in certs)}")

    raw_data = "\n\n".join(parts)

    prompt = f"""Ты HR-аналитик. На основе данных кандидата создай структурированное резюме-профиль.

Данные кандидата:
{raw_data}

Создай профиль в формате markdown со следующими разделами:
# [ФИО кандидата]

## Общая информация
Маркированный список «**Поле:** значение» (возраст, город, контакты, зарплатные ожидания)

## Профессиональный профиль
Краткое описание кандидата в 2-3 предложения на основе всей информации

## Опыт работы
Для каждого места: должность, компания, период, краткое описание достижений

## Ключевые навыки
Список навыков сгруппированный по категориям (hard skills, soft skills)

## Языки
Список языков с уровнями

## Образование
Учебные заведения, специальности, годы

## Лицензии и сертификаты
Список сертификатов с организацией (пропусти раздел, если данных нет)

## Итоговая оценка
Краткая оценка сильных сторон и зон роста кандидата

Пиши на русском, кратко и по делу. Не выдумывай информацию которой нет в данных.

ФОРМАТ (строго): только заголовки (##), маркированные списки (• или -) и абзацы.
НЕ используй markdown-таблицы (строки вида «| ... | ... |») — они ломают PDF."""

    try:
        client = anthropic.AsyncAnthropic(api_key=api_key)
        response = await client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text
    except Exception as e:
        logger.error(f"AI summary generation failed: {e}")
        return _fallback_summary(candidate_data)


def _fallback_summary(data: dict) -> str:
    """Generate plain markdown summary without AI."""
    lines = [f"# {data.get('full_name', 'Кандидат')}"]
    lines.append("")
    lines.append("## Общая информация")
    if data.get("position"):
        lines.append(f"- **Желаемая должность:** {data['position']}")
    if data.get("age"):
        lines.append(f"- **Возраст:** {data['age']}")
    if data.get("birthday"):
        lines.append(f"- **Дата рождения:** {data['birthday']}")
    if data.get("city"):
        lines.append(f"- **Город:** {data['city']}")
    if data.get("email"):
        lines.append(f"- **Email:** {data['email']}")
    if data.get("phone"):
        lines.append(f"- **Телефон:** {data['phone']}")
    if data.get("telegram"):
        lines.append(f"- **Telegram:** {data['telegram']}")
    if data.get("salary"):
        lines.append(f"- **Зарплатные ожидания:** {data['salary']}")
    if data.get("total_experience"):
        lines.append(f"- **Общий опыт:** {data['total_experience']}")

    if data.get("experience_summary"):
        lines.append("")
        lines.append("## Опыт работы")
        for exp_line in data["experience_summary"].split("\n"):
            if exp_line.strip():
                lines.append(f"- {exp_line.strip()}")

    if data.get("experience_descriptions"):
        descs = data["experience_descriptions"]
        if isinstance(descs, list):
            for i, d in enumerate(descs[:3], 1):
                lines.append(f"")
                lines.append(f"### Описание опыта #{i}")
                lines.append(d[:500])

    if data.get("skills"):
        skills = data["skills"]
        if isinstance(skills, list):
            lines.append("")
            lines.append("## Навыки")
            lines.append(", ".join(skills))

    if data.get("languages"):
        langs = data["languages"]
        if isinstance(langs, list):
            lines.append("")
            lines.append("## Языки")
            for lang in langs:
                lines.append(f"- {lang}")

    if data.get("certifications"):
        certs = data["certifications"]
        if isinstance(certs, list):
            lines.append("")
            lines.append("## Лицензии и сертификаты")
            for c in certs:
                lines.append(f"- {c}")

    return "\n".join(lines)


def generate_candidate_pdf(
    markdown_content: str,
    candidate_name: str,
    photo_bytes: Optional[bytes] = None,
) -> bytes:
    """Generate a styled PDF from markdown content.

    If photo_bytes is provided, renders the photo at the top of the first
    page next to the candidate's name (inside a 2-column table).
    """
    use_cyrillic = _register_fonts()
    font_regular = 'DejaVuSans' if use_cyrillic else 'Helvetica'
    font_bold = 'DejaVuSans-Bold' if use_cyrillic else 'Helvetica-Bold'

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=20 * mm, bottomMargin=15 * mm,
        leftMargin=18 * mm, rightMargin=18 * mm,
    )

    styles = getSampleStyleSheet()

    # --- Custom styles ---
    styles.add(ParagraphStyle(
        name='CandTitle', fontName=font_bold, fontSize=18,
        spaceBefore=0, spaceAfter=4,
        textColor=colors.HexColor('#1a1a2e'),
    ))
    styles.add(ParagraphStyle(
        name='CandSubtitle', fontName=font_regular, fontSize=10,
        spaceAfter=10,
        textColor=colors.HexColor('#666677'),
    ))
    styles.add(ParagraphStyle(
        name='CandH2', fontName=font_bold, fontSize=13,
        spaceBefore=14, spaceAfter=6,
        textColor=colors.HexColor('#2d2d44'),
    ))
    styles.add(ParagraphStyle(
        name='CandH3', fontName=font_bold, fontSize=11,
        spaceBefore=10, spaceAfter=4,
        textColor=colors.HexColor('#3d3d54'),
    ))
    styles.add(ParagraphStyle(
        name='CandBody', fontName=font_regular, fontSize=9.5,
        spaceAfter=4, leading=13,
        textColor=colors.HexColor('#333344'),
    ))
    styles.add(ParagraphStyle(
        name='CandBullet', fontName=font_regular, fontSize=9.5,
        spaceAfter=3, leftIndent=15, bulletIndent=8,
        leading=13, textColor=colors.HexColor('#333344'),
    ))
    styles.add(ParagraphStyle(
        name='CandBold', fontName=font_bold, fontSize=9.5,
        spaceAfter=3, leading=13,
        textColor=colors.HexColor('#333344'),
    ))

    story = []

    # Header: photo (left, 30x40mm) + candidate name (right), if photo is provided
    photo_rendered = False
    if photo_bytes:
        try:
            photo_img = Image(io.BytesIO(photo_bytes), width=30 * mm, height=40 * mm)
            photo_img.hAlign = 'LEFT'
            name_para = Paragraph(_escape(candidate_name), styles['CandTitle'])
            header_table = Table(
                [[photo_img, name_para]],
                colWidths=[34 * mm, None],
            )
            header_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (0, 0), 6),
                ('RIGHTPADDING', (1, 0), (1, 0), 0),
                ('TOPPADDING', (0, 0), (-1, -1), 0),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]))
            story.append(header_table)
            story.append(Spacer(1, 8))
            photo_rendered = True
        except Exception as e:
            logger.warning(f"Failed to embed photo in PDF: {e}")

    # Parse markdown — skip the first H1 if we already rendered the name
    # inside the photo header block to avoid a duplicate title.
    skipped_first_h1 = not photo_rendered
    lines = markdown_content.split('\n')
    for line in lines:
        line = line.rstrip()
        stripped = line.strip()

        if not stripped:
            story.append(Spacer(1, 4))
        elif stripped.startswith('### '):
            story.append(Paragraph(_escape(stripped[4:]), styles['CandH3']))
        elif stripped.startswith('## '):
            # Add separator line before H2
            story.append(Spacer(1, 4))
            story.append(HRFlowable(
                width="100%", thickness=0.5,
                color=colors.HexColor('#ddddee'),
                spaceAfter=4, spaceBefore=6,
            ))
            story.append(Paragraph(_escape(stripped[3:]), styles['CandH2']))
        elif stripped.startswith('# '):
            if not skipped_first_h1:
                # First H1 — skip, we already rendered the name in the photo header
                skipped_first_h1 = True
                continue
            story.append(Paragraph(_escape(stripped[2:]), styles['CandTitle']))
        elif stripped.startswith('**') and stripped.endswith('**'):
            story.append(Paragraph(
                f"<b>{_escape(stripped[2:-2])}</b>", styles['CandBold'],
            ))
        elif stripped.startswith('- ') or stripped.startswith('* ') or stripped.startswith('• '):
            text = stripped[2:]
            # Handle bold inside bullet
            text = _escape(text)
            text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
            story.append(Paragraph(f"• {text}", styles['CandBullet']))
        elif re.match(r'^\d+\.\s', stripped):
            text = _escape(stripped)
            text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
            story.append(Paragraph(text, styles['CandBullet']))
        elif stripped.startswith('---') or stripped.startswith('___'):
            story.append(HRFlowable(
                width="100%", thickness=0.5,
                color=colors.HexColor('#ddddee'),
                spaceAfter=6, spaceBefore=6,
            ))
        elif stripped.startswith('|') and stripped.endswith('|'):
            # Markdown-таблица. Раньше такие строки проваливались в else и
            # печатались буквально («| Город | София |», «|----|----|») — мусор
            # в PDF. Теперь: строку-разделитель |---|---| выкидываем целиком,
            # строку данных | ключ | значение | рисуем как буллет «ключ: значение».
            cells = [c.strip() for c in stripped.strip('|').split('|')]
            # Разделитель (только дефисы/двоеточия/пробелы) — пропускаем.
            if all(re.fullmatch(r'[:\-\s]*', c) for c in cells):
                continue
            cells = [c for c in cells if c]
            if not cells:
                continue
            # Шапка таблицы «Параметр | Значение» — не данные, пропускаем.
            if (len(cells) >= 2 and cells[0].lower() in ('параметр', 'ключ', 'поле')
                    and cells[1].lower() in ('значение', 'value')):
                continue
            if len(cells) >= 2:
                key = _escape(cells[0])
                val = _escape(' — '.join(cells[1:]))
                val = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', val)
                story.append(Paragraph(f"<b>{key}:</b> {val}", styles['CandBullet']))
            else:
                story.append(Paragraph(_escape(cells[0]), styles['CandBody']))
        else:
            text = _escape(stripped)
            text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
            text = re.sub(r'\*(.+?)\*', r'<i>\1</i>', text)
            if text:
                story.append(Paragraph(text, styles['CandBody']))

    # Footer
    story.append(Spacer(1, 20))
    story.append(HRFlowable(
        width="100%", thickness=0.5,
        color=colors.HexColor('#ccccdd'),
        spaceAfter=6,
    ))
    story.append(Paragraph(
        f"Сгенерировано: {datetime.now().strftime('%d.%m.%Y %H:%M')} | HR-Bot AI",
        ParagraphStyle(
            'Footer', fontName=font_regular, fontSize=7,
            textColor=colors.HexColor('#999999'),
        ),
    ))

    doc.build(story)
    buffer.seek(0)
    return buffer.read()


def pdf_to_jpeg(pdf_bytes: bytes, dpi: int = 200) -> list[bytes]:
    """Convert PDF bytes to list of JPEG images (one per page)."""
    import fitz  # PyMuPDF

    images = []
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    for page_num in range(len(doc)):
        page = doc[page_num]
        zoom = dpi / 72
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        img_bytes = pix.tobytes(output="jpeg")
        images.append(img_bytes)
    doc.close()
    return images
