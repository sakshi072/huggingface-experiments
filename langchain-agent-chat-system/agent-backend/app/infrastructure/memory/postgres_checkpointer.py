import logging
from typing import Optional
logger = logging.getLogger(__name__)
from psycopg_pool import AsyncConnectionPool
from app.core.settings import settings
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

__pool: Optional[AsyncConnectionPool] = None
_checkpointer: Optional[AsyncPostgresSaver] = None

async def init_checkpointer() -> AsyncPostgresSaver:
    """
    Initialize Postgres connection pool and checkpointer
    Call once at app start
    """
    global _checkpointer, __pool

    _pool = AsyncConnectionPool(
        conninfo=settings.POSTGRES_URI,
        max_size=10,
        min_size=2,
        kwargs={"autocommit": True}
    )

    await _pool.open()
    _checkpointer = AsyncPostgresSaver(conn=_pool)
    await _checkpointer.setup()
    logger.info("Postgres Checkpointer initialized and table created")
    return _checkpointer

def get_checkpointer() -> AsyncPostgresSaver:
    if _checkpointer is None:
        raise RuntimeError("Checkpointer not initialized - call init_checkpointer() at startup")
    return _checkpointer

async def close_checkpointer():
    global _pool
    if _pool:
        await _pool.close()
        logger.info("Postgres connection pool closed")