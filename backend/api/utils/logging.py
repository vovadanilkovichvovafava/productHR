"""
Structured logging utilities for the HR-bot backend.

Provides JSON-formatted logs with correlation IDs for better observability.
"""

import logging
import json
import sys
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# Context variable for request correlation ID
correlation_id: ContextVar[Optional[str]] = ContextVar('correlation_id', default=None)


def get_correlation_id() -> str:
    """Get current correlation ID or generate a new one."""
    cid = correlation_id.get()
    if cid is None:
        cid = str(uuid.uuid4())[:8]
        correlation_id.set(cid)
    return cid


def set_correlation_id(cid: str) -> None:
    """Set correlation ID for current context."""
    correlation_id.set(cid)


class StructuredFormatter(logging.Formatter):
    """
    JSON formatter for structured logging.

    Output format:
    {
        "timestamp": "2024-01-22T12:00:00.000Z",
        "level": "INFO",
        "logger": "api.routes.auth",
        "message": "User logged in",
        "correlation_id": "abc12345",
        "extra": {...}
    }
    """

    def format(self, record: logging.LogRecord) -> str:
        log_data: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add correlation ID if available
        cid = correlation_id.get()
        if cid:
            log_data["correlation_id"] = cid

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields (excluding standard LogRecord attributes)
        standard_attrs = {
            'name', 'msg', 'args', 'created', 'filename', 'funcName',
            'levelname', 'levelno', 'lineno', 'module', 'msecs',
            'pathname', 'process', 'processName', 'relativeCreated',
            'stack_info', 'exc_info', 'exc_text', 'thread', 'threadName',
            'message', 'taskName'
        }
        extras = {
            k: v for k, v in record.__dict__.items()
            if k not in standard_attrs and not k.startswith('_')
        }
        if extras:
            log_data["extra"] = extras

        return json.dumps(log_data, default=str, ensure_ascii=False)


class PrettyFormatter(logging.Formatter):
    """
    Human-readable formatter for development.

    Output format:
    2024-01-22 12:00:00 [INFO] api.routes.auth: User logged in [abc12345]
    """

    COLORS = {
        'DEBUG': '\033[36m',     # Cyan
        'INFO': '\033[32m',      # Green
        'WARNING': '\033[33m',   # Yellow
        'ERROR': '\033[31m',     # Red
        'CRITICAL': '\033[35m',  # Magenta
    }
    RESET = '\033[0m'

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        color = self.COLORS.get(record.levelname, '')
        level = f"{color}[{record.levelname}]{self.RESET}" if color else f"[{record.levelname}]"

        cid = correlation_id.get()
        cid_part = f" [{cid}]" if cid else ""

        message = f"{timestamp} {level} {record.name}: {record.getMessage()}{cid_part}"

        if record.exc_info:
            message += '\n' + self.formatException(record.exc_info)

        return message


def setup_logging(
    level: str = "INFO",
    json_format: bool = True,
    log_file: Optional[str] = None
) -> None:
    """
    Configure logging for the application.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_format: Use JSON format (True for production, False for development)
        log_file: Optional file path to write logs to
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create formatter
    formatter = StructuredFormatter() if json_format else PrettyFormatter()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler (optional)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(StructuredFormatter())  # Always JSON for files
        root_logger.addHandler(file_handler)

    # Reduce noise from third-party libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger with the given name.

    Usage:
        logger = get_logger(__name__)
        logger.info("Processing request", extra={"user_id": 123})
    """
    return logging.getLogger(name)


class LogContext:
    """
    Context manager for adding extra fields to all logs within a block.

    Usage:
        with LogContext(user_id=123, org_id=456):
            logger.info("Processing...")  # Will include user_id and org_id
    """

    def __init__(self, **kwargs: Any):
        self.extra = kwargs
        self._old_factory: Any = None

    def __enter__(self) -> 'LogContext':
        self._old_factory = logging.getLogRecordFactory()

        extra = self.extra

        def factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
            record = self._old_factory(*args, **kwargs)
            for key, value in extra.items():
                setattr(record, key, value)
            return record

        logging.setLogRecordFactory(factory)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        logging.setLogRecordFactory(self._old_factory)


# Convenience functions
def log_request(method: str, path: str, status_code: int, duration_ms: float, user=None) -> None:
    """Log an HTTP request with standard fields.

    user — (id, имя) того, кто сделал запрос (21.10.2026): раньше в строке было
    только «POST /api/entities 201», и понять, кто это, было нельзя."""
    logger = get_logger("api.request")
    who = f" · {user[1]} ({user[0]})" if user else ""
    logger.info(
        f"{method} {path} {status_code}{who}",
        extra={
            "method": method,
            "path": path,
            "status_code": status_code,
            "duration_ms": round(duration_ms, 2),
            "user_id": user[0] if user else None,
        }
    )


def log_error(error: Exception, context: Optional[Dict[str, Any]] = None) -> None:
    """Log an error with context."""
    logger = get_logger("api.error")
    logger.error(
        str(error),
        exc_info=error,
        extra={"context": context} if context else {}
    )
