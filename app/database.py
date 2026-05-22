from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    pass


def _build_engine() -> AsyncEngine:
    url = settings.DATABASE_URL
    # Strip query params that asyncpg doesn't understand (sslmode, channel_binding)
    # and re-add SSL via connect_args instead.
    needs_ssl = "neon.tech" in url or "sslmode" in url
    clean_url = url.split("?")[0]

    connect_args = {}
    if needs_ssl:
        import ssl as _ssl
        ctx = _ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = _ssl.CERT_NONE
        connect_args["ssl"] = ctx

    return create_async_engine(
        clean_url,
        echo=settings.DEBUG,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=1800,
        connect_args=connect_args,
    )


engine: AsyncEngine = _build_engine()

AsyncSessionFactory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def create_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
