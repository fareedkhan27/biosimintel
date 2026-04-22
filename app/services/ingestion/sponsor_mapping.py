from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.competitor import Competitor

logger = get_logger(__name__)

ALIAS_MAP: dict[str, str] = {
    "accord healthcare": "Intas",
    "accord biopharma": "Intas",
    "novartis ag": "Sandoz",
    "novartis pharmaceuticals": "Sandoz",
    "novartis": "Sandoz",
    "shanghai henlius biotech": "Henlius",
    "shanghai henlius": "Henlius",
    "henlius biotech": "Henlius",
    "reliance life sciences pvt. ltd.": "Reliance Life Sciences",
    "reliance life sciences pvt": "Reliance Life Sciences",
    "reliance life": "Reliance Life Sciences",
    "dr. reddy's laboratories": "Dr. Reddy's",
    "dr reddy's laboratories": "Dr. Reddy's",
    "dr. reddys": "Dr. Reddy's",
    "biocon biologics ltd.": "Biocon Biologics",
    "biocon biologics ltd": "Biocon Biologics",
    "biocon biologics": "Biocon Biologics",
    "mabxience": "mAbxience",
    "mabxience holding": "mAbxience",
    "mabxience argentina": "mAbxience",
    "xbrane biopharma": "Xbrane",
    "xbrane": "Xbrane",
    "boan biotech": "Boan Biotech",
    "boan biologics": "Boan Biotech",
    "boan": "Boan Biotech",
    "enzene": "Enzene",
    "enzene biosciences": "Enzene",
    "enzene biosciences ltd": "Enzene",
    "neuclone": "NeuClone",
    "neuclone pty ltd": "NeuClone",
    "neuclone australia": "NeuClone",
}

BLOCKED_PATTERNS: list[str] = [
    "mayo clinic",
    "national cancer institute",
    "nci ",
    "nrg oncology",
    "university of",
    "university",
    "hospital",
    "medical center",
    "academic",
    "cancer center",
    "research institute",
    "school of medicine",
    "college of",
    "national institutes of health",
    "national institute",
]

ASSET_CODE_MAP: dict[str, str] = {
    r"\bABP 206\b": "Amgen",
    r"\bTishtha\b": "Zydus",
    r"\bXdivane\b": "Xbrane",
    r"\bBA1104\b": "Boan Biotech",
    r"\bJPB898\b": "Sandoz",
    r"\bHLX18\b": "Henlius",
    r"\bMB11\b": "mAbxience",
}

FUZZY_MATCH_THRESHOLD = 0.85


@dataclass
class SponsorMappingResult:
    """Result of mapping a sponsor name to a canonical competitor."""

    competitor: Competitor | None
    match_method: str | None
    confidence: float
    blocked: bool
    blocked_reason: str | None
    flag_for_review: bool


class SponsorMappingService:
    """Deterministic service that maps API sponsor names to canonical competitor records."""

    def __init__(self, competitors: list[Competitor] | None = None) -> None:
        self.competitors = competitors or []
        self._build_indexes()

    def _build_indexes(self) -> None:
        """Build lookup indexes from the competitor list."""
        self.alias_to_competitor: dict[str, Competitor] = {}
        self.canonical_to_competitor: dict[str, Competitor] = {}
        self.parent_to_competitor: dict[str, Competitor] = {}

        for competitor in self.competitors:
            self.canonical_to_competitor[competitor.canonical_name.lower()] = competitor
            if competitor.parent_company:
                self.parent_to_competitor[competitor.parent_company.lower()] = competitor

        for alias, canonical in ALIAS_MAP.items():
            canonical_lower = canonical.lower()
            alias_competitor = self.canonical_to_competitor.get(canonical_lower)
            if alias_competitor is None:
                alias_competitor = self.parent_to_competitor.get(canonical_lower)
            if alias_competitor:
                self.alias_to_competitor[alias.lower()] = alias_competitor

    async def load_competitors(self, db: AsyncSession, molecule_id: Any) -> None:
        """Load competitors from the database for a molecule and rebuild indexes."""
        result = await db.execute(
            select(Competitor).where(Competitor.molecule_id == molecule_id)
        )
        self.competitors = list(result.scalars().all())
        self._build_indexes()

    def map_sponsor_to_competitor(
        self,
        sponsor_name: str,
        sponsor_class: str | None,
        trial_title: str | None = None,
    ) -> SponsorMappingResult:
        """Map a sponsor name to a canonical competitor record.

        Matching priority:
        1. Exact alias match
        2. Exact canonical_name match (case-insensitive)
        3. Exact parent_company match (case-insensitive)
        4. Fuzzy match on canonical_name or parent_company (threshold: 0.85)
        5. Asset code extraction from trial title (regex fallback)

        Sponsor classes "NIH" and "NETWORK" are blocked immediately.
        Sponsor class "OTHER" is blocked unless it fuzzy-matches >= 0.85.
        Sponsor class "INDUSTRY" attempts mapping; no match flags for review.
        """
        normalized_name = sponsor_name.lower().strip()

        # Blocked patterns (academic / institutional)
        for pattern in BLOCKED_PATTERNS:
            if pattern in normalized_name:
                return SponsorMappingResult(
                    competitor=None,
                    match_method=None,
                    confidence=0.0,
                    blocked=True,
                    blocked_reason=f"blocked_pattern: {pattern}",
                    flag_for_review=False,
                )

        # Blocked sponsor classes
        if sponsor_class:
            class_upper = sponsor_class.upper()
            if class_upper in ("NIH", "NETWORK"):
                return SponsorMappingResult(
                    competitor=None,
                    match_method=None,
                    confidence=0.0,
                    blocked=True,
                    blocked_reason=f"blocked_class: {class_upper}",
                    flag_for_review=False,
                )

        # 1. Exact alias match
        competitor = self.alias_to_competitor.get(normalized_name)
        if competitor:
            return SponsorMappingResult(
                competitor=competitor,
                match_method="alias_exact",
                confidence=1.0,
                blocked=False,
                blocked_reason=None,
                flag_for_review=False,
            )

        # 2. Exact canonical_name match
        competitor = self.canonical_to_competitor.get(normalized_name)
        if competitor:
            return SponsorMappingResult(
                competitor=competitor,
                match_method="canonical_exact",
                confidence=1.0,
                blocked=False,
                blocked_reason=None,
                flag_for_review=False,
            )

        # 3. Exact parent_company match
        competitor = self.parent_to_competitor.get(normalized_name)
        if competitor:
            return SponsorMappingResult(
                competitor=competitor,
                match_method="parent_exact",
                confidence=1.0,
                blocked=False,
                blocked_reason=None,
                flag_for_review=False,
            )

        # 4. Fuzzy match on canonical_name or parent_company
        best_match: Competitor | None = None
        best_score = 0.0
        best_method = ""

        for canonical, competitor in self.canonical_to_competitor.items():
            score = fuzz.partial_ratio(normalized_name, canonical) / 100.0
            if score > best_score:
                best_score = score
                best_match = competitor
                best_method = "canonical_fuzzy"

        for parent, competitor in self.parent_to_competitor.items():
            score = fuzz.partial_ratio(normalized_name, parent) / 100.0
            if score > best_score:
                best_score = score
                best_match = competitor
                best_method = "parent_fuzzy"

        if best_score >= FUZZY_MATCH_THRESHOLD:
            return SponsorMappingResult(
                competitor=best_match,
                match_method=best_method,
                confidence=round(best_score, 4),
                blocked=False,
                blocked_reason=None,
                flag_for_review=False,
            )

        # 5. Asset code extraction from trial title
        if trial_title:
            for pattern, canonical in ASSET_CODE_MAP.items():
                if re.search(pattern, trial_title, re.IGNORECASE):
                    competitor = (
                        self.canonical_to_competitor.get(canonical.lower())
                        or self.parent_to_competitor.get(canonical.lower())
                    )
                    if competitor:
                        return SponsorMappingResult(
                            competitor=competitor,
                            match_method="asset_code",
                            confidence=0.9,
                            blocked=False,
                            blocked_reason=None,
                            flag_for_review=False,
                        )

        # No match found — apply class-specific rules
        if sponsor_class and sponsor_class.upper() == "OTHER":
            return SponsorMappingResult(
                competitor=None,
                match_method=None,
                confidence=0.0,
                blocked=True,
                blocked_reason="other_class_no_match",
                flag_for_review=False,
            )

        # INDUSTRY or missing class with no match — flag for review
        return SponsorMappingResult(
            competitor=None,
            match_method=None,
            confidence=0.0,
            blocked=False,
            blocked_reason=None,
            flag_for_review=True,
        )
