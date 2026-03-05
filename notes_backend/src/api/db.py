import os
from dataclasses import dataclass
from typing import AsyncIterator, Optional
from urllib.parse import urlparse

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


def _postgres_url_needs_credentials(url: str) -> bool:
    """
    Return True if the URL is a postgres URL that lacks username/password.

    Some orchestrators provide `POSTGRES_URL=postgresql://host:port/db` and separate
    `POSTGRES_USER` / `POSTGRES_PASSWORD`. SQLAlchemy/asyncpg still need credentials
    in the URL, so we splice them in when missing.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False

    if parsed.scheme not in {"postgresql", "postgres", "postgresql+asyncpg"}:
        return False

    # urlparse sets username/password based on netloc userinfo
    return (parsed.username is None) and (parsed.password is None)


def _inject_credentials_into_postgres_url(url: str, user: str, password: str) -> str:
    """Inject user/password into a postgres URL that currently has none."""
    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port
    path = parsed.path or ""
    scheme = parsed.scheme

    # Preserve query/fragment if present.
    query = f"?{parsed.query}" if parsed.query else ""
    fragment = f"#{parsed.fragment}" if parsed.fragment else ""

    port_part = f":{port}" if port else ""
    # Keep the path as-is (should include leading slash + db name).
    return f"{scheme}://{user}:{password}@{host}{port_part}{path}{query}{fragment}"


def _build_database_url_from_parts() -> Optional[str]:
    """
    Build a postgres URL from provided env vars, if present.

    The database container advertises these env vars:
    - POSTGRES_URL
    - POSTGRES_USER
    - POSTGRES_PASSWORD
    - POSTGRES_DB
    - POSTGRES_PORT

    Resolution:
    1) If POSTGRES_URL is set, use it. If it lacks credentials but POSTGRES_USER/PASSWORD
       exist, inject them into the URL.
    2) Otherwise construct a URL from parts if user/password/db/port exist.
    """
    pg_url = os.getenv("POSTGRES_URL")
    if pg_url:
        user = os.getenv("POSTGRES_USER")
        password = os.getenv("POSTGRES_PASSWORD")
        if user and password and _postgres_url_needs_credentials(pg_url):
            pg_url = _inject_credentials_into_postgres_url(pg_url, user=user, password=password)
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
