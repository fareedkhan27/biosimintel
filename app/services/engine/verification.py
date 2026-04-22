from __future__ import annotations

from typing import Any

from rapidfuzz import fuzz

REQUIRED_SOURCES: dict[str, dict[str, Any]] = {
    "clinical_trial": {
        "sources": ["clinicaltrials_gov"],
        "min_confidence": 0.95,
    },
    "regulatory_approval": {
        "sources": ["fda_purple_book", "ema", "sec_edgar"],
        "min_confidence": 0.99,
    },
    "press_release": {
        "sources": ["company_ir"],
        "min_confidence": 0.85,
    },
    "pricing_launch": {
        "sources": ["company_ir", "sec_edgar"],
        "min_confidence": 0.90,
    },
}

FUZZY_MATCH_THRESHOLD = 0.85


class VerifiedEvent:
    def __init__(self, event: Any, confidence: float, sources: list[str]) -> None:
        self.event = event
        self.confidence = confidence
        self.sources = sources
        self.status = "verified"


class RejectedEvent:
    def __init__(self, event: Any, reason: str) -> None:
        self.event = event
        self.reason = reason
        self.status = "rejected"


class VerificationEngine:
    """Deterministic verification engine."""

    def verify(
        self,
        event: Any,
        provenance: list[Any],
    ) -> VerifiedEvent | RejectedEvent:
        event_type = (event.event_type or "").lower()
        rules = REQUIRED_SOURCES.get(event_type, {})

        if not rules:
            return VerifiedEvent(event, confidence=0.5, sources=[])

        required = set(rules.get("sources", []))
        min_confidence = rules.get("min_confidence", 0.5)

        available_sources: set[str] = set()
        avg_confidence = 0.0
        if provenance:
            confidences = []
            for p in provenance:
                src = (p.extraction_method or "").lower()
                available_sources.add(src)
                confidences.append(float(p.confidence or 1.0))
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        if required and not required.intersection(available_sources):
            return RejectedEvent(
                event,
                reason=f"Missing required source. Needed one of {required}, got {available_sources}",
            )

        if avg_confidence < min_confidence:
            return RejectedEvent(
                event,
                reason=f"Confidence {avg_confidence:.2f} below minimum {min_confidence}",
            )

        return VerifiedEvent(
            event,
            confidence=avg_confidence,
            sources=list(available_sources),
        )

    def fuzzy_match_competitor(self, name: str, candidates: list[str]) -> str | None:
        best_match: str | None = None
        best_score = 0.0
        for candidate in candidates:
            score = fuzz.ratio(name.lower(), candidate.lower()) / 100.0
            if score > best_score:
                best_score = score
                best_match = candidate
        if best_score >= FUZZY_MATCH_THRESHOLD:
            return best_match
        return None
