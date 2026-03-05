import os
from dataclasses import dataclass
from typing import AsyncIterator, Optional

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


@dataclass(frozen=True)
class DbSettings:
    """Database settings for the API."""

    database_url: str


def _sync_to_async_pg_url(url: str) -> str:
    """
    Convert a sync postgres URL to an asyncpg SQLAlchemy URL if needed.

    Accepts:
    - postgresql://user:pass@host:port/db
    - postgres://user:pass@host:port/db

    Returns:
    - postgresql+asyncpg://user:pass@host:port/db
    """
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


def _build_database_url_from_parts() -> Optional[str]:
    """
    Build a postgres URL from provided env vars, if present.

    The database container advertises these possible env vars:
    POSTGRES_URL, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB, POSTGRES_PORT

    We prefer POSTGRES_URL if available; otherwise construct from parts.
    """
    pg_url = os.getenv("POSTGRES_URL")
    if pg_url:
        return pg_url

    user = os.getenv("POSTGRES_USER")
    password = os.getenv("POSTGRES_PASSWORD")
    db = os.getenv("POSTGRES_DB")
    port = os.getenv("POSTGRES_PORT")
    host = os.getenv("POSTGRES_HOST") or "localhost"

    if user and password and db and port:
        return f"postgresql://{user}:{password}@{host}:{port}/{db}"
    return None


# PUBLIC_INTERFACE
def get_db_settings() -> DbSettings:
    """Resolve database settings from environment variables with sane fallbacks."""
    # Preferred path: DB env vars provided by orchestration
    built = _build_database_url_from_parts()
    if built:
        return DbSettings(database_url=_sync_to_async_pg_url(built))

    # Fallback for this repo’s local Postgres container (db_connection.txt shows port 5000)
    # NOTE: keep as fallback only; do not assume in production.
    fallback = "postgresql://appuser:dbuser123@localhost:5000/myapp"
    return DbSettings(database_url=_sync_to_async_pg_url(fallback))


_engine: Optional[AsyncEngine] = None
_sessionmaker: Optional[async_sessionmaker[AsyncSession]] = None


# PUBLIC_INTERFACE
def get_engine() -> AsyncEngine:
    """Get (and lazily initialize) the global SQLAlchemy async engine."""
    global _engine, _sessionmaker
    if _engine is None:
        settings = get_db_settings()
        _engine = create_async_engine(
            settings.database_url,
            pool_pre_ping=True,
        )
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


# PUBLIC_INTERFACE
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Get the global async sessionmaker (initializing the engine if needed)."""
    if _sessionmaker is None:
        get_engine()
        assert _sessionmaker is not None
    return _sessionmaker


# PUBLIC_INTERFACE
async def get_db_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields an AsyncSession."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        yield session
