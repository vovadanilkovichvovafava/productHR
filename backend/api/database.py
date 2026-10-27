from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from .models.database import Base
from .utils.db_url import get_database_url


database_url = get_database_url()

# Determine if we're using PostgreSQL (supports connection pooling) or SQLite (tests)
is_postgresql = database_url.startswith("postgresql")

# Connection pool configuration for production workloads (PostgreSQL only)
# SQLite doesn't support these parameters
if is_postgresql:
    engine = create_async_engine(
        database_url,
        echo=False,
        pool_pre_ping=True,      # Check connection health before use
        pool_size=20,            # Main pool size
        max_overflow=30,         # Extra connections during peak
        pool_recycle=3600,       # Recycle connections every hour
        pool_timeout=30,         # Wait up to 30s for available connection
    )
else:
    # SQLite for testing - no pool configuration needed
    engine = create_async_engine(
        database_url,
        echo=False,
    )

AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
