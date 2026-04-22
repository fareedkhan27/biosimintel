from __future__ import annotations

from app.core.config import Settings
from app.core.exceptions import (
    AIClientException,
    BiosimError,
    IngestionException,
    NotFoundException,
    ValidationException,
)
from app.core.logging import configure_logging, get_logger


def test_configure_logging() -> None:
    configure_logging()


def test_get_logger() -> None:
    logger = get_logger("test")
    assert logger is not None


def test_settings_defaults() -> None:
    settings = Settings()
    assert settings.APP_ENV == "dev"
    assert settings.DEBUG is False


def test_biosim_error() -> None:
    exc = BiosimError("test")
    assert str(exc) == "test"


def test_not_found_exception() -> None:
    exc = NotFoundException("Molecule")
    assert "Molecule not found" in str(exc)


def test_validation_exception() -> None:
    exc = ValidationException("bad input")
    assert "bad input" in str(exc)


def test_ingestion_exception() -> None:
    exc = IngestionException("ingest failed")
    assert "ingest failed" in str(exc)


def test_ai_client_exception() -> None:
    exc = AIClientException("ai failed")
    assert "ai failed" in str(exc)
