from abc import ABC, abstractmethod


class Transformer(ABC):
    @abstractmethod
    async def transform(self, text: str) -> str:
        """Return the transformed form of a single string."""
