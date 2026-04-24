# Biosim

Deterministic-first, AI-reasoning-only competitive intelligence platform for pharmaceutical biosimilar monitoring.

## Core Philosophy

- **Deterministic extraction**: APIs, structured downloads, CSS selectors. Never AI for structured data extraction.
- **Deterministic verification**: Cross-reference, schema validation, provenance tracking. Never AI to verify facts.
- **Deterministic scoring**: Weighted algorithm with full audit trail. Never AI for scoring.
- **AI-only-for-interpretation**: OpenRouter/Gemini used ONLY for why it matters, recommended action, user Q&A, and digest composition.

## Quick Start

```bash
# Copy environment
cp .env.example .env

# Start infrastructure
docker compose up -d postgres redis

# Run migrations
alembic upgrade head

# Seed data
python -m app.db.seeds

# Start app
uvicorn app.main:app --reload
```

## Email Automation

Powered by Railway-native cron services. Zero external dependencies.

- `biosim-emailer-weekly`: Mondays 08:00 UTC — sends digest for all `weekly_digest` molecules
- `biosim-emailer-alerts`: Daily 09:00 UTC — sends alerts for `alert_only` molecules crossing thresholds

See `docs/railway_cron_architecture.md` for full architecture details.

## Testing

```bash
pytest --cov=app --cov-report=term-missing
ruff check .
mypy app
```

## Project Structure

- `app/` - FastAPI application
- `app/core/` - Config, logging, exceptions
- `app/api/v1/` - REST API endpoints
- `app/models/` - SQLAlchemy ORM models
- `app/schemas/` - Pydantic v2 request/response schemas
- `app/services/` - Business logic and ingestion engines
- `app/db/` - Database session, migrations, seeds
- `scripts/` - Standalone utilities and cron job scripts
- `tests/` - pytest test suite
