"""
Correlation ID middleware for request tracing.

Adds a correlation ID to each request for log tracing across services.
"""

import os
import time
import uuid
from datetime import datetime

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from ..database import get_db
from ..services.audit import MAX_BODY_BYTES, clean_body, describe, ids_from, should_audit, write_event
from ..utils.logging import set_correlation_id, get_correlation_id, log_request


class CorrelationMiddleware(BaseHTTPMiddleware):
    """
    Middleware that adds correlation ID to each request.

    The correlation ID is:
    1. Extracted from X-Correlation-ID header if present
    2. Generated as a new UUID if not present
    3. Added to response headers
    4. Available in logs via correlation_id context var

    С 21.10.2026 здесь же — КТО сделал запрос (строка лога «… · Имя (id)») и
    журнал действий в базе (services/audit.py): каждый изменяющий запрос
    записывается с пользователем, действием, номерами и данными запроса.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Get or generate correlation ID
        correlation_id = request.headers.get("X-Correlation-ID")
        if not correlation_id:
            correlation_id = str(uuid.uuid4())[:8]

        # Set in context for logging
        set_correlation_id(correlation_id)

        method = request.method
        path = request.url.path
        audit = should_audit(method, path)
        raw_body = None
        content_type = request.headers.get("content-type", "")
        try:
            content_length = int(request.headers.get("content-length") or 0)
        except ValueError:
            content_length = 0
        if audit and "multipart" not in content_type.lower() and content_length <= MAX_BODY_BYTES:
            # Starlette кэширует тело — ручка получит его как обычно.
            raw_body = await request.body()

        # Track request timing
        start_time = time.perf_counter()

        # Process request
        response = await call_next(request)

        # Calculate duration
        duration_ms = (time.perf_counter() - start_time) * 1000

        # Add correlation ID to response
        response.headers["X-Correlation-ID"] = correlation_id

        user = getattr(request.state, "audit_user", None)

        # Log request (skip health checks and static files)
        if not path.startswith(("/health", "/static", "/favicon")):
            log_request(
                method=method,
                path=path,
                status_code=response.status_code,
                duration_ms=duration_ms,
                user=user,
            )

        if audit and _audit_enabled(request):
            body = clean_body(raw_body, content_type, content_length if raw_body is None else None, request.url.query)
            ids = ids_from(path, body)
            extra = getattr(request.state, "audit_extra", None) or {}
            ids.update({k: v for k, v in extra.items() if v is not None})
            await write_event(
                request.app.dependency_overrides.get(get_db, get_db),
                {
                    "at": datetime.utcnow(),
                    "user_id": user[0] if user else None,
                    "user_name": user[1] if user else None,
                    "method": method,
                    "path": path[:500],
                    "status": response.status_code,
                    "duration_ms": int(duration_ms),
                    "action": (getattr(request.state, "audit_action", None) or describe(method, path, request.url.query))[:200],
                    "body": body,
                    "correlation_id": correlation_id,
                    **ids,
                },
            )

        return response


def _audit_enabled(request: Request) -> bool:
    """В тестах журнал в базу выключен: запись идёт в общую тестовую сессию и
    гасила бы объекты теста. Тесты журнала включают его сами."""
    if os.environ.get("TESTING") == "1":
        return bool(getattr(request.app.state, "audit_in_tests", False))
    return True
