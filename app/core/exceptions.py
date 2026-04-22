from __future__ import annotations


class BiosimError(Exception):
    """Base exception for Biosim."""

    def __init__(self, message: str = "Biosim error") -> None:
        self.message = message
        super().__init__(self.message)


class NotFoundException(BiosimError):
    """Resource not found."""

    def __init__(self, resource: str = "Resource") -> None:
        super().__init__(f"{resource} not found")


class ValidationException(BiosimError):
    """Validation error."""

    def __init__(self, message: str = "Validation error") -> None:
        super().__init__(message)


class IngestionException(BiosimError):
    """Ingestion pipeline error."""

    def __init__(self, message: str = "Ingestion failed") -> None:
        super().__init__(message)


class AIClientException(BiosimError):
    """AI client error."""

    def __init__(self, message: str = "AI client error") -> None:
        super().__init__(message)
