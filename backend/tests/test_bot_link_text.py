"""Текст бота, когда команда недоступна (12.11.2026): у владельца Telegram был
привязан к аккаунту суперадмина без организации, а бот отвечал «Сначала
привяжите аккаунт» — будто ничего не привязано."""
from types import SimpleNamespace

from api.bot import LINK_FIRST_TEXT, _link_problem_text


def test_not_linked_asks_to_link():
    assert _link_problem_text(None) == LINK_FIRST_TEXT


def test_linked_without_org_says_so():
    text = _link_problem_text(SimpleNamespace(name="Vova_dev", email="x@y"))
    assert "привязан к аккаунту «Vova_dev»" in text
    assert "организации" in text
    assert "Сначала привяжите" not in text
