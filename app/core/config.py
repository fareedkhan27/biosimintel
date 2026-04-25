from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_ENV: str = "dev"
    SECRET_KEY: str = "change-me-min-32-chars-change-me-now"
    DEBUG: bool = False

    DATABASE_URL: str = "postgresql+asyncpg://biosim:biosim@localhost:5432/biosim"
    DATABASE_URL_DIRECT: str = "postgresql+psycopg://biosim:biosim@localhost:5432/biosim"
    REDIS_URL: str = "redis://localhost:6379/0"

    OPENROUTER_API_KEY: str = ""
    OPENROUTER_MODEL_PRIMARY: str = "google/gemini-2.0-flash-001"
    OPENROUTER_MODEL_FALLBACK: str = "anthropic/claude-3.5-haiku"

    CLINICALTRIALS_BASE_URL: str = "https://clinicaltrials.gov/api/v2/studies"
    EMA_API_BASE_URL: str = "https://www.ema.europa.eu/en/documents/report/medicines-output-medicines_json-report_en.json"
    SEC_EDGAR_BASE_URL: str = "https://data.sec.gov"
    SEC_EDGAR_TICKERS_URL: str = "https://www.sec.gov/files/company_tickers.json"
    SEC_EDGAR_SUBMISSIONS_URL: str = "https://data.sec.gov/submissions/CIK"
    SEC_EDGAR_USER_AGENT: str = "Biosim/1.0 (your-email@example.com)"
    FDA_PURPLE_BOOK_URL: str = "https://purplebooksearch.fda.gov"
    API_BASE_URL: str = "https://api.biosimintel.com"

    EMA_EPAR_ENABLED: bool = True
    EMA_EPAR_ENDPOINT: str = "https://www.ema.europa.eu/en/medicines"
    EMA_EPAR_POLL_HOUR_UTC: int = 6

    OPENFDA_ENABLED: bool = True
    OPENFDA_API_BASE_URL: str = "https://api.fda.gov"
    OPENFDA_POLL_HOUR_UTC: int = 7

    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASS: str = ""
    EMAIL_FROM: str = "intelligence@biosim.platform"

    APAC_EMAIL: str = "apac-team@example.com"
    NA_EMAIL: str = "na-team@example.com"
    EMEA_EMAIL: str = "emea-team@example.com"
    EXECUTIVE_EMAIL: str = "exec-team@example.com"
    DEFAULT_FROM_EMAIL: str = "intelligence@biosimintel.com"

    BRIEFING_RECIPIENT: str = ""
    BRIEFING_CC: str = ""

    SENTRY_DSN: str = ""
    RESEND_API_KEY: str = ""


settings = Settings()
