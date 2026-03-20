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
    """Create all tables and run lightweight migrations."""
    from sqlalchemy import text
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # ── Lightweight column migrations (idempotent) ──
        migrations = [
            ("rate_grids", "palette_format", "VARCHAR(20) DEFAULT 'EPAL'"),
            # Order columns that may have been added after initial table creation
            ("orders", "preferred_holds", "VARCHAR(100)"),
            ("orders", "booking_fee", "FLOAT DEFAULT 0"),
            ("orders", "documentation_fee", "FLOAT DEFAULT 0"),
            ("orders", "delivery_date_start", "DATE"),
            ("orders", "delivery_date_end", "DATE"),
            ("orders", "departure_locode", "VARCHAR(5)"),
            ("orders", "arrival_locode", "VARCHAR(5)"),
            ("orders", "attachment_filename", "VARCHAR(255)"),
            ("orders", "attachment_path", "VARCHAR(500)"),
            ("orders", "pipedrive_deal_id", "INTEGER"),
            ("orders", "rate_grid_id", "INTEGER REFERENCES rate_grids(id)"),
            ("orders", "rate_grid_line_id", "INTEGER REFERENCES rate_grid_lines(id)"),
        ]
        for table, column, col_type in migrations:
            await conn.execute(text(
                f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {col_type}"
            ))
