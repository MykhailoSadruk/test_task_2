from sqlalchemy import event
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import ConnectionPoolEntry

from app.infrastructure.models import Base

BUSY_TIMEOUT_SECONDS = 30


def enable_wal(dbapi_connection: DBAPIConnection, _: ConnectionPoolEntry) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


def create_database_engine(database_url: str) -> AsyncEngine:
    # SQLite allows one writer at a time. WAL lets readers continue during a
    # write, and the busy timeout makes a blocked writer wait for the lock
    # instead of failing at once with "database is locked".
    engine = create_async_engine(
        database_url, connect_args={"timeout": BUSY_TIMEOUT_SECONDS}
    )
    event.listen(engine.sync_engine, "connect", enable_wal)
    return engine


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def create_tables(bind: AsyncEngine) -> None:
    async with bind.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
