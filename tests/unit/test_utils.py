from __future__ import annotations

from app.utils.dates import parse_iso_date, utc_now
from app.utils.hashing import compute_sha256
from app.utils.text import normalize_whitespace, truncate
from app.utils.validators import is_valid_uuid


def test_compute_sha256() -> None:
    result = compute_sha256("hello")
    assert len(result) == 64
    assert result == compute_sha256("hello")


def test_utc_now() -> None:
    now = utc_now()
    assert now.tzinfo is not None


def test_parse_iso_date() -> None:
    result = parse_iso_date("2025-01-01T00:00:00Z")
    assert result is not None
    assert result.year == 2025
    assert parse_iso_date(None) is None


def test_truncate() -> None:
    assert truncate("hello world", 5) == "he..."
    assert truncate("hi", 5) == "hi"


def test_normalize_whitespace() -> None:
    assert normalize_whitespace("  a   b  ") == "a b"


def test_is_valid_uuid() -> None:
    assert is_valid_uuid("550e8400-e29b-41d4-a716-446655440000") is True
    assert is_valid_uuid("not-a-uuid") is False
