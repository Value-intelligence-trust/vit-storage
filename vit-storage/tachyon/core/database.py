import logging
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import sessionmaker
from tachyon.core.config import settings

logger = logging.getLogger(__name__)

# Resolve and standardise database URL
db_url = settings.DATABASE_URL
# Convert sqlite:// to sqlite+aiosqlite:// for async compatibility
if db_url.startswith("sqlite://") and not db_url.startswith("sqlite+aiosqlite://"):
    db_url = db_url.replace("sqlite://", "sqlite+aiosqlite://")

logger.info(f"Initializing async database engine with URL: {db_url}")

async_engine = create_async_engine(
    db_url,
    echo=False,
    pool_pre_ping=True
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False
)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency injection helper for FastAPI endpoints."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

async def init_db():
    """Create all standard schemas and tables if missing."""
    from tachyon.core.models import Base
    try:
        logger.info("Verifying database schema...")
        async with async_engine.begin() as conn:
            # Create tables
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database schema validated successfully.")
    except Exception as e:
        logger.critical(f"Database schema initialization failed: {e}")
        # In memory/dev sqlite fallback
        raise
