from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event


@pytest.mark.asyncio
async def test_interpret_event_returns_structured_fields(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """POST /events/{id}/interpret returns structured interpretation fields."""
    # Create molecule
    mol_resp = await client.post("/api/v1/molecules", json={
        "molecule_name": "nivolumab_interp",
        "reference_brand": "Opdivo",
        "manufacturer": "BMS",
        "search_terms": ["nivolumab"],
        "indications": {},
        "loe_timeline": {},
        "competitor_universe": [],
        "scoring_weights": {},
        "is_active": True,
    })
    molecule = mol_resp.json()

    # Create event via press release ingestion
    text = "Amgen announces positive Phase 3 results for ABP 206 in NSCLC."
    source_url = "https://amgen.com/news/2025/abp206"
    await client.post(
        f"/api/v1/jobs/ingest/press-release?text={text}&source_url={source_url}&molecule_id={molecule['id']}"
    )

    # Get the created event
    events_result = await db_session.execute(
        select(Event).where(Event.molecule_id == molecule["id"])
    )
    event = events_result.scalar_one()
    assert event.ai_interpreted_at is None

    # Mock AI client response
    mock_ai_response = {
        "choices": [{
            "message": {
                "content": (
                    "summary: Amgen reported positive Phase 3 results for ABP 206 in NSCLC.\n"
                    "why_it_matters: This advances a Tier 1 biosimilar competitor closer to market entry, "
                    "directly threatening Opdivo's NSCLC revenue (~$2.8B).\n"
                    "recommended_action: Monitor BLA filing timeline and prepare pricing defense strategy.\n"
                    "confidence_note: Based solely on press release language; need FDA submission confirmation."
                )
            }
        }]
    }

    with patch("app.services.ai.interpretation.AIClient.chat_completion", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = mock_ai_response

        resp = await client.post(f"/api/v1/events/{event.id}/interpret")
        assert resp.status_code == 200

        data = resp.json()
        assert data["ai_summary"] is not None
        assert "Amgen" in data["ai_summary"]
        assert data["ai_why_it_matters"] is not None
        assert data["ai_recommended_action"] is not None
        assert data["ai_confidence_note"] is not None
        assert data["ai_interpreted_at"] is not None

    # Verify AI was called exactly once
    mock_chat.assert_called_once()


@pytest.mark.asyncio
async def test_interpret_event_is_idempotent(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Calling interpret twice on the same event only calls AI once."""
    # Create molecule
    mol_resp = await client.post("/api/v1/molecules", json={
        "molecule_name": "nivolumab_idem",
        "reference_brand": "Opdivo",
        "manufacturer": "BMS",
        "search_terms": ["nivolumab"],
        "indications": {},
        "loe_timeline": {},
        "competitor_universe": [],
        "scoring_weights": {},
        "is_active": True,
    })
    molecule = mol_resp.json()

    # Create event
    text = "Boan Biotech reports Phase 3 enrollment complete for BA1104."
    source_url = "https://boanbio.com/news"
    await client.post(
        f"/api/v1/jobs/ingest/press-release?text={text}&source_url={source_url}&molecule_id={molecule['id']}"
    )

    events_result = await db_session.execute(
        select(Event).where(Event.molecule_id == molecule["id"])
    )
    event = events_result.scalar_one()

    mock_ai_response = {
        "choices": [{
            "message": {
                "content": (
                    "summary: Boan Biotech completed Phase 3 enrollment.\n"
                    "why_it_matters: China-market biosimilar threat advancing.\n"
                    "recommended_action: Monitor NMPA submission.\n"
                    "confidence_note: Based on company press release only."
                )
            }
        }]
    }

    with patch("app.services.ai.interpretation.AIClient.chat_completion", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = mock_ai_response

        # First call
        resp1 = await client.post(f"/api/v1/events/{event.id}/interpret")
        assert resp1.status_code == 200
        first_interpreted_at = resp1.json()["ai_interpreted_at"]

        # Second call — should be idempotent
        resp2 = await client.post(f"/api/v1/events/{event.id}/interpret")
        assert resp2.status_code == 200
        second_interpreted_at = resp2.json()["ai_interpreted_at"]

        # Same timestamp = no re-interpretation
        assert first_interpreted_at == second_interpreted_at

        # AI client should only be called once
        mock_chat.assert_called_once()


@pytest.mark.asyncio
async def test_interpret_event_ai_does_not_invent_facts(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """AI interpretation prompt only uses verified event data."""
    mol_resp = await client.post("/api/v1/molecules", json={
        "molecule_name": "nivolumab_facts",
        "reference_brand": "Opdivo",
        "manufacturer": "BMS",
        "search_terms": ["nivolumab"],
        "indications": {},
        "loe_timeline": {},
        "competitor_universe": [],
        "scoring_weights": {},
        "is_active": True,
    })
    molecule = mol_resp.json()

    text = "Sandoz suspends JPB898 Phase 3 trial due to portfolio reprioritization."
    source_url = "https://sandoz.com/news"
    await client.post(
        f"/api/v1/jobs/ingest/press-release?text={text}&source_url={source_url}&molecule_id={molecule['id']}"
    )

    events_result = await db_session.execute(
        select(Event).where(Event.molecule_id == molecule["id"])
    )
    event = events_result.scalar_one()

    captured_prompts: list[str] = []

    async def mock_chat_completion(messages: list[dict[str, str]], **_kwargs: Any) -> dict[str, Any]:
        captured_prompts.append(messages[1]["content"])
        return {
            "choices": [{
                "message": {
                    "content": (
                        "summary: Sandoz suspended JPB898.\n"
                        "why_it_matters: Reduced near-term threat.\n"
                        "recommended_action: Monitor portfolio restart.\n"
                        "confidence_note: Based on provided event data only."
                    )
                }
            }]
        }

    with patch("app.services.ai.interpretation.AIClient.chat_completion", side_effect=mock_chat_completion):
        resp = await client.post(f"/api/v1/events/{event.id}/interpret")
        assert resp.status_code == 200

    # Verify prompt only contains event data, no external knowledge
    assert len(captured_prompts) == 1
    prompt = captured_prompts[0]
    assert "Sandoz" in prompt
    assert event.event_type in prompt
    assert "Interpret the following verified competitive intelligence event" in prompt
    assert "NEVER invent facts" not in prompt  # The system prompt has this, not the user prompt


@pytest.mark.asyncio
async def test_interpret_event_not_found(client: AsyncClient) -> None:
    """Interpret on non-existent event returns 404."""
    from uuid import uuid4
    resp = await client.post(f"/api/v1/events/{uuid4()}/interpret")
    assert resp.status_code == 404
