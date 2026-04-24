"""Send daily alert briefings for molecules in alert_only mode."""
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


async def send_alert_briefings() -> int:
    """Fetch alert_only molecules, check thresholds, and send alert emails."""
    exit_code = 0
    async with httpx.AsyncClient(timeout=TIMEOUT, headers=HEADERS) as client:
        try:
            resp = await client.get(
                f"{API_BASE_URL}/api/v1/molecules?briefing_mode=alert_only"
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
            print("No molecules in alert_only mode. Skipping.")
            return 0

        for molecule in molecules:
            molecule_id = molecule.get("id")
            molecule_name = molecule.get("molecule_name", "unknown")
            if not molecule_id:
                print(f"Skipping molecule with missing id: {molecule_name}")
                continue

            try:
                check_resp = await client.get(
                    f"{API_BASE_URL}/api/v1/intelligence/alert-check?molecule_id={molecule_id}"
                )
                check_resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                print(
                    f"ERROR checking alert for {molecule_name}: "
                    f"{exc.response.status_code} {exc.response.text}"
                )
                exit_code = 1
                continue
            except httpx.RequestError as exc:
                print(f"ERROR checking alert for {molecule_name}: {exc}")
                exit_code = 1
                continue

            check_data = check_resp.json()
            should_alert = check_data.get("should_alert", False)
            top_score = check_data.get("top_score", 0)
            threshold = check_data.get("threshold", 0)

            if not should_alert:
                print(
                    f"No alert for {molecule_name}: "
                    f"score {top_score} < threshold {threshold}"
                )
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
                print(
                    f"ALERT sent for {molecule_name}: "
                    f"top score {top_score} >= threshold {threshold}"
                )
            except httpx.HTTPStatusError as exc:
                print(
                    f"ERROR sending alert briefing for {molecule_name}: "
                    f"{exc.response.status_code} {exc.response.text}"
                )
                exit_code = 1
                continue
            except httpx.RequestError as exc:
                print(f"ERROR sending alert briefing for {molecule_name}: {exc}")
                exit_code = 1
                continue

    return exit_code


if __name__ == "__main__":
    sys.exit(asyncio.run(send_alert_briefings()))
