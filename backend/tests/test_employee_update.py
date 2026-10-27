"""Edit-integrity: слияние extra_data не теряет посторонние ключи."""


def test_merge_extra_keeps_unrelated_keys():
    from api.routes.employees import _merge_extra
    base = {"passport": {"filename": "p"}, "address": "old", "documents": [1, 2]}
    patch = {"address": "new", "payment_method": "card"}
    out = _merge_extra(base, patch)
    assert out["passport"] == {"filename": "p"}   # не затёрто
    assert out["documents"] == [1, 2]             # не затёрто
    assert out["address"] == "new"                # обновлено
    assert out["payment_method"] == "card"        # добавлено


def test_merge_extra_handles_none():
    from api.routes.employees import _merge_extra
    assert _merge_extra(None, {"a": 1}) == {"a": 1}
    assert _merge_extra({"a": 1}, None) == {"a": 1}
    assert _merge_extra(None, None) == {}
