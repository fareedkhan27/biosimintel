# Biosim — Complete Project Blueprint

> **Version:** 0.1.0  
> **Purpose:** A single-file reference for understanding every component, file, and architectural decision in the Biosim competitive intelligence platform.  
> **Audience:** New developers, DevOps engineers, technical stakeholders, and AI agents onboarding to the project.

---

## 1. Project Intent & Core Philosophy

**Biosim** is a **deterministic-first, AI-reasoning-only competitive intelligence platform** for pharmaceutical biosimilar monitoring. It tracks competitor activity around specific drug molecules (e.g., nivolumab/Opdivo), ingests data from sources like ClinicalTrials.gov, FDA Purple Book, EMA, SEC EDGAR, and press releases, verifies events deterministically, scores threats algorithmically, and uses AI *only* for interpretation (why it matters, recommended actions, Q&A, and briefing composition).

### Four Pillars of the Design

| Pillar | Rule |
|--------|------|
| **Deterministic Extraction** | APIs, structured downloads, CSS selectors. Never AI for structured data extraction. |
| **Deterministic Verification** | Cross-reference, schema validation, provenance tracking. Never AI to verify facts. |
| **Deterministic Scoring** | Weighted algorithm with full audit trail. Never AI for scoring. |
| **AI-Only-for-Interpretation** | OpenRouter/Gemini used ONLY for why it matters, recommended action, user Q&A, and digest composition. |

---

## 2. Complete File Tree

```
Biosim/
├── .git/                          # Git repository metadata
├── .mypy_cache/                   # mypy incremental cache
├── .pytest_cache/                 # pytest test result cache
├── .ruff_cache/                   # ruff lint cache
├── .venv/                         # Python virtual environment
│
├── alembic/                       # Database migrations
│   ├── env.py                     # Async Alembic environment (Neon SSL-compatible)
│   ├── script.py.mako             # Migration template
│   └── versions/
│       └── 20250422_0137_initial_schema.py   # Initial schema migration
│
├── app/                           # FastAPI application
│   ├── api/
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── router.py          # V1 API router aggregator
│   │       ├── health.py          # Health check endpoints
│   │       ├── molecules.py       # Molecule CRUD endpoints
│   │       ├── competitors.py     # Competitor CRUD + filtering
│   │       ├── events.py          # Event listing, detail, provenance, interpretation
│   │       ├── intelligence.py    # Briefings, Q&A, summaries, email dispatch
│   │       ├── jobs.py            # Ingestion triggers + score recomputation
│   │       └── webhooks.py        # n8n webhook endpoints
│   │
│   ├── core/
│   │   ├── config.py              # Pydantic Settings (env vars, DB, Redis, SMTP, etc.)
│   │   ├── exceptions.py          # Custom exception hierarchy
│   │   └── logging.py             # structlog configuration (JSON/TTY renderers)
│   │
│   ├── db/
│   │   ├── session.py             # Async SQLAlchemy engine + session factory
│   │   ├── seeds.py               # Idempotent seed runner
│   │   └── seed_data.py           # Hardcoded nivolumab + 12 competitor seeds
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── molecule.py            # Tracked drug molecule
│   │   ├── competitor.py          # Biosimilar competitor company
│   │   ├── event.py               # Competitive intelligence event
│   │   ├── source_document.py     # Raw ingested document
│   │   ├── data_provenance.py     # Audit trail per extracted field
│   │   ├── scoring_rule.py        # Configurable scoring rules
│   │   └── review.py              # Human review of events
│   │
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── molecule.py            # Molecule Pydantic schemas
│   │   ├── competitor.py          # Competitor Pydantic schemas
│   │   ├── event.py               # Event Pydantic schemas
│   │   ├── intelligence.py        # Briefing, Q&A, email schemas
│   │   ├── job.py                 # Job trigger response schema
│   │   ├── health.py              # Health check schema
│   │   ├── source_document.py     # Source document schemas
│   │   └── data_provenance.py     # Provenance schemas
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── intelligence_service.py    # Briefing generation + email rendering
│   │   ├── competitor_service.py      # Competitor business logic
│   │   ├── event_service.py           # Event business logic
│   │   ├── dashboard_service.py       # Dashboard aggregation (placeholder)
│   │   ├── review_service.py          # Review workflow (placeholder)
│   │   │
│   │   ├── ai/
│   │   │   ├── __init__.py
│   │   │   ├── client.py              # OpenRouter wrapper (Gemini → Claude fallback)
│   │   │   ├── interpretation.py      # AI interpretation of verified events
│   │   │   └── qa_engine.py           # Natural language Q&A engine
│   │   │
│   │   ├── engine/
│   │   │   ├── __init__.py
│   │   │   ├── scoring.py             # Deterministic threat scoring (0-100 + traffic light)
│   │   │   ├── deduplication.py       # External_id / hash / fuzzy dedup
│   │   │   └── verification.py        # Source validation + confidence thresholds
│   │   │
│   │   └── ingestion/
│   │       ├── __init__.py
│   │       ├── clinicaltrials.py      # ClinicalTrials.gov API v2 ingestion (fully implemented)
│   │       ├── press_release.py       # Unstructured PR ingestion (fully implemented)
│   │       ├── ema.py                 # EMA ingestion (placeholder)
│   │       ├── fda_purple_book.py     # FDA Purple Book ingestion (placeholder)
│   │       └── sec_edgar.py           # SEC EDGAR ingestion (placeholder)
│   │
│   ├── templates/
│   │   └── email/
│   │       └── weekly_briefing.html   # Jinja2 HTML email template
│   │
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── dates.py                 # UTC date helpers
│   │   ├── hashing.py               # SHA-256 helper
│   │   ├── text.py                  # Truncate + whitespace normalization
│   │   └── validators.py            # UUID validation
│   │
│   ├── __init__.py
│   └── main.py                      # FastAPI app factory with lifespan manager
│
├── docker/
│   └── Dockerfile                   # Python 3.12 slim image
│
├── docs/
│   ├── api-contract/                # API endpoint documentation
│   ├── deployment/                  # Docker & Railway deployment docs
│   ├── n8n-workflows/
│   │   └── ...                      # n8n workflow specification assets
│   └── n8n-workflows.md             # n8n automation workflow specs
│
├── scripts/
│   ├── run_checks.py                # Lint (ruff) → type-check (mypy) → test (pytest)
│   ├── seed_competitors.py          # CLI wrapper for seeding competitors
│   └── seed_molecules.py            # CLI wrapper for seeding molecules
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py                  # pytest fixtures (test DB, async client, session)
│   ├── factories/                   # factory-boy factories (placeholder)
│   ├── integration/                 # 18 integration test files
│   │   ├── test_health.py
│   │   ├── test_molecules.py
│   │   ├── test_competitors.py
│   │   ├── test_events.py
│   │   ├── test_intelligence.py
│   │   ├── test_jobs.py
│   │   ├── test_events_full.py
│   │   ├── test_intelligence_full.py
│   │   ├── test_jobs_full.py
│   │   ├── test_jobs_ingestion.py
│   │   ├── test_phase2_deterministic_ingestion.py
│   │   ├── test_phase3_ai_interpretation.py
│   │   ├── test_phase4_department_briefings.py
│   │   ├── test_phase4_natural_language_qa.py
│   │   ├── test_phase5_email_briefing.py
│   │   └── test_phase5_red_alert_webhook.py
│   └── unit/                        # 12 unit test files
│       ├── test_core.py
│       ├── test_utils.py
│       ├── test_scoring_engine.py
│       ├── test_deduplication_engine.py
│       ├── test_verification_engine.py
│       ├── test_ai_client.py
│       ├── test_ai_services.py
│       ├── test_intelligence_service.py
│       ├── test_clinicaltrials_service.py
│       ├── test_ingestion_services.py
│       └── test_services.py
│
├── .env                             # Local environment variables (gitignored)
├── .env.example                     # Environment variable template
├── .gitignore
├── alembic.ini                      # Alembic configuration
├── BIOSIM_BLUEPRINT.md              # This file
├── docker-compose.yml               # Postgres 16 + Redis 7 + App
├── pyproject.toml                   # Build, pytest, mypy, ruff config + dependencies
├── railway.toml                     # Railway.app deployment config
├── requirements.txt                 # Production dependencies (generated)
├── requirements-dev.txt             # Dev dependencies (generated)
├── README.md                        # Human-facing quick start guide
└── start.sh                         # Railway startup script (migrations + seeds + uvicorn)
```

---

## 3. Technology Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Language | Python | 3.12+ |
| Web Framework | FastAPI | 0.115+ |
| Server | Uvicorn (standard) | 0.30+ |
| ORM | SQLAlchemy (async) | 2.0+ |
| Database Driver | asyncpg + psycopg | 0.29+ / 3.2+ |
| Migrations | Alembic | 1.13+ |
| Cache | Redis | 5.0+ |
| Validation | Pydantic v2 + pydantic-settings | 2.8+ / 2.4+ |
| HTTP Client | httpx | 0.27+ |
| Logging | structlog + python-json-logger | 24.4+ / 2.0+ |
| Retry Logic | tenacity | 9.0+ |
| Fuzzy Matching | rapidfuzz | 3.9+ |
| Templating | Jinja2 | 3.1+ |
| Monitoring | Sentry SDK (FastAPI) | 2.14+ |
| Testing | pytest + pytest-asyncio + pytest-cov + pytest-mock | 8.3+ |
| Linting | ruff | 0.6+ |
| Type Checking | mypy (strict mode) | 1.11+ |
| AI API | OpenRouter (primary: Gemini, fallback: Claude) | — |

---

## 4. Application Architecture

### 4.1 Request Lifecycle

```
HTTP Request
    ↓
FastAPI (app/main.py)
    ↓
API Router (app/api/v1/router.py)
    ↓
Endpoint Handler (app/api/v1/*.py)
    ↓
Pydantic Schema Validation (app/schemas/*.py)
    ↓
Service Layer (app/services/*.py)
    │   ├── Business Services (intelligence, competitor, event...)
    │   ├── Ingestion Services (clinicaltrials, press_release, ema...)
    │   ├── Engine Services (scoring, dedup, verification)
    │   └── AI Services (client, interpretation, qa_engine)
    ↓
SQLAlchemy Models (app/models/*.py)
    ↓
PostgreSQL (via asyncpg) / Redis
```

### 4.2 Layer Responsibilities

| Layer | Responsibility |
|-------|---------------|
| **API** | HTTP routing, request/response handling, dependency injection (`get_db`) |
| **Schemas** | Pydantic v2 validation for every request body, query param, and response |
| **Services** | All business logic. No business logic in endpoints or models. |
| **Models** | SQLAlchemy 2.0 ORM: table definitions, relationships, column constraints |
| **DB** | Engine configuration, session management, seed data, migrations |
| **Core** | Cross-cutting concerns: config, logging, exception hierarchy |
| **Utils** | Stateless helper functions (dates, hashing, text, validators) |

---

## 5. Database Schema

Uses **PostgreSQL** with **asyncpg**, **UUID primary keys**, and **JSONB** for flexible schema fields.

### 5.1 Entity Relationship Diagram

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│    Molecule     │◄────│   Competitor    │     │     Event       │
├─────────────────┤ 1:M ├─────────────────┤     ├─────────────────┤
│ id (UUID PK)    │     │ id (UUID PK)    │◄────│ id (UUID PK)    │
│ molecule_name   │     │ molecule_id FK  │ M:1 │ molecule_id FK  │
│ reference_brand │     │ canonical_name  │     │ competitor_idFK │
│ manufacturer    │     │ tier (1-4)      │     │ event_type      │
│ search_terms    │     │ asset_code      │     │ event_subtype   │
│ indications     │     │ development_... │     │ threat_score    │
│ loe_timeline    │     │ status          │     │ traffic_light   │
│ scoring_weights │     │ primary_markets │     │ verification_...│
│ competitor_...  │────►│ launch_window   │     │ ai_summary      │
└─────────────────┘     └─────────────────┘     │ ai_why_it_...   │
       │ 1:M              │ 1:M                 │ ai_recommended..│
       │                  │                     │ ai_confidence.. │
       ▼                  ▼                     └─────────────────┘
┌─────────────────┐     ┌─────────────────┐            │ 1:M
│  SourceDocument │     │     Review      │            ▼
├─────────────────┤     ├─────────────────┤     ┌─────────────────┐
│ id (UUID PK)    │     │ id (UUID PK)    │     │ DataProvenance  │
│ molecule_id FK  │     │ event_id FK     │     ├─────────────────┤
│ source_name     │     │ reviewer_id     │     │ id (UUID PK)    │
│ source_type     │     │ review_status   │     │ event_id FK     │
│ external_id     │     │ comments        │     │ field_name      │
│ raw_payload     │     └─────────────────┘     │ raw_value       │
│ content_hash    │                             │ normalized_value│
│ processing_...  │                             │ extraction_...  │
└─────────────────┘                             │ confidence      │
                                                │ verified_by     │
                                                └─────────────────┘
```

### 5.2 Table Definitions

| Table | Description | Key Columns |
|-------|-------------|-------------|
| `molecule` | Tracked drug molecule | `molecule_name`, `reference_brand`, `manufacturer`, `search_terms` (JSONB), `indications` (JSONB), `loe_timeline` (JSONB), `competitor_universe` (JSONB), `scoring_weights` (JSONB) |
| `competitor` | Biosimilar competitor | `canonical_name`, `tier` (1-4), `asset_code`, `development_stage`, `status`, `primary_markets` (JSONB), `launch_window`, `parent_company`, `partnership_status`, `cik` |
| `event` | Intelligence event | `event_type`, `event_subtype`, `development_stage`, `indication`, `indication_priority`, `country`, `region`, `threat_score` (0-100), `traffic_light` (Green/Amber/Red), `verification_status`, `ai_summary`, `ai_why_it_matters`, `ai_recommended_action`, `ai_confidence_note` |
| `source_document` | Raw ingested data | `source_name`, `source_type`, `external_id`, `title`, `url`, `raw_payload` (JSONB), `raw_text`, `content_hash`, `processing_status` |
| `data_provenance` | Audit trail per field | `field_name`, `raw_value`, `normalized_value`, `extraction_method`, `confidence`, `verified_by` |
| `scoring_rule` | Configurable rules | `rule_name`, `rule_type`, `config` (JSONB), `version`, `is_active` |
| `review` | Human review | `event_id`, `reviewer_id`, `review_status`, `comments` |

### 5.3 Cascading Deletes

- `molecule` → `competitor` (cascade)
- `molecule` → `event`
- `molecule` → `source_document`
- `competitor` → `event`
- `source_document` → `event`
- `event` → `data_provenance` (cascade)
- `event` → `review`

---

## 6. API Contract

All routes are mounted under `/api/v1/` via `app/api/v1/router.py`.

### 6.1 Endpoint Summary

| Router | Prefix | Endpoints | Description |
|--------|--------|-----------|-------------|
| `health.py` | `/health` | `GET /` | DB + Redis health check |
| `molecules.py` | `/molecules` | `GET /`, `POST /`, `GET /{id}`, `PATCH /{id}` | Molecule CRUD |
| `competitors.py` | `/competitors` | `GET /?molecule_id=&tier=`, `POST /`, `GET /{id}` | Competitor CRUD + filter |
| `events.py` | `/events` | `GET /?filters`, `GET /{id}`, `GET /{id}/provenance`, `POST /{id}/interpret` | Event listing, detail, provenance, AI interpretation |
| `intelligence.py` | `/intelligence` | `GET /summary`, `GET /top-threats`, `GET /recent`, `POST /briefing`, `POST /ask`, `POST /briefing/email` | Intelligence aggregation, briefings, Q&A, email |
| `jobs.py` | `/jobs` | `POST /ingest/clinicaltrials`, `/ingest/ema`, `/ingest/sec-edgar`, `/ingest/fda-purple-book`, `/ingest/press-release`, `POST /recompute-scores` | Manual ingestion triggers + score refresh |
| `webhooks.py` | `/webhooks` | `POST /red-alert` | n8n webhook for Red alerts in last 24h |

### 6.2 Exception Mapping

| Exception | HTTP Status | Trigger |
|-----------|------------|---------|
| `NotFoundException` | 404 | Resource not found |
| `ValidationException` | 400 | Invalid input data |
| `AIClientException` | 502 | OpenRouter API failure |
| `IngestionException` | 502 | Data ingestion pipeline failure |

---

## 7. Services Deep Dive

### 7.1 Business Services

| Service | File | Purpose |
|---------|------|---------|
| Intelligence Service | `app/services/intelligence_service.py` | Generates department briefings (JSON) and email-ready HTML briefings with regional routing. Uses Jinja2 templates. |
| Competitor Service | `app/services/competitor_service.py` | Competitor management logic (placeholder) |
| Event Service | `app/services/event_service.py` | Event management logic (placeholder) |
| Dashboard Service | `app/services/dashboard_service.py` | Dashboard aggregation (placeholder) |
| Review Service | `app/services/review_service.py` | Review workflow (placeholder) |

### 7.2 AI Services (`app/services/ai/`)

| Service | File | Purpose |
|---------|------|---------|
| AI Client | `client.py` | OpenRouter API wrapper with primary/fallback model logic (Gemini → Claude), cost tracking. |
| Interpretation | `interpretation.py` | `InterpretationService` — generates `ai_summary`, `ai_why_it_matters`, `ai_recommended_action`, `ai_confidence_note` from verified event data only. Idempotent (`ai_interpreted_at` guard). |
| QA Engine | `qa_engine.py` | `QAEngine` — natural language Q&A using only verified database records. |

### 7.3 Engine Services (`app/services/engine/`)

| Service | File | Purpose |
|---------|------|---------|
| Scoring Engine | `scoring.py` | Deterministic threat scoring (0-100) based on: development stage (30%), competitor tier (20%), geography/LOE (20%), indication priority (15%), data confidence (10%), recency (5%). Produces traffic light: Green/Amber/Red. |
| Deduplication Engine | `deduplication.py` | Deduplication by `external_id`, `content_hash` (SHA-256), or Levenshtein fuzzy title matching (threshold ≤5). |
| Verification Engine | `verification.py` | Verifies events against required source types per event type (e.g., clinical trials need `clinicaltrials_gov` source, min confidence 0.95). Uses `rapidfuzz` for competitor name matching. |

### 7.4 Ingestion Services (`app/services/ingestion/`)

| Service | File | Status | Details |
|---------|------|--------|---------|
| ClinicalTrials | `clinicaltrials.py` | ✅ Fully Implemented | Paginated ClinicalTrials.gov API v2 ingestion. Sponsor filtering against `competitor_universe`. Indication regex extraction. Automatic dedup, verification, scoring, provenance recording. |
| Press Release | `press_release.py` | ✅ Fully Implemented | Ingests unstructured text. SHA-256 dedup. Verification + scoring. |
| EMA | `ema.py` | 📝 Placeholder | Logs "not yet implemented" |
| FDA Purple Book | `fda_purple_book.py` | 📝 Placeholder | Logs "not yet implemented" |
| SEC EDGAR | `sec_edgar.py` | 📝 Placeholder | Logs "not yet implemented" |

---

## 8. Configuration & Environment

### 8.1 Core Config (`app/core/config.py`)

`pydantic-settings` loads from `.env` and environment variables.

### 8.2 Required Environment Variables

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | Async PostgreSQL URL (`postgresql+asyncpg://...`) |
| `DATABASE_URL_DIRECT` | Sync PostgreSQL URL (`postgresql+psycopg://...`) |
| `REDIS_URL` | Redis connection string |
| `SECRET_KEY` | Application secret (min 32 chars) |
| `OPENROUTER_API_KEY` | OpenRouter API key |
| `OPENROUTER_MODEL_PRIMARY` | Primary AI model (`google/gemini-2.0-flash-001`) |
| `OPENROUTER_MODEL_FALLBACK` | Fallback AI model (`anthropic/claude-3.5-haiku`) |
| `CLINICALTRIALS_BASE_URL` | ClinicalTrials.gov API v2 base URL |
| `EMA_API_BASE_URL` | EMA API base URL |
| `SEC_EDGAR_BASE_URL` | SEC EDGAR base URL |
| `FDA_PURPLE_BOOK_URL` | FDA Purple Book URL |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASS` | Email SMTP settings |
| `EMAIL_FROM` / `DEFAULT_FROM_EMAIL` | Sender email addresses |
| `APAC_EMAIL` / `NA_EMAIL` / `EMEA_EMAIL` / `EXECUTIVE_EMAIL` | Regional distribution lists |
| `SENTRY_DSN` | Sentry error tracking DSN |
| `N8N_WEBHOOK_BASE_URL` | n8n webhook base URL |
| `API_BASE_URL` | Public API base URL |

### 8.3 Neon PostgreSQL Compatibility

Alembic and SQLAlchemy engine both filter out `sslmode`/`channel_binding` query params and explicitly pass `ssl=True` to support Neon-hosted PostgreSQL.

---

## 9. Data Flow — Ingestion to Briefing

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              DATA SOURCES                                    │
│  ClinicalTrials.gov    FDA Purple Book    EMA    SEC EDGAR    Press Releases │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         INGESTION SERVICES                                   │
│  clinicaltrials.py    fda_purple_book.py    ema.py    sec_edgar.py    pr.py  │
│  • API pagination    • Structured download   • Placeholders  • Unstructured │
│  • Sponsor filtering                                                                  │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         DEDUPLICATION ENGINE                                 │
│  1. external_id match → skip                                                │
│  2. content_hash (SHA-256) match → skip                                      │
│  3. Levenshtein fuzzy title match (≤5) → skip                                │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         VERIFICATION ENGINE                                  │
│  • Source type required per event type (e.g., clinical trials need CT.gov)   │
│  • Minimum confidence threshold (default 0.95)                               │
│  • Competitor name fuzzy matching via rapidfuzz                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         SCORING ENGINE                                       │
│  Development Stage (30%) + Competitor Tier (20%) + Geography/LOE (20%)      │
  + Indication Priority (15%) + Data Confidence (10%) + Recency (5%)          │
│  = 0-100 score → Green / Amber / Red traffic light                           │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         PROVENANCE RECORDING                                 │
│  Every extracted field → DataProvenance row with raw/normalized values,      │
│  extraction method, confidence, verified_by                                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         AI INTERPRETATION (IDEMPOTENT)                       │
│  Only runs on verified events. Guarded by `ai_interpreted_at` timestamp.     │
│  Generates: ai_summary, ai_why_it_matters, ai_recommended_action,            │
│  ai_confidence_note                                                          │
│  Model: Gemini 2.0 Flash → fallback to Claude 3.5 Haiku                      │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         INTELLIGENCE OUTPUTS                                 │
│  • REST API responses (JSON)                                                 │
│  • Department briefings (JSON + HTML email)                                  │
│  • Natural language Q&A                                                      │
│  • Red Alert webhooks → n8n → immediate regional email alerts                │
│  • Weekly digest emails with LOE dashboard + event cards                     │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 10. Testing Strategy

### 10.1 Test Organization

| Suite | Location | Count | Focus |
|-------|----------|-------|-------|
| Integration | `tests/integration/` | 18 files | End-to-end API flows, phase-based pipelines |
| Unit | `tests/unit/` | 12 files | Isolated logic, engine algorithms, utilities |

### 10.2 Phase-Based Integration Tests

| Phase | File | Coverage |
|-------|------|----------|
| Phase 2 | `test_phase2_deterministic_ingestion.py` | Full ingestion pipeline: ClinicalTrials + PR ingestion, dedup, verification, provenance, sponsor filtering, scoring reproducibility |
| Phase 3 | `test_phase3_ai_interpretation.py` | AI interpretation endpoint, idempotency, fact-grounding |
| Phase 4 | `test_phase4_department_briefings.py` | Briefing generation for departments |
| Phase 4 | `test_phase4_natural_language_qa.py` | Q&A endpoint with verified data only |
| Phase 5 | `test_phase5_email_briefing.py` | Email briefing HTML/JSON generation |
| Phase 5 | `test_phase5_red_alert_webhook.py` | Red alert webhook, 24h window, regional routing |

### 10.3 Test Configuration (`tests/conftest.py`)

- Overrides `get_db` dependency with `biosim_test` PostgreSQL database
- `setup_database` fixture: drops and recreates tables before each test
- `db_session` fixture: yields async session with rollback
- `client` fixture: `httpx.AsyncClient` with `ASGITransport`

### 10.4 Quality Gates

| Tool | Command | Gate |
|------|---------|------|
| Lint | `ruff check .` | Zero errors |
| Type Check | `mypy app` | Zero errors (strict mode) |
| Test | `pytest --cov=app --cov-report=term-missing` | ≥80% coverage |
| All | `python scripts/run_checks.py` | Sequential run of all three |

---

## 11. Deployment Architecture

### 11.1 Docker Compose (Local Development)

```yaml
Services:
  postgres:   postgres:16-alpine  (healthcheck)
  redis:      redis:7-alpine      (healthcheck)
  app:        Python 3.12 slim    (depends on both healthy, mounts ./app read-only)
```

### 11.2 Railway (Production)

| File | Purpose |
|------|---------|
| `railway.toml` | Dockerfile build, `./start.sh` start command, healthcheck at `/api/v1/health` |
| `start.sh` | Validates `DATABASE_URL` + `SECRET_KEY`, runs `alembic upgrade head` (5 retries), runs seeds idempotently, starts `uvicorn` on `$PORT` (default 8000) |
| `docker/Dockerfile` | Python 3.12 slim, installs gcc/libpq, exposes 8000, runs `./start.sh` |

### 11.3 Startup Sequence

```
start.sh
  ├── Validate required env vars
  ├── Run alembic upgrade head (retry up to 5x)
  ├── Run seeds idempotently
  └── Start uvicorn on $PORT
```

---

## 12. n8n Automation Workflows

Defined in `docs/n8n-workflows.md`.

| Workflow | Trigger | Action |
|----------|---------|--------|
| **Weekly Department Briefing** | Monday 08:00 UTC | Loops molecules, generates HTML email, routes by geography |
| **Red Alert** | Hourly cron | Checks for verified Red events in last 24h, sends immediate alerts |
| **Press Release Monitor** | Every 15 minutes | Fetches RSS/news, ingests new PRs, triggers red alert check |

---

## 13. Development Workflow

### 13.1 Quick Start

```bash
# 1. Copy environment
cp .env.example .env

# 2. Start infrastructure
docker compose up -d postgres redis

# 3. Run migrations
alembic upgrade head

# 4. Seed data
python -m app.db.seeds

# 5. Start app
uvicorn app.main:app --reload
```

### 13.2 Code Quality

```bash
# Run all checks sequentially
python scripts/run_checks.py

# Or individually:
ruff check .
mypy app
pytest --cov=app --cov-report=term-missing
```

### 13.3 Seeding

```bash
# Seed molecules
python scripts/seed_molecules.py

# Seed competitors
python scripts/seed_competitors.py
```

---

## 14. Key Architectural Decisions

1. **Deterministic-first design** — All data extraction, verification, and scoring use deterministic algorithms. AI is strictly walled off to interpretation/Q&A layers.
2. **Full provenance tracking** — Every extracted field gets a `DataProvenance` record with raw value, normalized value, extraction method, and confidence.
3. **Idempotent AI interpretation** — Events are only interpreted once (`ai_interpreted_at` timestamp guard).
4. **Regional email routing** — Built-in mapping from event country/region to APAC/NA/EMEA/Executive distribution lists.
5. **Neon PostgreSQL compatibility** — Alembic and SQLAlchemy engine both filter out `sslmode`/`channel_binding` query params and explicitly pass `ssl=True`.
6. **Comprehensive test suite** — Phase-based integration tests provide end-to-end coverage with 80% minimum coverage gate.
7. **OpenRouter abstraction** — Primary/fallback model pattern with cost tracking and graceful degradation.

---

## 15. Glossary

| Term | Definition |
|------|------------|
| **Biosimilar** | A biological product highly similar to an FDA-approved reference product with no clinically meaningful differences |
| **LOE** | Loss of Exclusivity — when patent/market exclusivity expires, opening to generic/biosimilar competition |
| **Traffic Light** | Green (low threat), Amber (medium threat), Red (high threat) |
| **Deterministic** | Rule-based, reproducible, non-AI logic |
| **Provenance** | Audit trail showing where each data point came from and how it was transformed |
| **n8n** | Open-source workflow automation tool (similar to Zapier) |

---

*This blueprint is a living document. If the project structure or architecture changes, update this file to keep it accurate.*
