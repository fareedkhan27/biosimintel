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


def format_datetime(value: datetime | str | None) -> str:
    """Format datetime or ISO string to human-readable: 'Apr 22, 2026, 6:31 PM'."""
    if value is None:
        return "N/A"
    if isinstance(value, str):
        value = parse_iso_date(value)
    if value is None:
        return "N/A"
    hour_12 = value.hour % 12 or 12
    return f"{value.strftime('%b')} {value.day}, {value.year}, {hour_12}:{value.minute:02d} {value.strftime('%p')}"


def utc_now_sqlalchemy() -> datetime:
    """Return current UTC datetime for SQLAlchemy defaults."""
    return datetime.now(UTC)
