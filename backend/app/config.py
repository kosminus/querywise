from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Application
    app_name: str = "QueryWise"
    environment: str = "development"
    debug: bool = False
    api_prefix: str = "/api/v1"

    # App database (stores metadata, glossary, etc.)
    database_url: str = "postgresql+asyncpg://querywise:querywise_dev@localhost:5432/querywise"

    # Security
    encryption_key: str = "dev-encryption-key-change-in-production"
    # Secrets backend for encrypting connection strings at rest:
    # env (default, Fernet) | aws | gcp | azure | vault
    secrets_backend: str = "env"
    cors_origins: list[str] = ["http://localhost:5173"]

    # Observability
    log_level: str = "INFO"
    log_format: str = "console"  # console | json (json for production/log aggregation)
    enable_metrics: bool = True  # expose Prometheus /metrics
    service_name: str = "querywise-backend"
    # OpenTelemetry tracing (off by default — no exporter connections attempted).
    otel_enabled: bool = False
    # OTLP/HTTP traces endpoint, e.g. http://jaeger:4318/v1/traces. When unset
    # while otel is enabled, spans are printed to stdout (ConsoleSpanExporter).
    otel_exporter_otlp_endpoint: str | None = None

    # Background jobs
    job_backend: str = "inprocess"  # inprocess (asyncio) | arq (Redis)
    redis_url: str = "redis://localhost:6379/0"

    # Scheduling & notifications (Phase 4 — Milestone 2)
    # The in-process scheduler loop claims due schedules and dispatches report
    # jobs. Disable when a separate process owns scheduling, or in tests.
    scheduler_enabled: bool = True
    scheduler_tick_seconds: int = 60  # how often the loop scans for due schedules
    # Public base URL of the frontend, used to build links in delivered reports
    # and magic-link emails. Falls back to the first CORS origin when unset.
    app_base_url: str | None = None
    # Email (SMTP) delivery. When smtp_host is unset, email degrades to logging.
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool = True  # STARTTLS
    smtp_from: str = "querywise@localhost"
    # Slack delivery via an Incoming Webhook URL. Unset → Slack degrades to log.
    slack_webhook_url: str | None = None

    # Cost attribution pricing (Phase 4 — Milestone 4). Estimates only; tune to
    # your contract. BigQuery on-demand is ~$6.25 / TiB scanned.
    cost_per_tib_scanned_usd: float = 6.25
    cost_per_slot_ms_usd: float = 0.0
    cost_per_dbu_usd: float = 0.0
    # Fallback when no warehouse stats are reported (e.g. PostgreSQL): a rough
    # per-second compute estimate. 0 = no time-based cost.
    cost_per_second_usd: float = 0.0

    # Query defaults
    default_query_timeout_seconds: int = 30
    default_max_rows: int = 1000
    max_retry_attempts: int = 3
    # Result-cache freshness window for saved-query runs / dashboards.
    result_cache_ttl_seconds: int = 300

    # LLM defaults
    default_llm_provider: str = "anthropic"
    default_llm_model: str = "claude-sonnet-4-20250514"
    embedding_model: str = "text-embedding-3-small"

    # Ollama settings (used when default_llm_provider = "ollama")
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    ollama_embedding_model: str = "nomic-embed-text"

    # Azure OpenAI settings (used when default_llm_provider = "azure_openai").
    # Lets the whole pipeline run inside a customer VPC against Azure OpenAI.
    azure_openai_endpoint: str | None = None
    azure_openai_api_key: str | None = None
    azure_openai_api_version: str = "2024-10-21"
    azure_openai_deployment: str | None = None

    # Rate limiting
    max_queries_per_minute: int = 30
    rate_limit_enabled: bool = True

    # Authentication & identity (Phase 1)
    # Master switch for local dev: when true, every request is treated as a
    # synthetic admin user — no login required. NEVER enable in production.
    disable_auth: bool = False
    # Auth provider for interactive login: local (password) | magic_link | oidc.
    # `local` and `magic_link` are implemented; `oidc` is a registered seam.
    auth_provider: str = "local"
    # JWT signing — sessions are stateless HS256 tokens delivered as a cookie.
    jwt_secret: str = "dev-jwt-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_ttl_minutes: int = 60 * 12  # session lifetime
    magic_link_ttl_minutes: int = 15  # magic-link token lifetime
    # Session cookie delivery (HTTP-only; Secure should be true behind TLS).
    auth_cookie_name: str = "qw_session"
    auth_cookie_secure: bool = False  # set true in production (HTTPS only)
    auth_cookie_samesite: str = "lax"  # lax | strict | none
    auth_cookie_domain: str | None = None
    # Default organization + first admin, created on boot (and in migration 004).
    default_org_name: str = "Default Organization"
    default_org_slug: str = "default"
    default_workspace_name: str = "Default Workspace"
    default_admin_email: str = "admin@querywise.local"
    # When set, the bootstrapped admin gets this password (local login).
    default_admin_password: str | None = None
    # OIDC seam (not implemented yet — placeholders for the provider stub).
    oidc_issuer: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: str | None = None
    oidc_redirect_url: str | None = None

    # Context builder
    max_context_tables: int = 8
    max_sample_queries: int = 3
    embedding_dimension: int = 1536

    # Auto-setup sample database on startup
    auto_setup_sample_db: bool = True
    sample_db_connection_string: str = (
        "postgresql://sample:sample_dev@sample-db:5432/sampledb"
    )


settings = Settings()
