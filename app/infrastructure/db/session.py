"""Async SQLAlchemy engine, session factory, and FastAPI session dependency."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

engine: AsyncEngine = create_async_engine(
    settings.sqlalchemy_url,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)

# expire_on_commit=False so ORM objects stay usable (for response
# serialization) after the request-scoped commit.
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding one AsyncSession per request.

    Commits on success, rolls back on any exception, always closes.
    Services may flush freely; the transaction boundary is the request.
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise
