from dataclasses import dataclass


@dataclass(frozen=True)
class PayloadDto:
    id: str
    output: str
