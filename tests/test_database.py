from pathlib import Path

from app.infrastructure.database import BUSY_TIMEOUT_SECONDS, create_database_engine


async def test_file_database_uses_wal_and_busy_timeout(tmp_path: Path) -> None:
    engine = create_database_engine(f"sqlite+aiosqlite:///{tmp_path / 'wal.db'}")

    async with engine.connect() as connection:
        journal = await connection.exec_driver_sql("PRAGMA journal_mode")
        timeout = await connection.exec_driver_sql("PRAGMA busy_timeout")
        journal_mode = journal.scalar()
        busy_timeout = timeout.scalar()
    await engine.dispose()

    assert journal_mode == "wal"
    assert busy_timeout == BUSY_TIMEOUT_SECONDS * 1000
