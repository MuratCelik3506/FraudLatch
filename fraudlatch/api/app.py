"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from fraudlatch.api.routes import router
from fraudlatch.db.config import get_database_url


def create_app(
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> FastAPI:
    """Build the API without creating tables or running migrations."""

    engine = None
    if session_factory is None:
        engine = create_async_engine(get_database_url(), pool_pre_ping=True)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        if engine is not None:
            await engine.dispose()

    app = FastAPI(title="FraudLatch API", version="0.1.0", lifespan=lifespan)
    app.state.session_factory = session_factory
    app.include_router(router)
    return app
