from dataclasses import dataclass


@dataclass(frozen=True)
class PayloadCreationDto:
    id: str
    created: bool
