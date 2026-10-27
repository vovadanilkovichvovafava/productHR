"""
Singleton HTTP client for external API calls.

This module provides a shared httpx.AsyncClient instance to:
- Reuse TCP connections (HTTP keep-alive)
- Reduce connection establishment overhead
- Manage connection pooling efficiently

Usage:
    from api.utils.http_client import get_http_client

    async def my_function():
        client = get_http_client()
        response = await client.get("https://api.example.com")
"""

import httpx
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Global singleton client
_http_client: Optional[httpx.AsyncClient] = None


def get_http_client() -> httpx.AsyncClient:
    """
    Get or create the singleton HTTP client.

    Returns:
        httpx.AsyncClient: Shared HTTP client instance

    Configuration:
        - timeout: 30s total, 10s for connect
        - max_connections: 100 total
        - max_keepalive: 20 persistent connections
        - follow_redirects: True for convenience
    """
    global _http_client

    if _http_client is None:
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
            limits=httpx.Limits(
                max_connections=100,
                max_keepalive_connections=20,
                keepalive_expiry=30.0,  # Close idle connections after 30s
            ),
            follow_redirects=True,
            http2=True,  # Enable HTTP/2 for better performance
        )
        logger.info("HTTP client initialized with connection pooling")

    return _http_client


async def close_http_client() -> None:
    """
    Close the HTTP client and release resources.

    Call this during application shutdown (e.g., in FastAPI lifespan).
    """
    global _http_client

    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None
        logger.info("HTTP client closed")
