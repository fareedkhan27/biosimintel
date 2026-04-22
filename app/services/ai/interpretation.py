from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.core.logging import get_logger
from app.services.ai.client import AIClient

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.event import Event

logger = get_logger(__name__)


class InterpretationService:
    """AI interpretation service — ONLY interprets verified data, never invents facts."""

    def __init__(self) -> None:
        self.client = AIClient()

    async def interpret(self, event: Event, _db: AsyncSession) -> None:
        if event.ai_interpreted_at is not None:
            logger.info("Event already interpreted, skipping", event_id=str(event.id))
            return

        # Build prompt from verified event data ONLY
        prompt = self._build_prompt(event)  # type: ignore[unreachable]

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a pharmaceutical competitive intelligence analyst. "
                    "You interpret structured event data for biosimilar monitoring. "
                    "You NEVER invent facts. If uncertain, say so explicitly. "
                    "Respond ONLY with the requested fields."
                ),
            },
            {"role": "user", "content": prompt},
        ]

        try:
            response = await self.client.chat_completion(messages)
            content = response["choices"][0]["message"]["content"]
            parsed = self._parse_response(content)

            event.ai_summary = parsed.get("summary")
            event.ai_why_it_matters = parsed.get("why_it_matters")
            event.ai_recommended_action = parsed.get("recommended_action")
            event.ai_confidence_note = parsed.get("confidence_note")
            event.ai_interpreted_at = datetime.now(UTC)

            logger.info("Event interpreted", event_id=str(event.id))
        except Exception as exc:
            logger.error("Interpretation failed", event_id=str(event.id), error=str(exc))
            raise

    def _build_prompt(self, event: Event) -> str:
        competitor_name = event.competitor.canonical_name if event.competitor else "Unknown"
        return f"""Interpret the following verified competitive intelligence event:

Competitor: {competitor_name}
Event Type: {event.event_type}
Event Subtype: {event.event_subtype or "N/A"}
Development Stage: {event.development_stage or "N/A"}
Indication: {event.indication or "N/A"}
Indication Priority: {event.indication_priority or "N/A"}
Country/Region: {event.country or "N/A"} / {event.region or "N/A"}
Event Date: {event.event_date or "N/A"}
Summary: {event.summary or "N/A"}
Evidence Excerpt: {event.evidence_excerpt or "N/A"}
Threat Score: {event.threat_score or "N/A"}
Traffic Light: {event.traffic_light or "N/A"}
Verification Status: {event.verification_status}
Verified Sources: {event.verified_sources_count}

Provide exactly these fields:
- summary: A concise 1-2 sentence summary of what happened
- why_it_matters: Strategic implications for the reference brand
- recommended_action: Recommended next steps for the intelligence team
- confidence_note: Any caveats or uncertainties about this interpretation
"""

    def _parse_response(self, content: str) -> dict[str, str]:
        result: dict[str, str] = {}
        current_key: str | None = None
        current_value: list[str] = []

        for line in content.splitlines():
            stripped = line.strip()
            if stripped.lower().startswith("summary:"):
                if current_key:
                    result[current_key] = "\n".join(current_value).strip()
                current_key = "summary"
                current_value = [stripped.split(":", 1)[1].strip()] if ":" in stripped else []
            elif stripped.lower().startswith("why_it_matters:") or stripped.lower().startswith("why it matters:"):
                if current_key:
                    result[current_key] = "\n".join(current_value).strip()
                current_key = "why_it_matters"
                current_value = [stripped.split(":", 1)[1].strip()] if ":" in stripped else []
            elif stripped.lower().startswith("recommended_action:") or stripped.lower().startswith("recommended action:"):
                if current_key:
                    result[current_key] = "\n".join(current_value).strip()
                current_key = "recommended_action"
                current_value = [stripped.split(":", 1)[1].strip()] if ":" in stripped else []
            elif stripped.lower().startswith("confidence_note:") or stripped.lower().startswith("confidence note:"):
                if current_key:
                    result[current_key] = "\n".join(current_value).strip()
                current_key = "confidence_note"
                current_value = [stripped.split(":", 1)[1].strip()] if ":" in stripped else []
            elif current_key:
                current_value.append(stripped)

        if current_key:
            result[current_key] = "\n".join(current_value).strip()

        return result
