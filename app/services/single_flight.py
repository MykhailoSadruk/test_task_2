import asyncio
import logging

from app.services.interfaces import Transformer

logger = logging.getLogger(__name__)


class SingleFlightTransformer(Transformer):
    def __init__(self, transformer: Transformer) -> None:
        self._transformer = transformer
        self._in_flight: dict[str, asyncio.Future[str]] = {}

    async def transform(self, text: str) -> str:
        # The same text requested by several requests at once is transformed by
        # one call; the others wait for its result. Shield keeps a cancelled
        # waiter from cancelling the call that the other waiters depend on.
        shared = self._in_flight.get(text)
        if shared is not None:
            logger.debug("Joining the running call for %r", text)
            return await asyncio.shield(shared)
        shared = asyncio.get_running_loop().create_future()
        self._in_flight[text] = shared
        try:
            result = await self._transformer.transform(text)
        except BaseException as error:
            # A cancelled call is reported to waiters as a plain failure so that
            # their retry makes a fresh call instead of inheriting the cancel.
            shared.set_exception(
                error if isinstance(error, Exception) else RuntimeError("cancelled")
            )
            shared.exception()
            raise
        else:
            shared.set_result(result)
            return result
        finally:
            del self._in_flight[text]
