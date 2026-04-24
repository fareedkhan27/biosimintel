# n8n Smart Briefing Router — Phase 4D

This document describes the n8n workflows that power the smart briefing system. Each molecule can be configured with a `briefing_mode` that controls how and when briefings are delivered.

## Molecule Briefing Modes

| Mode           | Behavior                                                          |
|----------------|-------------------------------------------------------------------|
| `silent`       | Ingest data, never auto-email                                     |
| `alert_only`   | Email only when top threat score >= `alert_threshold`             |
| `weekly_digest`| Include in the weekly n8n briefing (default, current behavior)    |
| `on_demand`    | Never auto-email; only trigger via API                            |

## API Endpoints

- `GET /api/v1/molecules?briefing_mode=weekly_digest` — list molecules for weekly digest
- `GET /api/v1/molecules?briefing_mode=alert_only` — list molecules for daily alert workflow
- `GET /api/v1/intelligence/alert-check?molecule_id={id}` — check if alert threshold is breached
- `POST /api/v1/intelligence/briefing/email` — generate email briefing (respects preferences)
- `POST /api/v1/intelligence/briefing/trigger` — on-demand briefing (bypasses preferences)
- `PATCH /api/v1/molecules/{id}/preferences` — update molecule briefing preferences

All admin endpoints require `Authorization: Bearer {{BIOSIM_API_KEY}}`.

---

## Workflow 1: Weekly Digest

**Schedule:** Mondays 08:00

```
Schedule Trigger (Mondays 08:00)
  → HTTP Request: GET https://api.biosimintel.com/api/v1/molecules?briefing_mode=weekly_digest
    Headers: Authorization: Bearer {{BIOSIM_API_KEY}}
  → Loop Over Items
    → HTTP Request: POST /api/v1/intelligence/briefing/email
      Body: {"molecule_id": "{{ $json.id }}", "segments": ["market_access"], "since_days": 7}
    → IF: check html response
    → Send Email via Resend
```

Notes:
- The `briefing/email` endpoint will reject molecules in `silent`, `on_demand`, or `alert_only` mode.
- Only molecules with `briefing_mode == "weekly_digest"` and `is_monitored == true` are returned by the filter.

---

## Workflow 2: Daily Alert

**Schedule:** Daily 09:00

```
Schedule Trigger (Daily 09:00)
  → HTTP Request: GET https://api.biosimintel.com/api/v1/molecules?briefing_mode=alert_only
  → Loop Over Items
    → HTTP Request: GET /api/v1/intelligence/alert-check?molecule_id={{ $json.id }}
    → IF: $json.should_alert == true
      → HTTP Request: POST /api/v1/intelligence/briefing/email
        Body: {"molecule_id": "{{ $json.id }}", "segments": ["market_access"], "since_days": 7}
      → Send Email
```

Notes:
- The `alert-check` endpoint returns `should_alert: true` only if the top verified threat score is >= the molecule's `alert_threshold`.
- The response includes `top_score`, `threshold`, and the triggering `event` details.

---

## Workflow 3: On-Demand Trigger

**Trigger:** Webhook (manual or button)

```
Webhook Trigger (manual or button)
  → HTTP Request: POST /api/v1/intelligence/briefing/trigger
    Body: {"molecule_id": "...", "recipient": "..."}
  → Send Email
```

Notes:
- The `/briefing/trigger` endpoint bypasses all preference checks.
- It updates `last_briefing_sent_at` on the molecule.
- Useful for one-off briefings or testing.

---

## Backward Compatibility

- All existing molecules default to `weekly_digest` via the database default.
- The existing nivolumab weekly briefing workflow continues to work exactly as before.
- No breaking changes to any existing endpoints.
