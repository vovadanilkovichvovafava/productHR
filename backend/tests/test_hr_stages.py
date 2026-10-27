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


def test_board_statuses_cover_sync_map():
    assert set(hr_stages.BOARD_STATUSES) == {s.value for s in STATUS_SYNC_MAP}
    for status in STATUS_SYNC_MAP:
        assert status.value in hr_stages.STATUS_LABELS


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
    assert EntityStatus.withdrawn.value not in keys  # у «Отозван» нет вкладки воронки
    assert keys == [s for s in hr_stages.BOARD_STATUSES if s != "withdrawn"]


def test_no_handwritten_label_tables_left():
    """Новая копия словаря подписей — повод взять справочник, а не писать свой."""
    api_dir = Path(__file__).resolve().parents[1] / "api"
    offenders = []
    for path in api_dir.rglob("*.py"):
        if path.name == "hr_stages.py":
            continue
        text = path.read_text(encoding="utf-8")
        if '"Выполняет ТЗ",' in text or "'Выполняет ТЗ'," in text:
            offenders.append(str(path.relative_to(api_dir)))
    assert offenders == []
