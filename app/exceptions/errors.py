class PayloadNotFoundError(Exception):
    def __init__(self, payload_id: str) -> None:
        super().__init__(payload_id)
        self.payload_id = payload_id


class TransformerError(Exception):
    pass


class DatabaseUnavailableError(Exception):
    pass


class PayloadTooLargeError(Exception):
    pass
