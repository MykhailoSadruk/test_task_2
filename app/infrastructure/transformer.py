from app.services.interfaces import Transformer


class UppercaseTransformer(Transformer):
    """Stand-in for the external transformation service."""

    async def transform(self, text: str) -> str:
        return text.upper()
