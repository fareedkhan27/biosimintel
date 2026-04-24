# n8n Workflows

This document describes the n8n automation workflows that consume the Biosim API.

---

## 1. Weekly Department Briefing

**Schedule:** Every Monday at 08:00 UTC  
**Trigger:** n8n Cron node  
**API Endpoint:** `POST /api/v1/intelligence/briefing/email`

### Flow

1. **Cron Trigger** — Runs `0 8 * * 1` (Monday 08:00).
2. **Get Active Molecules** — `GET /api/v1/molecules?is_active=true`
3. **Loop Molecules** — For each active molecule:
   - `POST /api/v1/intelligence/briefing/email`
     ```json
     {
       "molecule_id": "<uuid>",
       "department": "market_access",
       "format": "html",
       "since_days": 7
     }
     ```
4. **Branch by Format**
   - If `html` is returned, pass `response.html` to the email sender.
   - If `json` is returned, format into a simple text email.
5. **Send via Resend** — Use the `recipient` and `from_email` fields from the response.
   - Subject: `response.subject`
   - Body: `response.html`
   - To: `response.recipient`
6. **Log Delivery** — POST delivery status to internal audit log (optional).

### Regional Routing

The API automatically routes based on the highest-priority event geography:

| Event Country/Region | Recipient (from API response) |
|---------------------|------------------------------|
| India, Japan, China, Australia | `APAC_EMAIL` |
| United States, US | `NA_EMAIL` |
| EU, Germany, France, UK, Spain, Italy | `EMEA_EMAIL` |
| Other / Mixed | `EXECUTIVE_EMAIL` |

---

## 2. Red Alert

**Schedule:** Every hour + immediate ingestion trigger  
**Trigger:** n8n Cron (`0 * * * *`) OR webhook from ingestion pipeline  
**API Endpoint:** `POST /api/v1/webhooks/red-alert`

### Flow

1. **Trigger** — Cron every hour, or immediate call after ingestion job completes.
2. **Call Red Alert Webhook** — `POST /api/v1/webhooks/red-alert` (no body required).
3. **Branch by Alert Count**
   - If `alert_count == 0`: End workflow silently.
   - If `alert_count > 0`: Continue.
4. **Loop Alerts** — For each alert:
   - Extract `event` and `routing` from the alert object.
   - Render a short alert email:
     - Subject: `[RED ALERT] {{ event.competitor.canonical_name }} — {{ event.traffic_light }} (Score: {{ event.threat_score }})`
     - Body: Event summary + recommended action + link to provenance.
   - Send via Resend to `routing.recipient`.
5. **Dedupe** — Use n8n static data or Redis to prevent duplicate alerts for the same event within 24h.

### Alert Criteria

The API returns only events that meet **all** of the following:
- `verification_status == "verified"`
- `traffic_light == "Red"`
- `created_at >= now() - 24 hours`

---

## 3. Press Release Monitor

**Schedule:** Continuous (every 15 minutes)  
**Trigger:** n8n Cron node  
**API Endpoint:** `POST /api/v1/jobs/ingest/press-release`

### Flow

1. **Cron Trigger** — Runs `*/15 * * * *`.
2. **Fetch RSS / News API** — Query external news sources (e.g., Google News API, PR Newswire RSS) for keywords matching active molecule `search_terms`.
3. **Filter New Items** — Compare URLs against already-ingested `source_documents` (query DB or cache).
4. **Ingest New PRs** — For each new press release:
   - `POST /api/v1/jobs/ingest/press-release?text=<url_extracted_text>&source_url=<url>&molecule_id=<uuid>`
5. **Trigger Red Alert Check** — After ingestion batch completes, call `POST /api/v1/webhooks/red-alert` to immediately surface any new Red events.
6. **Log** — Record ingestion count and any new events for audit.

### Notes

- The ingestion endpoint runs deterministic extraction, verification, and scoring automatically.
- Press releases deduplicate by `content_hash` inside the API.
- If the AI interpretation layer is enabled, events will also receive `ai_summary`, `ai_why_it_matters`, and `ai_recommended_action`.

---

## Environment Variables for n8n

Configure these in your n8n instance or `.env`:

```bash
BIOSIM_API_BASE_URL=https://api.biosim.example.com/api/v1
BIOSIM_API_KEY=your-api-key-here
RESEND_API_KEY=re_xxxxxxxx
```

## Security

- Use an API key or JWT in the `Authorization` header for all n8n→Biosim calls.
- The `/api/v1/webhooks/red-alert` endpoint is designed to be idempotent and safe to poll frequently.
- Rate-limit n8n Cron nodes to respect API limits (e.g., max 1 req/sec for webhooks).
