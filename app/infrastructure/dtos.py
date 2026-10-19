from dataclasses import dataclass


@dataclass(frozen=True)
class PayloadDto:
    id: str
    output: str


@dataclass(frozen=True)
class TransformedStringDto:
    original: str
    transformed: str
