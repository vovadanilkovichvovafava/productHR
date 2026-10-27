"""Превью аватарок для списков (24.10.2026, services/image_thumbs.py).

Список просит `?thumb=1` и получает копию до 160 px вместо полного фото
(~340 КБ). Карточка и скачивание — по-прежнему оригинал.
"""
import io
import random

import pytest
from PIL import Image

from api.models.database import Entity, EntityFile, EntityFileType, EntityType
from api.services.auth import create_access_token
from api.services.image_thumbs import THUMB_MAX_SIDE


_REAL_OPEN = Image.open  # до автофикстуры conftest.mock_pillow, которая подменяет open


@pytest.fixture(autouse=True)
def real_pillow(mock_pillow, monkeypatch):
    # Здесь проверяется само уменьшение картинки — нужен настоящий Pillow.
    monkeypatch.setattr("PIL.Image.open", _REAL_OPEN)


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(u.id)})}"}


def _noisy_jpeg(w=1200, h=1600) -> bytes:
    # Шум — чтобы файл был «как фото», а не сжимался в пару килобайт.
    rnd = random.Random(1)
    img = Image.new("RGB", (w // 8, h // 8))
    img.putdata([(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256)) for _ in range((w // 8) * (h // 8))])
    out = io.BytesIO()
    img.resize((w, h)).save(out, format="JPEG", quality=95)
    return out.getvalue()


async def _photo(db, org, user, data, name="Фото_Иванов.jpg", mime="image/jpeg"):
    e = Entity(org_id=org.id, type=EntityType.candidate, name="Иванов Иван", created_by=user.id)
    db.add(e)
    await db.commit()
    f = EntityFile(entity_id=e.id, org_id=org.id, file_type=EntityFileType.other, file_name=name,
                   file_data=data, file_size=len(data), mime_type=mime, uploaded_by=user.id)
    db.add(f)
    await db.commit()
    return e, f


async def test_thumb_is_small_jpeg_and_cached(client, db_session, organization, org_owner, admin_user):
    big = _noisy_jpeg()
    assert len(big) > 200_000
    e, f = await _photo(db_session, organization, admin_user, big)
    url = f"/api/entities/{e.id}/files/{f.id}/download"

    r = await client.get(url + "?thumb=1", headers=_h(admin_user))
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"
    assert len(r.content) < 30_000
    with Image.open(io.BytesIO(r.content)) as img:
        assert max(img.size) == THUMB_MAX_SIDE
        assert img.size == (120, 160)  # пропорции сохранены
    assert "immutable" in r.headers["cache-control"]

    # Без ?thumb — оригинал, как раньше (карточка, скачивание).
    r = await client.get(url, headers=_h(admin_user))
    assert r.content == big


async def test_small_or_broken_image_falls_back_to_original(client, db_session, organization, org_owner, admin_user):
    tiny = io.BytesIO()
    Image.new("RGB", (40, 40), (200, 10, 10)).save(tiny, format="PNG")
    e, f = await _photo(db_session, organization, admin_user, tiny.getvalue(), name="Фото_мал.png", mime="image/png")
    r = await client.get(f"/api/entities/{e.id}/files/{f.id}/download?thumb=1", headers=_h(admin_user))
    assert r.status_code == 200 and r.content == tiny.getvalue()

    broken = b"\xff\xd8\xff" + b"x" * 50_000
    e2, f2 = await _photo(db_session, organization, admin_user, broken, name="Фото_битое.jpg")
    r = await client.get(f"/api/entities/{e2.id}/files/{f2.id}/download?thumb=1", headers=_h(admin_user))
    assert r.status_code == 200 and r.content == broken


async def test_thumb_ignored_for_non_images(client, db_session, organization, org_owner, admin_user):
    pdf = b"%PDF-1.4 " + b"0" * 60_000
    e, f = await _photo(db_session, organization, admin_user, pdf, name="Резюме.pdf", mime="application/pdf")
    r = await client.get(f"/api/entities/{e.id}/files/{f.id}/download?thumb=1", headers=_h(admin_user))
    assert r.status_code == 200 and r.content == pdf
