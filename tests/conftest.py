from collections.abc import Iterator

import pytest
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import Session

from app.infrastructure.database import create_tables


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    create_tables(engine)
    with Session(engine) as db_session:
        yield db_session
