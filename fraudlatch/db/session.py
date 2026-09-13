"""Async SQLAlchemy engine and session factory."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from fraudlatch.db.config import get_database_url


def create_session_factory() -> async_sessionmaker[AsyncSession]:
    """Create an async session factory from the current environment."""

    engine = create_async_engine(get_database_url(), pool_pre_ping=True)
    return async_sessionmaker(engine, expire_on_commit=False)


async def session_scope() -> AsyncIterator[AsyncSession]:
    """Yield a session and roll back if its caller raises."""

    session_factory = create_session_factory()
    async with session_factory() as session:
        try:
            yield session
        except BaseException:
            await session.rollback()
            raise
