import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from typing import AsyncGenerator

DATABASE_URL = (
    f"postgresql+asyncpg://{os.getenv('POSTGRES_USER','learnova')}:{os.getenv('POSTGRES_PASSWORD','learnova')}@"
    f"{os.getenv('POSTGRES_HOST','postgres')}:{os.getenv('POSTGRES_PORT','5432')}/{os.getenv('POSTGRES_DB','learnova')}"
)

engine = create_async_engine(DATABASE_URL, echo=False, future=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)

class Base(DeclarativeBase):
    pass

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session

async def init_db():
    """Create tables (lightweight). In production prefer Alembic migrations."""
    from ..models.db_models import Base  # local import to avoid circular
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
