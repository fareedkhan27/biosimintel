# API Contract

## Health
- `GET /api/v1/health` - Status, version, dependency checks

## Molecules
- `GET /api/v1/molecules` - List all
- `POST /api/v1/molecules` - Create
- `GET /api/v1/molecules/{id}` - Get
- `PATCH /api/v1/molecules/{id}` - Update

## Events
- `GET /api/v1/events` - List with filters
- `GET /api/v1/events/{id}` - Get
- `GET /api/v1/events/{id}/provenance` - Provenance trail
- `POST /api/v1/events/{id}/interpret` - AI interpretation

## Competitors
- `GET /api/v1/competitors` - List with filters
- `POST /api/v1/competitors` - Create
- `GET /api/v1/competitors/{id}` - Get

## Intelligence
- `GET /api/v1/intelligence/summary` - Dashboard summary
- `GET /api/v1/intelligence/top-threats` - Top threats
- `GET /api/v1/intelligence/recent` - Recent events
- `POST /api/v1/intelligence/briefing` - Department briefing
- `POST /api/v1/intelligence/ask` - Natural language Q&A

## Jobs
- `POST /api/v1/jobs/ingest/clinicaltrials` - ClinicalTrials.gov sync
- `POST /api/v1/jobs/ingest/ema` - EMA sync
- `POST /api/v1/jobs/ingest/sec-edgar` - SEC EDGAR sync
- `POST /api/v1/jobs/ingest/fda-purple-book` - FDA Purple Book sync
- `POST /api/v1/jobs/ingest/press-release` - Ingest unstructured text
- `POST /api/v1/jobs/recompute-scores` - Recalculate scores
