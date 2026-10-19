from collections.abc import AsyncIterator

import pytest_asyncio
from sqlalchemy import StaticPool
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.infrastructure.database import create_tables


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    await create_tables(engine)
    async with AsyncSession(engine, expire_on_commit=False) as db_session:
        yield db_session
    await engine.dispose()
