from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import DATABASE_URL
from app.models import Base

engine = create_async_engine(DATABASE_URL, echo=False, future=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


async def init_models() -> None:
    """Crea las tablas si no existen. Sirve para desarrollo/demo rápido;
    en producción esto se reemplaza por migraciones de Alembic
    (`alembic upgrade head`), pero dejarlo aquí hace que `docker compose up`
    funcione de punta a punta sin pasos manuales adicionales."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
