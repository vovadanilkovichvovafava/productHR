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

# (статус кандидата, подпись, цвет, есть ли колонка в воронке, показывать ли)
#
# Список и названия — как у Марии (10.11.2026, «актуальные статусы в базе
# кандидатов… уберите лишние»): Новые, Выполняют ТЗ, Интервью с HR, Интервью с
# заказчиком, Выставлен оффер, Оффер принят, Практика, Перешёл в отдел, Отказ,
# Мы уволили, Сам уволился, Резерв. «Принятие решения» и «Отозван» убраны
# (на проде на них не было ни кандидатов, ни заявок, ни архивных): строки
# остались только ради подписей в старой истории — вкладок, пунктов выбора и
# колонок воронки у них нет (shown=False).
_STAGES = [
    (EntityStatus.new,           "Новые",                 "#3b82f6", True,  True),
    (EntityStatus.screening,     "Выполняют ТЗ",          "#06b6d4", True,  True),
    (EntityStatus.practice,      "Интервью с HR",         "#a855f7", True,  True),
    (EntityStatus.tech_practice, "Интервью с заказчиком", "#6366f1", True,  True),
    (EntityStatus.is_interview,  "Принятие решения",      "#f97316", False, False),
    (EntityStatus.offer,         "Выставлен оффер",       "#eab308", True,  True),
    (EntityStatus.hired,         "Оффер принят",          "#22c55e", True,  True),
    (EntityStatus.probation,     "Практика",              "#14b8a6", True,  True),
    (EntityStatus.transferred,   "Перешёл в отдел",       "#16a34a", True,  True),
    (EntityStatus.rejected,      "Отказ",                 "#ef4444", True,  True),
    (EntityStatus.withdrawn,     "Отозван",               "#6b7280", False, False),
    (EntityStatus.reserve,       "Резерв",                "#6b7280", True,  True),
]

# Колонка-приёмник «Все кандидаты» для статусов вне списка (легаси, убранные
# этапы) — чтобы такие кандидаты не выпадали с доски (18.09.2026). Пустая —
# не показывается.
OTHER_STATUS = "other"
OTHER_LABEL = "Вне воронки"

# «Мы уволили» / «Сам уволился» — итог работы с человеком после отдела. С
# 10.11.2026 у них СВОИ вкладки на «Все кандидаты» (список Марии; до этого
# стояли во вкладке «Отказ»). Этапа заявки у них нет: в воронках уволенный —
# «Отказ» (все живые заявки закрываются, stage_change.depart_entity).
DEPARTED_LABELS: dict[str, str] = {
    EntityStatus.dismissed.value: "Мы уволили",
    EntityStatus.quit.value: "Сам уволился",
}

# Статусы кандидата в порядке вкладок «Все кандидаты».
BOARD_STATUSES: list[str] = []
for _status, _label, _color, _in_funnel, _shown in _STAGES:
    if _shown:
        BOARD_STATUSES.append(_status.value)
    if _status == EntityStatus.rejected:
        BOARD_STATUSES.extend(DEPARTED_LABELS)

# Подпись по статусу кандидата (EntityStatus.value), включая «Вне воронки».
STATUS_LABELS: dict[str, str] = {
    **{s.value: label for s, label, *_ in _STAGES},
    **DEPARTED_LABELS,
    OTHER_STATUS: OTHER_LABEL,
}


def board_column(status: str) -> str:
    """Вкладка «Все кандидаты», в которой стоит кандидат с этим статусом."""
    return status if status in BOARD_STATUSES else OTHER_STATUS


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
    for s, label, color, in_funnel, _shown in _STAGES
    if in_funnel
]


def stage_label(stage) -> str:
    """Подпись этапа заявки: enum или строка; неизвестное — как есть."""
    value = stage.value if hasattr(stage, "value") else str(stage)
    return STAGE_LABELS.get(value, value)


# Причины отказа — список Марии (11.11.2026: «добавь под статус „Отказ“ эти
# причины, без них перевести на статус нельзя»). Окно смены этапа кладёт
# выбранную причину ПЕРВОЙ строкой комментария; по ней же заполняется
# `VacancyApplication.rejection_reason` (отчёт «Причины отказов» группирует
# по этому полю — список даёт ровные категории вместо свободного текста).
# Тот же список — `REJECTION_REASONS` в frontend/src/constants/hrStages.ts.
REJECTION_REASONS: tuple[str, ...] = (
    "Высокие запросы по зарплате",
    "Закрыли вакансию другим",
    "Кандидат отказался сам",
    "Неприемлемые личностные качества",
    "Перестал отвечать",
    "Плохо выполненное ТЗ",
    "Принял другой оффер",
    "Принял контроффер",
    "Связь с серыми нишами",
    "Слабые тех. скиллы",
)

_REASON_BY_KEY = {r.lower().replace("ё", "е"): r for r in REJECTION_REASONS}


def match_rejection_reason(line: str | None) -> str | None:
    """Строка — одна из причин списка? Возвращает её каноническое написание."""
    key = (line or "").strip().rstrip(".").lower().replace("ё", "е")
    return _REASON_BY_KEY.get(key)

