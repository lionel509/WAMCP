import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

logger = logging.getLogger(__name__)

engine = create_async_engine(settings.DATABASE_URL, echo=False, future=True, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

audit_engine = None
AuditSessionLocal: Optional[async_sessionmaker[AsyncSession]] = None

if settings.audit_database_url:
    audit_engine = create_async_engine(settings.audit_database_url, echo=False, future=True, pool_pre_ping=True)
    AuditSessionLocal = async_sessionmaker(audit_engine, expire_on_commit=False)


async def get_db(read_only: Optional[bool] = None) -> AsyncIterator[AsyncSession]:
    """
    Yield a DB session. In plugin mode, sessions are set to read-only.
    """
    readonly = settings.plugin_mode if read_only is None else read_only
    async with AsyncSessionLocal() as session:
        if readonly:
            try:
                await session.execute(text("SET default_transaction_read_only = on"))
            except Exception:
                logger.warning("Failed to set session read-only mode", exc_info=True)
        try:
            yield session
        finally:
            await session.close()


@asynccontextmanager
async def get_audit_db() -> AsyncIterator[Optional[AsyncSession]]:
    """
    Yield an audit DB session if configured; otherwise yield None.
    """
    if not AuditSessionLocal:
        yield None
        return

    async with AuditSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
