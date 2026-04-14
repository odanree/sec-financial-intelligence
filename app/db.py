from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.models.filing import Base

async_engine = None
AsyncSessionLocal: async_sessionmaker[AsyncSession] | None = None


async def init_db() -> None:
    global async_engine, AsyncSessionLocal
    async_engine = create_async_engine(
        get_settings().database_url,
        echo=False,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )
    AsyncSessionLocal = async_sessionmaker(async_engine, expire_on_commit=False)
    import app.models.filing  # noqa: F401 — register models with metadata
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    if AsyncSessionLocal is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    async with AsyncSessionLocal() as session:
        yield session
