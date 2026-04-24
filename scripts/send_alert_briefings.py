#!/usr/bin/env python3
"""
Daily alert sender. Runs via Railway cron (biosim-emailer-alerts service).
Checks alert thresholds, fetches HTML from API, then sends via Resend SMTP.
"""
import asyncio
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
    r.raise_for_status()
    print(f"  Resend ID: {r.json().get('id', 'N/A')}")


async def main() -> None:
    if not API_KEY:
        print("BIOSIM_API_KEY not set")
        raise SystemExit(1)
    if not SMTP_PASS:
        print("SMTP_PASS or RESEND_API_KEY not set")
        raise SystemExit(1)

    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.get(
            f"{API_BASE}/api/v1/molecules?briefing_mode=alert_only",
            headers={"Authorization": f"Bearer {API_KEY}"},
        )
        r.raise_for_status()
        molecules = r.json()

        if not molecules:
            print("No molecules in alert_only mode. Skipping.")
            return

        alert_count = 0
        for m in molecules:
            name = m.get("molecule_name", "Unknown")
            mid = m["id"]
            try:
                # Check threshold
                ar = await client.get(
                    f"{API_BASE}/api/v1/intelligence/alert-check?molecule_id={mid}",
                    headers={"Authorization": f"Bearer {API_KEY}"},
                )
                ar.raise_for_status()
                alert_data = ar.json()

                if not alert_data.get("should_alert"):
                    score = alert_data.get("top_score", "N/A")
                    threshold = alert_data.get("threshold", "N/A")
                    print(f"No alert for {name}: score {score} < threshold {threshold}")
                    continue

                # Fetch HTML
                top_score = alert_data.get("top_score", "N/A")
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

                # SEND ALERT EMAIL
                subject = f"[Biosim] ALERT: {name} -- Threat Score {top_score}"
                await send_resend_email(client, subject, html_content, RECIPIENT, CC)
                print(f"ALERT sent for {name}: top score {top_score} >= threshold {alert_data.get('threshold')}")
                alert_count += 1

            except Exception as e:
                print(f"Failed for {name}: {type(e).__name__}: {e}")
                continue

        if alert_count == 0:
            print("No alerts triggered today.")


if __name__ == "__main__":
    asyncio.run(main())
