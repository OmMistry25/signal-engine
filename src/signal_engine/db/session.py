from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from signal_engine.config import get_settings


def _async_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def make_engine() -> AsyncEngine:
    return create_async_engine(_async_url(get_settings().database_url), pool_pre_ping=True)


engine: AsyncEngine = make_engine()
async_session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
