from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services.engine.deduplication import DeduplicationEngine


@pytest.fixture
def mock_existing() -> list[MagicMock]:
    e1 = MagicMock()
    e1.external_id = "NCT001"
    e1.content_hash = "abc"
    e1.title = "Phase 3 study"
    e2 = MagicMock()
    e2.external_id = "NCT002"
    e2.content_hash = "def"
    e2.title = "Another study"
    return [e1, e2]


def test_duplicate_by_external_id(mock_existing: list[MagicMock]) -> None:
    engine = DeduplicationEngine()
    new = MagicMock()
    new.external_id = "NCT001"
    new.content_hash = "zzz"
    new.title = "Different title"
    assert engine.is_duplicate(new, mock_existing) is True


def test_duplicate_by_content_hash(mock_existing: list[MagicMock]) -> None:
    engine = DeduplicationEngine()
    new = MagicMock()
    new.external_id = "NCT999"
    new.content_hash = "abc"
    new.title = "Different title"
    assert engine.is_duplicate(new, mock_existing) is True


def test_not_duplicate(mock_existing: list[MagicMock]) -> None:
    engine = DeduplicationEngine()
    new = MagicMock()
    new.external_id = "NCT999"
    new.content_hash = "zzz"
    new.title = "Completely unrelated study title here"
    assert engine.is_duplicate(new, mock_existing) is False
