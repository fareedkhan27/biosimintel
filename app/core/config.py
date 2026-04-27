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
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPENROUTER_ENABLED: bool = False
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

    PUBMED_ENABLED: bool = True
    PUBMED_API_BASE_URL: str = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    PUBMED_API_KEY: str = ""
    PUBMED_POLL_DAY: str = "monday"
    PUBMED_LOOKBACK_DAYS: int = 14

    USPTO_ENABLED: bool = True
    USPTO_API_BASE_URL: str = "https://api.patentsview.org"
    USPTO_POLL_DAY: str = "tuesday"
    USPTO_LOOKBACK_DAYS: int = 14

    EPO_ENABLED: bool = True
    EPO_OPS_BASE_URL: str = "https://ops.epo.org/3.2/rest-services"
    EPO_POLL_DAY: str = "wednesday"
    EPO_LOOKBACK_DAYS: int = 14

    WHO_ICTRP_ENABLED: bool = True
    WHO_ICTRP_BASE_URL: str = "https://www.who.int/clinical-trials-registry-platform"
    WHO_ICTRP_POLL_DAY: int = 1
    WHO_ICTRP_DOWNLOAD_TIMEOUT: int = 120

    PRESS_RELEASE_ENABLED: bool = True
    PRESS_RELEASE_AUTO_VERIFY_THRESHOLD: int = 80
    PRESS_RELEASE_NOISE_EXPIRY_DAYS: int = 7

    EU_CTIS_ENABLED: bool = True
    EU_CTIS_BASE_URL: str = "https://euclinicaltrials.eu"
    EU_CTIS_POLL_DAY: str = "thursday"
    EU_CTIS_MAX_PAGES: int = 5

    SOCIAL_MEDIA_ENABLED: bool = True
    SOCIAL_MEDIA_MAX_CONFIDENCE: int = 55  # Hard cap — never auto-verifies
    SOCIAL_MEDIA_NOISE_EXPIRY_DAYS: int = 7

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
