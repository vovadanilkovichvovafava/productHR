"""Картинки файлов кандидата кэшируются браузером, JSON API — нет (16.10.2026).

Эльвира: «карточки подвисали, дёргались… метки и анкета пропадали, спустя время
догружалось». На проде каждая аватарка в списке — полноразмерное фото ~340 КБ,
и глобальный no-store заставлял браузер качать их ЗАНОВО при любой перерисовке
списка. Здесь закреплено исключение и то, что оно не расползлось на JSON:
no-store для API появился из-за Safari, который отдавал устаревшие списки.
"""
from starlette.applications import Starlette
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from starlette.testclient import TestClient

from api.middleware.security import IMAGE_CACHE_CONTROL, SecurityHeadersMiddleware


async def _image(request):
    return Response(b"\x89PNG", media_type="image/png")


async def _pdf(request):
    return Response(b"%PDF", media_type="application/pdf")


async def _json(request):
    return JSONResponse({"ok": True})


async def _missing(request):
    return Response(b"", status_code=404, media_type="image/png")


app = Starlette(
    routes=[
        Route("/api/entities/7/files/42/download", _image),
        Route("/api/entities/7/files/43/download", _pdf),
        Route("/api/entities/7/files/44/download", _missing),
        Route("/api/entities/7", _json),
        Route("/api/entities/7/files/42/download/extra", _image),
    ]
)
app.add_middleware(SecurityHeadersMiddleware)
client = TestClient(app)


def test_avatar_image_is_cached_privately():
    r = client.get("/api/entities/7/files/42/download")
    assert r.headers["cache-control"] == IMAGE_CACHE_CONTROL
    assert "private" in r.headers["cache-control"]


def test_json_api_is_still_never_cached():
    r = client.get("/api/entities/7")
    assert "no-store" in r.headers["cache-control"]


def test_pdf_download_is_not_cached():
    # Исключение только для картинок — остальное как было.
    r = client.get("/api/entities/7/files/43/download")
    assert "no-store" in r.headers["cache-control"]


def test_missing_file_is_not_cached():
    # 404 не должен залипнуть в кэше на неделю.
    r = client.get("/api/entities/7/files/44/download")
    assert "no-store" in r.headers["cache-control"]


def test_only_exact_download_path():
    r = client.get("/api/entities/7/files/42/download/extra")
    assert "no-store" in r.headers["cache-control"]
