# Railway Cron Architecture

Phase 4E replaced the external n8n dependency with Railway-native cron services. All email automation is now handled by lightweight Python scripts invoked via Railway cron schedules.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         Railway Project                          │
│                                                                  │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │  biosimintel    │  │  biosim-redis   │  │  biosim-ingest  │  │
│  │  (FastAPI)      │  │  (Cache/Queue)  │  │  (Daily 06:00)  │  │
│  └────────┬────────┘  └─────────────────┘  └─────────────────┘  │
│           │                                                      │
│           │  API calls                                           │
│           │                                                      │
│  ┌────────┴──────────────────────────────────────────────────┐  │
│  │              biosim-emailer-weekly                         │  │
│  │              (Monday 08:00 UTC)                            │  │
│  │              → GET /molecules?briefing_mode=weekly_digest  │  │
│  │              → POST /intelligence/briefing/email           │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │              biosim-emailer-alerts                         │  │
│  │              (Daily 09:00 UTC)                             │  │
│  │              → GET /molecules?briefing_mode=alert_only     │  │
│  │              → GET /intelligence/alert-check               │  │
│  │              → POST /intelligence/briefing/email           │  │
│  └────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Service Schedule

| Service | Schedule | Purpose |
|---------|----------|---------|
| `biosim-ingest` | Daily 06:00 UTC | Refresh ClinicalTrials.gov data |
| `biosim-emailer-weekly` | Monday 08:00 UTC | Send weekly digest emails for `weekly_digest` molecules |
| `biosim-emailer-alerts` | Daily 09:00 UTC | Send threshold breach alerts for `alert_only` molecules |

## Molecule Briefing Modes

| Mode | Behavior |
|------|----------|
| `silent` | Ingest data, never auto-email |
| `alert_only` | Email only when top threat score >= `alert_threshold` |
| `weekly_digest` | Include in the weekly digest (default) |
| `on_demand` | Never auto-email; only trigger via API |

## Environment Variables

The emailer services require the following environment variables:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `API_BASE_URL` | No | `https://api.biosimintel.com` | Base URL of the Biosim API |
| `BIOSIM_API_KEY` | Yes | — | API key for `Authorization: Bearer` header |
| `BRIEFING_RECIPIENT` | No | `na-team@biosimintel.com` | Primary recipient for briefing emails |
| `BRIEFING_CC` | No | *(empty)* | CC recipients (comma-separated) |

## Changing Molecule Briefing Modes

Use the PATCH endpoint to update a molecule's briefing preferences:

```bash
curl -X PATCH "https://api.biosimintel.com/api/v1/molecules/{molecule_id}/preferences" \
  -H "Authorization: Bearer $BIOSIM_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "briefing_mode": "alert_only",
    "alert_threshold": 70,
    "is_monitored": true
  }'
```

## Manual Trigger

To send a briefing on demand (bypasses all preference checks):

```bash
curl -X POST "https://api.biosimintel.com/api/v1/intelligence/briefing/trigger" \
  -H "Authorization: Bearer $BIOSIM_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "molecule_id": "<uuid>",
    "recipient": "user@example.com",
    "since_days": 7
  }'
```

## API Endpoints Used by Cron Services

- `GET /api/v1/molecules?briefing_mode={mode}` — list molecules for a given briefing mode
- `GET /api/v1/intelligence/alert-check?molecule_id={id}` — check if alert threshold is breached
- `POST /api/v1/intelligence/briefing/email` — generate and send email briefing
- `POST /api/v1/intelligence/briefing/trigger` — on-demand briefing (manual use only)

All admin endpoints require `Authorization: Bearer {{BIOSIM_API_KEY}}`.
