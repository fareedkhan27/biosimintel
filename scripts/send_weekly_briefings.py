"""Send weekly digest briefings for molecules in weekly_digest mode."""
from __future__ import annotations

import asyncio
import os
import sys

import httpx

API_BASE_URL = os.getenv("API_BASE_URL", "https://api.biosimintel.com").rstrip("/")
API_KEY = os.getenv("BIOSIM_API_KEY", "")
BRIEFING_RECIPIENT = os.getenv("BRIEFING_RECIPIENT", "na-team@biosimintel.com")
BRIEFING_CC = os.getenv("BRIEFING_CC", "")

HEADERS: dict[str, str] = {"Content-Type": "application/json"}
if API_KEY:
    HEADERS["Authorization"] = f"Bearer {API_KEY}"

TIMEOUT = httpx.Timeout(60.0, connect=10.0)


async def send_weekly_briefings() -> int:
    """Fetch weekly_digest molecules and send briefing emails."""
    exit_code = 0
    async with httpx.AsyncClient(timeout=TIMEOUT, headers=HEADERS) as client:
        try:
            resp = await client.get(
                f"{API_BASE_URL}/api/v1/molecules?briefing_mode=weekly_digest"
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            print(f"Failed to fetch molecules: {exc.response.status_code} {exc.response.text}")
            return 1
        except httpx.RequestError as exc:
            print(f"Failed to fetch molecules: {exc}")
            return 1

        molecules = resp.json()
        if not molecules:
            print("No molecules in weekly_digest mode. Skipping.")
            return 0

        sent_names: list[str] = []
        for molecule in molecules:
            molecule_id = molecule.get("id")
            molecule_name = molecule.get("molecule_name", "unknown")
            if not molecule_id:
                print(f"Skipping molecule with missing id: {molecule_name}")
                continue

            payload = {
                "molecule_id": molecule_id,
                "segments": ["market_access"],
                "since_days": 7,
            }
            try:
                post_resp = await client.post(
                    f"{API_BASE_URL}/api/v1/intelligence/briefing/email",
                    json=payload,
                )
                post_resp.raise_for_status()
                sent_names.append(molecule_name)
            except httpx.HTTPStatusError as exc:
                print(
                    f"ERROR sending weekly briefing for {molecule_name}: "
                    f"{exc.response.status_code} {exc.response.text}"
                )
                exit_code = 1
                continue
            except httpx.RequestError as exc:
                print(f"ERROR sending weekly briefing for {molecule_name}: {exc}")
                exit_code = 1
                continue

        if sent_names:
            names_str = ", ".join(sent_names)
            print(f"Sent {len(sent_names)} weekly briefing(s): {names_str}")
        else:
            print("No weekly briefings were sent.")

    return exit_code


if __name__ == "__main__":
    sys.exit(asyncio.run(send_weekly_briefings()))
