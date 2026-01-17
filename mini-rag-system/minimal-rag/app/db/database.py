"""
Database connection and session management for PostgreSQL with pgvector
"""

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    create_async_engine,
    async_sessionmaker
)
from sqlalchemy.orm import DeclarativeBase
import logging

load_dotenv()
logger = logging.getLogger(__name__)

# Database Configuration
DATABASE_URL = (
    f"postgresql+asyncpg://"
    f"{os.getenv('POSTGRES_USER')}:"
    f"{os.getenv('POSTGRES_PASSWORD')}@"
    f"{os.getenv('POSTGRES_HOST')}:"
    f"{os.getenv('POSTGRES_PORT')}/"
    f"{os.getenv('POSTGRES_DB')}"
)


class Base(DeclarativeBase):
    """Modern Base class for SQLAlchemy 2.0 models"""
    pass


class DatabaseManager:
    """Manages database connections and sessions"""

    def __init__(self, url: str = DATABASE_URL):
        """
        Initialize database manager

        Args:
            url: Database connection URL
        """
        self.url = url
        self.engine: AsyncEngine = None
        self.session_factory: async_sessionmaker = None

    def initialize(self):
        """Initialize database engine and session factory"""
        if self.engine is not None:
            return

        # Create async engine
        self.engine = create_async_engine(
            self.url,
            echo=False,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10
        )

        # Create session factory
        self.session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False
        )

    async def close(self):
        """Close database connections"""
        if self.engine:
            await self.engine.dispose()
            self.engine = None
            self.session_factory = None

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Context manager for database sessions

        Usage:
            async with db_manager.session() as session:
                result = await session.execute(query)
        """
        if self.session_factory is None:
            self.initialize()

        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    async def create_tables(self):
        """Create all tables (for development/testing)"""
        if self.engine is None:
            self.initialize()

        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def drop_tables(self):
        """Drop all tables (for development/testing)"""
        if self.engine is None:
            self.initialize()

        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)


# Global database manager instance
db_manager = DatabaseManager()


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency function for FastAPI endpoints

    Usage:
        @app.get("/documents")
        async def get_documents(session: AsyncSession = Depends(get_session)):
            result = await session.execute(select(Document))
            return result.scalars().all()
    """
    async with db_manager.session() as session:
        yield session


async def startup_database():
    """Initialize database on application startup"""
    logger.info("Connecting to PostgreSQL...")
    db_manager.initialize()
    logger.info("Database connected!")


async def shutdown_database():
    """Close database connections on application shutdown"""
    logger.info("Closing database connections...")
    await db_manager.close()
    logger.info("Database connections closed!")
