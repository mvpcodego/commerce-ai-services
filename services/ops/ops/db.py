from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from ops import config


def make_engine(url: str | None = None) -> AsyncEngine:
    # pool_pre_ping: пулер Supabase рвёт простаивающие соединения.
    return create_async_engine(url or config.DATABASE_URL, pool_size=5, pool_pre_ping=True)


def make_sessionmaker(engine: AsyncEngine) -> async_sessionmaker:
    return async_sessionmaker(engine, expire_on_commit=False)
