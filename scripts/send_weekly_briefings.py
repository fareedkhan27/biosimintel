#!/usr/bin/env python3
"""
Weekly briefing sender. Runs via Railway cron (biosim-emailer-weekly service).
Fetches HTML from API, then sends via Resend SMTP.
"""
import asyncio
import json
import os

import httpx

API_BASE = os.getenv("API_BASE_URL", "https://api.biosimintel.com")
API_KEY = os.getenv("BIOSIM_API_KEY")
RECIPIENT = (os.getenv("BRIEFING_RECIPIENT") or "na-team@biosimintel.com").strip()
CC = (os.getenv("BRIEFING_CC") or "").strip()

SMTP_PASS = os.getenv("SMTP_PASS") or os.getenv("RESEND_API_KEY", "")
EMAIL_FROM = (os.getenv("EMAIL_FROM") or "intelligence@biosimintel.com").strip()


async def send_resend_email(
    client: httpx.AsyncClient,
    subject: str,
    html_body: str,
    to: str,
    cc: str = ""
) -> None:
    api_key = (os.getenv("RESEND_API_KEY") or os.getenv("SMTP_PASS") or "").strip()
    payload = {
        "from": EMAIL_FROM,
        "to": [to],
        "subject": subject,
        "html": html_body,
    }
    if cc:
        payload["cc"] = [cc] if "," not in cc else [c.strip() for c in cc.split(",")]

    print(f"DEBUG: from='{EMAIL_FROM}'")
    print(f"DEBUG: to='{to}'")
    print(f"DEBUG: subject='{subject[:50]}...'")
    print(f"DEBUG: html_length={len(html_body)}")

    r = await client.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {api_key}"},
        json=payload,
    )
    try:
        r.raise_for_status()
    except httpx.HTTPStatusError as e:
        print(f"RESEND ERROR STATUS: {e.response.status_code}")
        print(f"RESEND ERROR BODY: {e.response.text}")
        print(f"RESEND REQUEST PAYLOAD: {json.dumps(payload, indent=2)}")
        raise
    print(f"  Resend ID: {r.json().get('id', 'N/A')}")


async def main() -> None:
    if not API_KEY:
        print("BIOSIM_API_KEY not set")
        raise SystemExit(1)
    if not SMTP_PASS:
        print("SMTP_PASS or RESEND_API_KEY not set")
        raise SystemExit(1)

    async with httpx.AsyncClient(timeout=60.0) as client:
        # 1. Get weekly_digest molecules
        r = await client.get(
            f"{API_BASE}/api/v1/molecules?briefing_mode=weekly_digest",
            headers={"Authorization": f"Bearer {API_KEY}"},
        )
        r.raise_for_status()
        molecules = r.json()

        if not molecules:
            print("No molecules in weekly_digest mode. Skipping.")
            return

        sent_count = 0
        for m in molecules:
            name = m.get("molecule_name", "Unknown")
            mid = m["id"]
            try:
                # 2. Generate briefing HTML
                br = await client.post(
                    f"{API_BASE}/api/v1/intelligence/briefing/email",
                    headers={
                        "Authorization": f"Bearer {API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "molecule_id": str(mid),
                        "segments": ["market_access"],
                        "since_days": 7,
                    },
                )
                br.raise_for_status()
                response_data = br.json()
                html_content = response_data["html"]

                # 3. SEND THE EMAIL via SMTP
                subject = f"[Biosim] Weekly Briefing: {name}"
                await send_resend_email(client, subject, html_content, RECIPIENT, CC)
                print(f"Email sent for {name}")
                sent_count += 1

            except Exception as e:
                print(f"Failed for {name}: {type(e).__name__}: {e}")
                continue

        print(f"Sent {sent_count} weekly briefing(s)")


if __name__ == "__main__":
    asyncio.run(main())
