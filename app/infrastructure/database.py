from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)

from app.config import Settings
from app.infrastructure.models import Base

engine = create_async_engine(Settings().database_url)
session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def create_tables(bind: AsyncEngine = engine) -> None:
    async with bind.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
