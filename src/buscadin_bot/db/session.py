"""Async SQLAlchemy engine and session factory helpers."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from buscadin_bot.config import Settings, get_settings
from buscadin_bot.db.models import Base


def create_engine(settings: Settings | None = None) -> AsyncEngine:
    settings = settings or get_settings()
    settings.ensure_sqlite_directory()
    return create_async_engine(settings.database_url, future=True, pool_pre_ping=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


async def init_db(engine: AsyncEngine) -> None:
    """Create all tables for tests and local bootstrap.

    Production deployments should use ``alembic upgrade head`` so schema changes remain explicit.
    """

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def close_engine(engine: AsyncEngine) -> None:
    await engine.dispose()


async def session_scope(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Yield one transactional session for small scripts and CLI commands."""

    factory = create_session_factory(engine)
    async with factory() as session:
        yield session
