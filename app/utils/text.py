from __future__ import annotations


def truncate(text: str, length: int = 200) -> str:
    """Truncate text to specified length with ellipsis."""
    if len(text) <= length:
        return text
    return text[: length - 3] + "..."


def normalize_whitespace(text: str) -> str:
    """Collapse multiple whitespace characters into single spaces."""
    return " ".join(text.split())
