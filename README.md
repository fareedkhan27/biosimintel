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
- `tests/` - pytest test suite
