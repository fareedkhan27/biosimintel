# n8n Workflows

## Weekly Briefing

1. Trigger: Schedule (weekly)
2. HTTP Request: `POST /api/v1/intelligence/briefing`
3. Format: Convert JSON to HTML email
4. Send Email: Route by geography
   - India -> APAC team
   - US -> NA team
   - EU -> EMEA team

## Ingestion Jobs

1. Trigger: Schedule (daily) or Webhook
2. HTTP Request: `POST /api/v1/jobs/ingest/clinicaltrials`
3. HTTP Request: `POST /api/v1/jobs/ingest/fda-purple-book`
4. HTTP Request: `POST /api/v1/jobs/ingest/ema`
5. HTTP Request: `POST /api/v1/jobs/ingest/sec-edgar`
