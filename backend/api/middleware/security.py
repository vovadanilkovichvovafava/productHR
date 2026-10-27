"""
Security middleware for adding security headers to all responses.
"""

import re

from starlette.middleware.base import BaseHTTPMiddleware

# Скачивание файла кандидата. Байты файла по его id НИКОГДА не меняются (новая
# загрузка = новый id, удаление = 404), поэтому картинки отсюда можно кэшировать.
_FILE_DOWNLOAD = re.compile(r"^/api/entities/\d+/files/\d+/download$")
# Картинке — неделя в кэше ЭТОГО браузера (private: не для общих прокси).
IMAGE_CACHE_CONTROL = "private, max-age=604800, immutable"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to add security headers to all responses."""

    async def dispatch(self, request, call_next):
        response = await call_next(request)

        # Skip CSP for API responses (JSON) — browsers don't enforce CSP on them
        path = request.url.path
        if path.startswith("/api/") or path.startswith("/health"):
            response.headers["X-Content-Type-Options"] = "nosniff"
            # Исключение — картинки файлов кандидата (аватарки в списке, сканы
            # резюме). С no-store браузер качал КАЖДУЮ аватарку (~340 КБ, ~0,5 с)
            # заново при любой перерисовке списка — переключил вкладку или раздел,
            # пришло обновление доски. Пока качалась — пусто («пропадают
            # аватарки»), а десятки таких скачиваний забивали сервер, и метки с
            # анкетой открытой карточки ждали в очереди (Эльвира, 16.10.2026).
            # Проблема Safari ниже — про JSON, к неизменным байтам файла она не
            # относится.
            if (
                response.status_code == 200
                and _FILE_DOWNLOAD.match(path)
                and response.headers.get("content-type", "").startswith("image/")
            ):
                response.headers["Cache-Control"] = IMAGE_CACHE_CONTROL
                return response
            # НИКОГДА не кэшируем API-ответы. Они персональные и динамические.
            # Без этого Safari/WebKit агрессивно кэширует same-origin GET /api/*
            # и отдаёт УСТАРЕВШЕЕ тело даже после обычного reload — напр. пустой
            # /api/vacancies, закэшированный ДО выдачи доступа наблюдателю, из-за
            # чего юзер навсегда видел «0 вакансий» (Егор, Safari, 2026-08-26).
            # no-store заставляет браузер всегда идти на сервер.
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            return response

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            # Allow candidate photos fetched from external recruiting sites
            # (hh.ru CDN, habr career, LinkedIn) — harmless image data.
            "img-src 'self' data: blob: https:; "
            "media-src 'self' blob:; "
            "connect-src 'self' ws: wss:; "
            "worker-src 'self' blob:"
        )
        return response
