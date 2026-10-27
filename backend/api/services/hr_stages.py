"""Справочник этапов HR — ОДИН на весь сервер (рефакторинг 20.10.2026).

До этого подписи этапов были переписаны руками в восьми файлах (уведомления,
публичная ссылка, аналитика, «Все кандидаты», рабочие пространства, настройки
этапов орги…), и копии разъехались: в пяти не было «Резерва» — уведомление о
переводе в резерв, ссылка для заказчика и отчёты показывали сырое «reserve».

Порядок строк = порядок колонок. Этап заявки берётся из STATUS_SYNC_MAP
(models/database.py) — связку «статус кандидата ↔ этап заявки» не дублируем.
Цвет — тот, что фронт рисует у этапа (frontend/src/constants/hrStages.ts,
держать в паре).
"""
from __future__ import annotations

from ..models.database import STATUS_SYNC_MAP, ApplicationStage, EntityStatus

# (статус кандидата, подпись, цвет, есть ли колонка в воронке)
_STAGES = [
    (EntityStatus.new,           "Новый",                 "#3b82f6", True),
    (EntityStatus.screening,     "Выполняет ТЗ",          "#06b6d4", True),
    (EntityStatus.practice,      "Интервью с HR",         "#a855f7", True),
    (EntityStatus.tech_practice, "Интервью с заказчиком", "#6366f1", True),
    (EntityStatus.is_interview,  "Принятие решения",      "#f97316", True),
    (EntityStatus.offer,         "Выставлен оффер",       "#eab308", True),
    (EntityStatus.hired,         "Оффер принят",          "#22c55e", True),
    (EntityStatus.probation,     "Практика",              "#14b8a6", True),
    (EntityStatus.transferred,   "Перешёл в отдел",       "#16a34a", True),
    (EntityStatus.rejected,      "Отказ",                 "#ef4444", True),
    # «Отозван» — на доске «Все кандидаты» есть, вкладки в воронке нет.
    (EntityStatus.withdrawn,     "Отозван",               "#6b7280", False),
    (EntityStatus.reserve,       "Резерв",                "#6b7280", True),
]

# Колонка-приёмник «Все кандидаты» для статусов вне воронки (dismissed, quit,
# легаси) — чтобы такие кандидаты не выпадали с доски (18.09.2026).
OTHER_STATUS = "other"
OTHER_LABEL = "Вне воронки"

# Статусы кандидата в порядке колонок доски «Все кандидаты».
BOARD_STATUSES: list[str] = [s.value for s, *_ in _STAGES]

# Уволен / уволился — итог работы с человеком после отдела. Своей колонки на
# «Все кандидаты» у них нет: для HR это отказ, и стоят они во вкладке «Отказ»
# (Мария, 20.10.2026: «борд и АТС — единая система: уволен на борде → отказ в
# АТС»). Точный статус виден на доске «Штат» и в чипе.
DEPARTED_LABELS: dict[str, str] = {
    EntityStatus.dismissed.value: "Уволен",
    EntityStatus.quit.value: "Уволился",
}
_COLUMN_OF_STATUS: dict[str, str] = {
    EntityStatus.dismissed.value: EntityStatus.rejected.value,
    EntityStatus.quit.value: EntityStatus.rejected.value,
}

# Подпись по статусу кандидата (EntityStatus.value), включая «Вне воронки».
STATUS_LABELS: dict[str, str] = {
    **{s.value: label for s, label, *_ in _STAGES},
    **DEPARTED_LABELS,
    OTHER_STATUS: OTHER_LABEL,
}


def board_column(status: str) -> str:
    """Вкладка «Все кандидаты», в которой стоит кандидат с этим статусом."""
    if status in BOARD_STATUSES:
        return status
    return _COLUMN_OF_STATUS.get(status, OTHER_STATUS)


def statuses_in_column(column: str) -> list[str] | None:
    """Какие статусы показывает вкладка. None — «Все»: без фильтра по статусу.

    Одно правило для доски и для «Выбрать всех» (/candidates/ids): разойдутся —
    кнопка выделит не тех, кого показал список.
    """
    if not column or column == "all":
        return None
    known = [s.value for s in EntityStatus]
    return [s for s in known if board_column(s) == column]

# Подпись по этапу заявки (ApplicationStage.value). «new» — легаси-синоним
# «applied» в старых записях истории.
STAGE_LABELS: dict[str, str] = {
    **{STATUS_SYNC_MAP[s].value: label for s, label, *_ in _STAGES},
    "new": "Новый",
}

# То же, но по самому enum — для кода, который держит ApplicationStage.
STAGE_LABELS_BY_ENUM: dict[ApplicationStage, str] = {
    STATUS_SYNC_MAP[s]: label for s, label, *_ in _STAGES
}

# Этапы организации по умолчанию (GET /auth/org-stages): только колонки воронки.
DEFAULT_ORG_STAGES: list[dict] = [
    {"key": s.value, "label": label, "color": color}
    for s, label, color, in_funnel in _STAGES
    if in_funnel
]


def stage_label(stage) -> str:
    """Подпись этапа заявки: enum или строка; неизвестное — как есть."""
    value = stage.value if hasattr(stage, "value") else str(stage)
    return STAGE_LABELS.get(value, value)
