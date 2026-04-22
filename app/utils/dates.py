from __future__ import annotations

from datetime import UTC, datetime


def utc_now() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(UTC)


def parse_iso_date(value: str | None) -> datetime | None:
    """Parse ISO date string to datetime."""
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def utc_now_sqlalchemy() -> datetime:
    """Return current UTC datetime for SQLAlchemy defaults."""
    return datetime.now(UTC)
