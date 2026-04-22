from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.core.logging import get_logger
from app.models.event import Event
from app.schemas.intelligence import AskRequest, AskResponse
from app.services.ai.client import AIClient

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)


class QAEngine:
    """Natural language Q&A using ONLY verified data from the database."""

    def __init__(self) -> None:
        self.client = AIClient()

    async def answer(self, payload: AskRequest, db: AsyncSession) -> AskResponse:
        events_result = await db.execute(
            select(Event)
            .where(Event.molecule_id == payload.molecule_id)
            .where(Event.verification_status == "verified")
            .order_by(Event.event_date.desc())
        )
        events = list(events_result.scalars().all())

        context = self._build_context(events)
        prompt = f"""Answer the following question using ONLY the provided verified data.
Do NOT invent competitors, events, or dates.
Cite specific events by competitor and date when possible.
If the answer is not in the data, say so explicitly.

Question: {payload.question}

Verified Data:
{context}

Provide:
- answer: Direct answer to the question
- sources: List of cited sources (competitor, date, event_type)
- confidence: Your confidence in the answer based on data quality (0.0-1.0)
"""

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a pharmaceutical competitive intelligence analyst. "
                    "You answer questions using ONLY verified database records. "
                    "Never hallucinate facts."
                ),
            },
            {"role": "user", "content": prompt},
        ]

        try:
            response = await self.client.chat_completion(messages)
            content = response["choices"][0]["message"]["content"]
            parsed = self._parse_response(content)
            return AskResponse(
                answer=parsed.get("answer", "Unable to generate answer."),
                sources=parsed.get("sources", []),
                confidence=float(parsed.get("confidence", 0.5)),
            )
        except Exception as exc:
            logger.error("Q&A failed", error=str(exc))
            return AskResponse(
                answer="An error occurred while generating the answer.",
                sources=[],
                confidence=0.0,
            )

    def _build_context(self, events: list[Event]) -> str:
        lines: list[str] = []
        for e in events:
            competitor = e.competitor.canonical_name if e.competitor else "Unknown"
            lines.append(
                f"- {competitor} | {e.event_type} | {e.indication or 'N/A'} | "
                f"{e.country or 'N/A'} | {e.event_date or 'N/A'} | Stage: {e.development_stage or 'N/A'} | "
                f"Score: {e.threat_score or 'N/A'}"
            )
        return "\n".join(lines) if lines else "No verified events found."

    def _parse_response(self, content: str) -> dict[str, Any]:
        result: dict[str, Any] = {"answer": "", "sources": [], "confidence": 0.5}
        current_key: str | None = None
        current_value: list[str] = []

        def _flush() -> None:
            nonlocal current_key, current_value
            if current_key is None:
                return
            if current_key == "sources":
                result[current_key] = [s.lstrip("- ").strip() for s in current_value if s.strip()]
            else:
                result[current_key] = "\n".join(current_value).strip()

        for line in content.splitlines():
            stripped = line.strip()
            lower = stripped.lower()
            if lower.startswith("answer:"):
                _flush()
                current_key = "answer"
                current_value = [stripped.split(":", 1)[1].strip()] if ":" in stripped else []
            elif lower.startswith("sources:"):
                _flush()
                current_key = "sources"
                current_value = []
            elif lower.startswith("confidence:"):
                _flush()
                current_key = "confidence"
                current_value = [stripped.split(":", 1)[1].strip()] if ":" in stripped else []
            elif current_key:
                current_value.append(stripped)

        _flush()
        return result
