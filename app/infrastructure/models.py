from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TransformedString(Base):
    __tablename__ = "transformed_strings"

    original: Mapped[str] = mapped_column(primary_key=True)
    transformed: Mapped[str]


class Payload(Base):
    __tablename__ = "payloads"

    id: Mapped[str] = mapped_column(primary_key=True)
    output: Mapped[str]
