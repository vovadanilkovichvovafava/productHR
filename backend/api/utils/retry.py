"""
Retry utilities for external API calls.

This module provides decorators and utilities for retrying failed API calls
with exponential backoff. Uses tenacity library for robust retry logic.
"""

import logging
from functools import wraps
from typing import Callable, TypeVar, Any
import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
    RetryError,
)

logger = logging.getLogger(__name__)

# Type variable for generic return type
T = TypeVar('T')

# Common retriable exceptions for HTTP calls
RETRIABLE_EXCEPTIONS = (
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.ReadError,
    httpx.WriteError,
    httpx.PoolTimeout,
    ConnectionError,
    TimeoutError,
)


def with_retry(
    max_attempts: int = 3,
    min_wait: float = 1,
    max_wait: float = 10,
    retriable_exceptions: tuple = RETRIABLE_EXCEPTIONS,
) -> Callable:
    """
    Decorator for retrying async functions with exponential backoff.
    
    Args:
        max_attempts: Maximum number of retry attempts (default: 3)
        min_wait: Minimum wait time between retries in seconds (default: 1)
        max_wait: Maximum wait time between retries in seconds (default: 10)
        retriable_exceptions: Tuple of exception types to retry on
    
    Usage:
        @with_retry(max_attempts=3)
        async def call_external_api():
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        @retry(
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
            retry=retry_if_exception_type(retriable_exceptions),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            return await func(*args, **kwargs)
        return wrapper
    return decorator


def retry_on_rate_limit(
    max_attempts: int = 5,
    min_wait: float = 2,
    max_wait: float = 60,
) -> Callable:
    """
    Decorator specifically for handling rate limit (429) errors.
    Uses longer backoff times suitable for rate limiting.
    
    Args:
        max_attempts: Maximum number of retry attempts (default: 5)
        min_wait: Minimum wait time between retries in seconds (default: 2)
        max_wait: Maximum wait time between retries in seconds (default: 60)
    """
    def is_rate_limit_error(exception: BaseException) -> bool:
        """Check if exception is a rate limit error."""
        if isinstance(exception, httpx.HTTPStatusError):
            return exception.response.status_code == 429
        return False
    
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        @retry(
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=2, min=min_wait, max=max_wait),
            retry=retry_if_exception_type(RETRIABLE_EXCEPTIONS) | retry_if_exception_type((httpx.HTTPStatusError,)),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            return await func(*args, **kwargs)
        return wrapper
    return decorator


class RetryableHTTPClient:
    """
    A wrapper around httpx.AsyncClient with built-in retry logic.
    
    Usage:
        async with RetryableHTTPClient() as client:
            response = await client.get("https://api.example.com")
    """
    
    def __init__(
        self,
        max_attempts: int = 3,
        min_wait: float = 1,
        max_wait: float = 10,
        **httpx_kwargs: Any,
    ):
        self.max_attempts = max_attempts
        self.min_wait = min_wait
        self.max_wait = max_wait
        self.httpx_kwargs = httpx_kwargs
        self._client: httpx.AsyncClient | None = None
    
    async def __aenter__(self) -> 'RetryableHTTPClient':
        self._client = httpx.AsyncClient(**self.httpx_kwargs)
        return self
    
    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._client:
            await self._client.aclose()
    
    @with_retry()
    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        """GET request with retry."""
        if not self._client:
            raise RuntimeError("Client not initialized. Use async with.")
        response = await self._client.get(url, **kwargs)
        response.raise_for_status()
        return response
    
    @with_retry()
    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        """POST request with retry."""
        if not self._client:
            raise RuntimeError("Client not initialized. Use async with.")
        response = await self._client.post(url, **kwargs)
        response.raise_for_status()
        return response
    
    @with_retry()
    async def put(self, url: str, **kwargs: Any) -> httpx.Response:
        """PUT request with retry."""
        if not self._client:
            raise RuntimeError("Client not initialized. Use async with.")
        response = await self._client.put(url, **kwargs)
        response.raise_for_status()
        return response
    
    @with_retry()
    async def delete(self, url: str, **kwargs: Any) -> httpx.Response:
        """DELETE request with retry."""
        if not self._client:
            raise RuntimeError("Client not initialized. Use async with.")
        response = await self._client.delete(url, **kwargs)
        response.raise_for_status()
        return response
