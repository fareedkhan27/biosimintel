#!/usr/bin/env python3
"""
Weekly briefing sender. Runs via Railway cron (biosim-emailer-weekly service).
Fetches HTML from API, then sends via Resend SMTP.
"""
import asyncio
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import httpx

API_BASE = os.getenv("API_BASE_URL", "https://api.biosimintel.com")
API_KEY = os.getenv("BIOSIM_API_KEY")
RECIPIENT = os.getenv("BRIEFING_RECIPIENT", "na-team@biosimintel.com")
CC = os.getenv("BRIEFING_CC", "")

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.resend.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "resend")
SMTP_PASS = os.getenv("SMTP_PASS") or os.getenv("RESEND_API_KEY", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", "intelligence@biosimintel.com")


def send_smtp_email(subject: str, html_body: str, to: str, cc: str = "") -> None:
    """Send HTML email via SMTP."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = EMAIL_FROM
    msg["To"] = to
    if cc:
        msg["Cc"] = cc

    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)


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
                send_smtp_email(subject, html_content, RECIPIENT, CC)
                print(f"Email sent for {name}")
                sent_count += 1

            except Exception as e:
                print(f"Failed for {name}: {type(e).__name__}: {e}")
                continue

        print(f"Sent {sent_count} weekly briefing(s)")


if __name__ == "__main__":
    asyncio.run(main())
