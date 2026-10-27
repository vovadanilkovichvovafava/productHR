"""
Database URL utility for consistent URL formatting across the application.

Handles conversion from various PostgreSQL URL formats to asyncpg format:
- postgres:// -> postgresql+asyncpg://  (old Heroku/Railway format)
- postgresql:// -> postgresql+asyncpg://
"""

import os


def get_database_url() -> str:
    """
    Get database URL from environment and convert to asyncpg format.

    Railway and Heroku sometimes provide postgres:// (deprecated format).
    SQLAlchemy asyncpg driver requires postgresql+asyncpg:// format.

    Returns:
        Database URL in postgresql+asyncpg:// format ready for async SQLAlchemy.

    Raises:
        ValueError: If DATABASE_URL environment variable is not set.
    """
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise ValueError("DATABASE_URL environment variable is not set")

    # Convert to asyncpg format
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    return database_url


def get_sync_database_url() -> str:
    """
    Get database URL from environment in standard postgresql:// format.

    Used for synchronous drivers like psycopg2 that don't need asyncpg.

    Returns:
        Database URL in postgresql:// format.

    Raises:
        ValueError: If DATABASE_URL environment variable is not set.
    """
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise ValueError("DATABASE_URL environment variable is not set")

    # Normalize to standard postgresql:// format
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    elif database_url.startswith("postgresql+asyncpg://"):
        database_url = database_url.replace("postgresql+asyncpg://", "postgresql://", 1)

    return database_url
