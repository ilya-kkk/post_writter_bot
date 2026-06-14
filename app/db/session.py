from collections.abc import AsyncIterator

from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings


LOCAL_DATABASE_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0", "db", "postgres"}


def make_async_database_url(database_url: str) -> URL:
    if not database_url.strip():
        raise RuntimeError("DATABASE_URL must be set to a Supabase Postgres connection string.")

    url = make_url(database_url)
    if _is_local_database_url(url):
        raise RuntimeError("Local PostgreSQL URLs are disabled. Set DATABASE_URL to your Supabase Postgres URL.")
    if not _is_supabase_database_url(url):
        raise RuntimeError("DATABASE_URL must point to a Supabase Postgres host.")

    if url.drivername in {"postgres", "postgresql"}:
        url = url.set(drivername="postgresql+asyncpg")

    query = dict(url.query)
    sslmode = query.pop("sslmode", None)
    if sslmode and url.drivername.endswith("+asyncpg"):
        query.setdefault("ssl", sslmode)

    if _is_supabase_transaction_pooler(url):
        query.setdefault("prepared_statement_cache_size", "0")

    return url.set(query=query)


def _is_local_database_url(url: URL) -> bool:
    host = (url.host or "").lower()
    return host in LOCAL_DATABASE_HOSTS


def _is_supabase_database_url(url: URL) -> bool:
    host = (url.host or "").lower()
    return host.endswith(".supabase.com") or host.endswith(".supabase.co") or host in {"supabase.com", "supabase.co"}


def _is_supabase_transaction_pooler(url: URL) -> bool:
    host = url.host or ""
    return _is_supabase_database_url(url) and url.port == 6543


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
