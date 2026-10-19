from collections.abc import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from app.config import Settings
from app.infrastructure.models import Base


def create_db_engine(database_url: str) -> Engine:
    connect_args = {"check_same_thread": False}
    if not database_url.startswith("sqlite"):
        connect_args = {}
    return create_engine(database_url, connect_args=connect_args)


engine = create_db_engine(Settings().database_url)


def create_tables(bind: Engine = engine) -> None:
    Base.metadata.create_all(bind)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
