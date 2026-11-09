"""Справочник отделов и должностей доски «Штат» (09.11.2026).

Раньше отдел заводили кнопкой «+ Отдел» с любым названием, а должность
вписывали руками: на доске копились «Facebook», «FB», «Facebook team» и
«медиабаер»/«Media Buyer». Владелец прислал фиксированный список: какие есть
отделы и какие должности в каждом. Теперь перевод в отдел и должность —
только выбором из него.

Список живёт ЗДЕСЬ, в одном месте: фронт получает его с отделами
(`BoardDept.positions`), своей копии не держит.

Решения владельца (09.11.2026):
- отдел с похожим названием («Facebook», «SEO», «Google») ПЕРЕИМЕНОВЫВАЕТСЯ в
  новое имя — люди, даты и история остаются на месте, дублей нет;
- отдел, не похожий ни на один из списка («iOS Product», «ASA»), остаётся с
  людьми, но в выпадающем списке перевода его больше нет;
- песочницы (SANDBOX…) список не трогает: это практика, а не отделы.
"""
from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select

from ..models.database import BoardDepartment, DataMigrationMark

logger = logging.getLogger("hr-analyzer.board_catalog")

CANON_MARK = "board_dept_canon_2026_11_09"

# (отдел, другие написания того же отдела, должности). Написания сравниваются
# после _norm: без регистра, пробелов, знаков и слова «team»/«команда».
CANON_TEAMS: List[Tuple[str, Tuple[str, ...], List[str]]] = [
    ("SEO team", ("seo", "сео"), [
        "SEO Buyer Team Lead",
        "SEO Buyer",
        "SEO System Administrator",
        "SEO Copywriter",
        "SEO Developer",
    ]),
    ("Push team", ("push", "пуш"), [
        "Push Media Buyer Team Lead",
        "Push Media Buyer",
    ]),
    ("Facebook team", ("facebook", "fb", "facebookads", "фейсбук", "фб"), [
        "Facebook Media Buyer Team Lead",
        "Facebook Media Buyer",
    ]),
    ("Google Ads team", ("googleads", "google", "gads", "гугл", "гуглэдс"), [
        "Google Ads Media Buyer Team Lead",
        "Google Ads Media Buyer",
        "Google Ads Farming Team Lead",
        "Google Ads Account Farmer",
    ]),
    ("BizDev team", ("bizdev", "businessdevelopment", "bd", "биздев"), [
        "Business Development Team Lead",
        "Business Development Manager",
    ]),
    ("HR team", ("hr", "эйчар"), [
        "HR Director",
        "HR Team Lead",
        "HR Manager",
        "Recruiter",
        "Talent Sourcer",
    ]),
    ("Product Studio", ("productstudio", "product", "продукт", "studio"), [
        "Product Studio Team Lead",
        "Project Manager",
        "Developer",
        "UA Manager",
        "Operations Manager",
        "Creative Producer",
        "Video Editor",
        "Billing Manager",
    ]),
]

_NOISE = re.compile(r"\b(team|команда|отдел)\b", re.IGNORECASE)


def _norm(name: str) -> str:
    s = _NOISE.sub("", (name or "").lower().replace("ё", "е"))
    return re.sub(r"[^0-9a-zа-я]", "", s)


_BY_NORM: Dict[str, int] = {}
for _i, (_name, _aliases, _) in enumerate(CANON_TEAMS):
    for _a in (_name, *_aliases):
        _BY_NORM[_norm(_a)] = _i


def canon_index(name: Optional[str]) -> Optional[int]:
    """Номер отдела в списке, если название — он или его другое написание."""
    return _BY_NORM.get(_norm(name or ""))


def positions_for(name: Optional[str]) -> List[str]:
    """Должности отдела из списка; у отдела вне списка — пусто."""
    i = canon_index(name)
    return list(CANON_TEAMS[i][2]) if i is not None else []


async def canonize_board_departments_once(db) -> None:
    """Разово: привести отделы доски к списку владельца.

    Для каждой организации, где доска уже заведена: похожий отдел получает
    новое имя, недостающие отделы создаются. Песочницы и отделы вне списка не
    трогаются. Если похожих несколько, переименовывается один (сначала тот, где
    уже стоит точное имя, иначе видимый, иначе с меньшим id) — остальные
    остаются как есть и пишутся в лог, чтобы HR разнёс людей сам.
    """
    if await db.get(DataMigrationMark, CANON_MARK) is not None:
        return

    depts = (await db.execute(select(BoardDepartment))).scalars().all()
    by_org: Dict[int, List[BoardDepartment]] = {}
    for d in depts:
        by_org.setdefault(d.org_id, []).append(d)

    renamed = created = 0
    for org_id, items in by_org.items():
        teams = [d for d in items if (d.kind or "team") != "sandbox"]
        for i, (name, _aliases, _positions) in enumerate(CANON_TEAMS):
            matches = sorted(
                (d for d in teams if canon_index(d.name) == i),
                key=lambda d: (d.name != name, d.hidden_at is not None, d.id),
            )
            if not matches:
                db.add(BoardDepartment(org_id=org_id, name=name, kind="team", visibility="all"))
                created += 1
                logger.info(f"BOARD_DEPT_CANON org {org_id}: создан «{name}»")
                continue
            main = matches[0]
            if main.name != name:
                logger.info(f"BOARD_DEPT_CANON org {org_id}: «{main.name}» → «{name}» (id={main.id})")
                main.name = name
                renamed += 1
            if main.hidden_at is not None:
                main.hidden_at = None   # отдел из списка должен предлагаться
            for extra in matches[1:]:
                logger.warning(
                    f"BOARD_DEPT_CANON org {org_id}: «{extra.name}» (id={extra.id}) тоже похож "
                    f"на «{name}» — оставлен как есть, людей перенести руками"
                )

    db.add(DataMigrationMark(key=CANON_MARK))
    await db.commit()
    logger.info(f"BOARD_DEPT_CANON: переименовано {renamed}, создано {created}")
