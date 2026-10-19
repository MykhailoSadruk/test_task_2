class PayloadNotFoundError(Exception):
    pass


class TransformerError(Exception):
    pass


class DatabaseUnavailableError(Exception):
    pass


class PayloadTooLargeError(Exception):
    pass
