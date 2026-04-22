from __future__ import annotations

import hashlib
from typing import Any

from rapidfuzz.distance import Levenshtein

LEVENSHTEIN_THRESHOLD = 5


class DeduplicationEngine:
    """Deterministic deduplication engine."""

    @staticmethod
    def compute_content_hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def is_duplicate(
        self,
        event: Any,
        existing_events: list[Any],
    ) -> bool:
        for existing in existing_events:
            if event.external_id and existing.external_id and event.external_id == existing.external_id:
                return True
            if event.content_hash and existing.content_hash and event.content_hash == existing.content_hash:
                return True
            if self._fuzzy_match(event, existing):
                return True
        return False

    def _fuzzy_match(self, a: Any, b: Any) -> bool:
        title_a = (a.title or "").lower()
        title_b = (b.title or "").lower()
        if not title_a or not title_b:
            return False
        distance = Levenshtein.distance(title_a, title_b)
        return distance <= LEVENSHTEIN_THRESHOLD
