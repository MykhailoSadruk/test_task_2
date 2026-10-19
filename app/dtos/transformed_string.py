from dataclasses import dataclass


@dataclass(frozen=True)
class TransformedStringDto:
    original: str
    transformed: str
