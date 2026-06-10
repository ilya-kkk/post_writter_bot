from collections.abc import AsyncIterator

from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings


def make_async_database_url(database_url: str) -> URL:
    url = make_url(database_url)
    if url.drivername in {"postgres", "postgresql"}:
        url = url.set(drivername="postgresql+asyncpg")

    query = dict(url.query)
    sslmode = query.pop("sslmode", None)
    if sslmode and url.drivername.endswith("+asyncpg"):
        query.setdefault("ssl", sslmode)

    if _is_supabase_transaction_pooler(url):
        query.setdefault("prepared_statement_cache_size", "0")

    return url.set(query=query)


def _is_supabase_transaction_pooler(url: URL) -> bool:
    host = url.host or ""
    return (host.endswith("supabase.com") or host.endswith("supabase.co")) and url.port == 6543


database_url = make_async_database_url(settings.database_url)
engine_kwargs: dict[str, object] = {"pool_pre_ping": True}
if _is_supabase_transaction_pooler(database_url):
    engine_kwargs["poolclass"] = NullPool
    engine_kwargs["connect_args"] = {"statement_cache_size": 0}

engine = create_async_engine(database_url, **engine_kwargs)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with async_session_factory() as session:
        yield session


def session_factory() -> async_sessionmaker[AsyncSession]:
    return async_session_factory
