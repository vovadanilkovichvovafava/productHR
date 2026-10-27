"""Контакты кандидата из ТЕКСТА резюме — только из шапки, без ИИ (22.09.2026).

Зачем. В карточке контактов часто нет (кандидат с hh.ru скрыл их, резюме
добавили файлом), а в самом PDF они есть. Такой телефон/почта — полноценный
признак «тот же человек», но только если это контакт САМОГО кандидата. В
резюме бывают и чужие контакты: рекомендатели, прежние руководители, телефоны
компаний.

Как отличаем. Контакты кандидата в резюме hh.ru / rabota.by / SuperJob всегда
в шапке — под ФИО, до первого раздела («Желаемая должность», «Опыт работы»,
«Образование»…). Чужие — ниже, в «Рекомендациях» и «Опыте работы». Поэтому:
- берём контакты только из шапки;
- в шапке пропускаем строки со словами «рекомендац…», «руководител…»,
  «контактное лицо» и т.п.;
- если ни одного заголовка раздела нет (резюме свободной формы) — не берём
  ничего: границу шапки не определить, лучше пропустить, чем ошибиться.
"""
import re
from typing import Dict, List

from .phone_keys import e164_variants
from .similarity import is_junk_telegram, is_service_email, normalize_email

# Заголовки разделов резюме: первая такая строка — конец шапки.
_SECTION_RE = re.compile(
    r"^\s*(?:"
    r"желаемая\s+должность|опыт\s+работы|образование|ключевые\s+навыки|навыки|"
    r"обо\s+мне|о\s+себе|дополнительная\s+информация|рекомендации|"
    r"специализаци[яи]|занятость|график\s+работы|повышение\s+квалификации|"
    r"знание\s+языков|портфолио|цель|"
    r"desired\s+position|work\s+experience|experience|education|skills|"
    r"key\s+skills|about\s+me|summary|references|languages"
    r")\b",
    re.I | re.M,
)
# Строки шапки, где контакт заведомо чужой.
_FOREIGN_RE = re.compile(
    r"рекоменд|руководител|контактн\w*\s+лиц|начальник|директор|менеджер\s+по\s+персоналу|"
    r"reference|supervisor|manager",
    re.I,
)
# Шапка не бывает длинной: дальше — уже содержимое резюме.
_HEADER_MAX_LINES = 25

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[a-z]{2,}", re.I)
_PHONE_RE = re.compile(r"(?:\+|\b)\d[\d\s().\-]{7,20}\d")
_TG_RE = re.compile(r"(?:t\.me/|telegram[:\s]+@?|@)([A-Za-z][A-Za-z0-9_]{4,31})\b", re.I)


def header_lines(text: str) -> List[str]:
    """Строки шапки резюме или пустой список, если шапку не определить."""
    if not text:
        return []
    lines = text.splitlines()
    for i, line in enumerate(lines[: _HEADER_MAX_LINES + 1]):
        if _SECTION_RE.match(line):
            return lines[:i]
    return []  # раздела в начале нет — свободная форма, не рискуем


def extract_header_contacts(text: str) -> Dict[str, List[str]]:
    """{"phones": [...E.164], "emails": [...], "telegrams": [...]} из шапки."""
    phones: List[str] = []
    emails: List[str] = []
    tgs: List[str] = []
    for line in header_lines(text):
        if _FOREIGN_RE.search(line):
            continue
        for m in _EMAIL_RE.finditer(line):
            e = normalize_email(m.group(0))
            if e and not is_service_email(e) and e not in emails:
                emails.append(e)
        # Почту вырезаем, чтобы её цифры не читались как телефон.
        rest = _EMAIL_RE.sub(" ", line)
        for m in _PHONE_RE.finditer(rest):
            variants = e164_variants(m.group(0))
            # Номер без однозначной страны берём, только если прочтение одно —
            # иначе ключей получится много, а шапка должна давать точный признак.
            if len(variants) == 1:
                p = next(iter(variants))
                if p not in phones:
                    phones.append(p)
        for m in _TG_RE.finditer(rest):
            t = m.group(1).lower()
            if not is_junk_telegram(t) and t not in tgs:
                tgs.append(t)
    return {"phones": phones, "emails": emails, "telegrams": tgs}


# --- Разовое заполнение для уже сохранённых резюме -----------------------------

BACKFILL_MARK = "resume_contacts_backfill_2026_09_22"


async def backfill_resume_contacts_once(db) -> int:
    """Посчитать resume_contacts у кандидатов, чей текст резюме уже сохранён.

    Один раз (отметка в data_migration_marks). Плашки здесь не пересчитываются:
    это 8 тыс. анкет — новые совпадения найдёт «Сверить активных» (секунды) или
    открытие карточки. Коммитит. Возвращает число анкет, где нашлись контакты.
    """
    import asyncio
    import logging

    from sqlalchemy import select, update

    from ..models.database import DataMigrationMark, Entity, EntityType
    from .resume_text_extract import set_resume_contacts

    log = logging.getLogger("hr-analyzer.resume_contacts")
    if await db.get(DataMigrationMark, BACKFILL_MARK) is not None:
        return 0
    rows = (await db.execute(
        select(Entity.id, Entity.extra_data).where(Entity.type == EntityType.candidate)
    )).all()

    def compute():
        changed = []
        for eid, extra in rows:
            if not isinstance(extra, dict) or not extra.get("resume_text"):
                continue
            ne = dict(extra)
            src = extra.get("resume_text_source") if isinstance(extra.get("resume_text_source"), dict) else {}
            if set_resume_contacts(ne, extra["resume_text"], src.get("file_id")):
                changed.append((eid, ne))
        return changed

    changed = await asyncio.to_thread(compute)  # регулярки по тысячам текстов — не в цикле событий
    for eid, ne in changed:
        await db.execute(update(Entity).where(Entity.id == eid).values(extra_data=ne))
    db.add(DataMigrationMark(key=BACKFILL_MARK))
    await db.commit()
    log.info(f"RESUME_CONTACTS backfill: {len(changed)} candidates got header contacts")
    return len(changed)
