from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_events(client: AsyncClient) -> None:
    response = await client.get("/api/v1/events")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
