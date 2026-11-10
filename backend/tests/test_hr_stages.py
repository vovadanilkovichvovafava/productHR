"""Справочник этапов один на весь сервер (services/hr_stages.py, 20.10.2026).

Подписи были переписаны в восьми файлах, и в пяти из них не было «Резерва»:
уведомление о переводе в резерв, ссылка для заказчика и отчёты аналитики
показывали сырое «reserve». Тест сторожит, чтобы копии не вернулись.
"""
from pathlib import Path

from api.models.database import STATUS_SYNC_MAP, ApplicationStage, EntityStatus
from api.services import hr_stages


def test_every_funnel_stage_has_label():
    for stage in ApplicationStage:
        assert stage.value in hr_stages.STAGE_LABELS, stage
        assert stage in hr_stages.STAGE_LABELS_BY_ENUM, stage


def test_board_statuses_are_marias_list():
    """Вкладки «Все кандидаты» — ровно список Марии (10.11.2026), её порядок и
    её названия. «Принятие решения» и «Отозван» убраны, уволенные — своими
    вкладками после «Отказа»."""
    labels = [hr_stages.STATUS_LABELS[s] for s in hr_stages.BOARD_STATUSES]
    assert labels == [
        "Новые", "Выполняют ТЗ", "Интервью с HR", "Интервью с заказчиком",
        "Выставлен оффер", "Оффер принят", "Практика", "Перешёл в отдел", "Отказ",
        "Мы уволили", "Сам уволился", "Резерв",
    ]
    # Убранные этапы подписаны (старая история), но вкладки у них нет.
    for status in STATUS_SYNC_MAP:
        assert status.value in hr_stages.STATUS_LABELS
    assert hr_stages.board_column("is_interview") == hr_stages.OTHER_STATUS
    assert hr_stages.board_column("withdrawn") == hr_stages.OTHER_STATUS
    assert hr_stages.board_column("dismissed") == "dismissed"
    assert hr_stages.statuses_in_column("rejected") == ["rejected"]


def test_status_and_stage_labels_agree():
    for status, stage in STATUS_SYNC_MAP.items():
        assert hr_stages.STATUS_LABELS[status.value] == hr_stages.STAGE_LABELS[stage.value]


def test_reserve_is_labelled_everywhere():
    from api.routes.analytics import funnel, reports
    from api.routes.entities import share_links
    from api.services import hr_notifications

    assert funnel.STAGE_LABELS["reserve"] == "Резерв"
    assert reports.STAGE_LABELS["reserve"] == "Резерв"
    assert share_links.STAGE_LABELS["reserve"] == "Резерв"
    assert hr_notifications._stage_label(ApplicationStage.reserve) == "Резерв"


def test_default_org_stages_are_funnel_columns():
    keys = [s["key"] for s in hr_stages.DEFAULT_ORG_STAGES]
    assert EntityStatus.withdrawn.value not in keys
    assert EntityStatus.is_interview.value not in keys
    # Вкладки воронки = вкладки «Все кандидаты», кроме уволенных (у заявки их нет).
    assert keys == [s for s in hr_stages.BOARD_STATUSES if s not in ("dismissed", "quit")]


def test_no_handwritten_label_tables_left():
    """Новая копия словаря подписей — повод взять справочник, а не писать свой."""
    api_dir = Path(__file__).resolve().parents[1] / "api"
    offenders = []
    for path in api_dir.rglob("*.py"):
        if path.name == "hr_stages.py":
            continue
        text = path.read_text(encoding="utf-8")
        if '"Выполняют ТЗ",' in text or "'Выполняют ТЗ'," in text:
            offenders.append(str(path.relative_to(api_dir)))
    assert offenders == []
