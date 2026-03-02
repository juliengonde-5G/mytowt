from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db():
    """Dependency: yields an async database session."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Create all tables (skip if they already exist)."""
    from sqlalchemy import inspect

    async with engine.begin() as conn:
        def _create_tables(sync_conn):
            inspector = inspect(sync_conn)
            existing = set(inspector.get_table_names())
            # Only create tables that don't exist yet
            tables_to_create = [
                t for t in Base.metadata.sorted_tables
                if t.name not in existing
            ]
            if tables_to_create:
                Base.metadata.create_all(sync_conn, tables=tables_to_create)

        await conn.run_sync(_create_tables)
