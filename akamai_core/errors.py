class PapiRequestError(RuntimeError):
    """Raised when a PAPI call fails at the transport level (timeout, network error)."""
