"""Адрес анкеты без пробелов (20.10.2026): «Новая анкета» давала
«novaya anketa-…» — пробел проходил веткой ASCII раньше замены на дефис."""
import re

from api.routes.forms import generate_slug


def test_slug_has_no_spaces_and_is_url_safe():
    for title in ["Новая анкета", "Anketa for QA team", "  Тест — анкета  ", "Анкета: Трафик/SEO"]:
        slug = generate_slug(title)
        assert " " not in slug
        assert re.fullmatch(r"[a-z0-9_-]+", slug), slug
    assert generate_slug("Новая анкета").startswith("novaya-anketa-")
