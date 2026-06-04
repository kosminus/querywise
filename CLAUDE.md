# CLAUDE.md

## Project Overview

QueryWise — a text-to-SQL application with a semantic metadata layer. Users ask natural language questions, an LLM generates SQL using business context, executes against their database, and returns human-readable answers.

## Tech Stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy (async), asyncpg, pgvector, Alembic
- **Frontend:** React 19, TypeScript, Vite, Mantine UI, React Query, React Router
- **Databases:** PostgreSQL 16 with pgvector extension (app metadata), PostgreSQL 16 (sample/target DB), Google BigQuery, Databricks
- **LLM:** Provider-agnostic (Anthropic Claude, OpenAI, Ollama)

## How to Run

```bash
# Full stack with Docker (preferred)
docker compose up

# Frontend: http://localhost:5173
# Backend:  http://localhost:8000
# API docs: http://localhost:8000/docs

# The IFRS 9 sample DB is auto-configured on startup (connection, introspection, metadata seeding).
# To disable: set AUTO_SETUP_SAMPLE_DB=false in .env
# For manual seeding (if auto-setup is disabled):
python backend/scripts/seed_ifrs9_metadata.py
```

## Sample Database

The sample-db contains an **IFRS 9 banking schema** with 6 tables: `counterparties`, `facilities`, `exposures`, `ecl_provisions`, `collateral`, `staging_history`. Connection string (from Docker): `postgresql://sample:sample_dev@sample-db:5432/sampledb`.

**Auto-setup** (`AUTO_SETUP_SAMPLE_DB=true`, default): On first `docker compose up`, the backend automatically creates the connection, introspects the schema, seeds all metadata (10 glossary terms, 8 metrics, 43 dictionary entries across 12 columns, 1 knowledge document), and launches background embedding generation. Logic in `app/services/setup_service.py`, called from `main.py` lifespan hook. Idempotent — safe to restart.

**Startup sequence** (in `main.py` lifespan):
1. `ensure_embedding_dimensions()` — checks vector column dimensions match `EMBEDDING_DIMENSION`, resizes + nulls stale embeddings if mismatched (handles provider switching)
2. `auto_setup_sample_db()` — connection, introspection, seeds, then launches background embedding generation (non-blocking)

For manual seeding (if auto-setup disabled): `python backend/scripts/seed_ifrs9_metadata.py`

## Backend Commands

Run from `backend/`:

```bash
pip install -e ".[llm,dev,bigquery,databricks]"  # Install all deps
alembic upgrade head                  # Run migrations
uvicorn app.main:app --reload         # Dev server on :8000
pytest                                # Run tests
ruff check .                          # Lint
ruff format .                         # Format
mypy .                                # Type check
```

## Frontend Commands

Run from `frontend/`:

```bash
npm install                           # Install deps
npm run dev                           # Dev server on :5173
npm run build                         # Production build (tsc + vite)
npm run lint                          # ESLint
```

## Code Style

- **Python:** Ruff, 100 char line length, Python 3.11 target, rules: E, F, I, N, UP, B
- **TypeScript:** ESLint, strict mode, no explicit `any`
- **Async everywhere:** All DB operations, HTTP calls, and LLM calls are async
- **Pytest:** asyncio_mode="auto", test paths at `tests/`

## Key Directories

```
backend/
├── scripts/             # Seed scripts (seed_ifrs9_metadata.py)
backend/app/
├── api/v1/endpoints/    # FastAPI route handlers (all under /api/v1)
├── api/v1/schemas/      # Pydantic request/response models
├── connectors/          # Database connector plugin system (PostgreSQL, BigQuery, Databricks)
├── db/models/           # SQLAlchemy ORM models (UUID PKs, timestamps)
├── llm/agents/          # LLM agents (composer, validator, interpreter, error handler)
├── llm/providers/       # LLM provider implementations (anthropic, openai, ollama)
├── llm/prompts/         # System/user prompt templates
├── llm/utils.py         # Shared LLM utilities (JSON repair for local models)
├── mcp/                 # FastMCP server mounted at /mcp (streamable HTTP) — reuses services
├── semantic/            # Core IP: context builder, schema linker, glossary resolver, knowledge resolver
├── services/            # Business logic (query pipeline, connection mgmt, embeddings, knowledge import)
└── utils/               # SQL sanitizer

frontend/src/
├── api/                 # Axios API clients (one per resource)
├── components/layout/   # AppShell with sidebar navigation
├── hooks/               # React Query hooks
├── pages/               # Route pages (Query, Connections, Glossary, Metrics, Dictionary, Knowledge, History)
└── types/               # TypeScript interfaces matching backend schemas
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://querywise:querywise_dev@localhost:5432/querywise` | App metadata DB |
| `ENCRYPTION_KEY` | `dev-encryption-key-change-in-production` | Fernet key for connection strings (used by the `env` secrets backend) |
| `SECRETS_BACKEND` | `env` | Secrets backend for connection-string encryption (`env`/`aws`/`gcp`/`azure`/`vault`) |
| `LOG_LEVEL` | `INFO` | Log level |
| `LOG_FORMAT` | `console` | Log format (`console`, or `json` for log aggregation) |
| `ENABLE_METRICS` | `true` | Expose Prometheus metrics at `GET /metrics` |
| `JOB_BACKEND` | `inprocess` | Background job runner (`inprocess` asyncio, or `arq` Redis) |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis URL (used when `JOB_BACKEND=arq`) |
| `RATE_LIMIT_ENABLED` | `true` | Enforce `MAX_QUERIES_PER_MINUTE` on `/query` endpoints |
| `DEFAULT_LLM_PROVIDER` | `anthropic` | LLM provider (`anthropic`, `openai`, `ollama`, `azure_openai`) |
| `DEFAULT_LLM_MODEL` | `claude-sonnet-4-20250514` | Default model for SQL generation |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | OpenAI embedding model |
| `CORS_ORIGINS` | `["http://localhost:5173"]` | Allowed CORS origins |
| `AUTO_SETUP_SAMPLE_DB` | `true` | Auto-create sample DB connection + seed metadata on startup |
| `SAMPLE_DB_CONNECTION_STRING` | `postgresql://sample:sample_dev@sample-db:5432/sampledb` | Sample DB for auto-setup |
| `OLLAMA_BASE_URL` | `http://host.docker.internal:11434` | Ollama server URL (use `http://ollama:11434` for Docker Ollama) |
| `OLLAMA_MODEL` | `llama3.1:8b` | Ollama model for completions |
| `OLLAMA_EMBEDDING_MODEL` | `nomic-embed-text` | Ollama model for embeddings |
| `EMBEDDING_DIMENSION` | `1536` | Vector dimension (1536 for OpenAI, 768 for Ollama nomic-embed-text) |
| `ANTHROPIC_API_KEY` | — | Required if using Anthropic |
| `OPENAI_API_KEY` | — | Required if using OpenAI (completions + embeddings) |
| `AZURE_OPENAI_ENDPOINT` | — | Azure OpenAI endpoint (required for `azure_openai` provider) |
| `AZURE_OPENAI_API_KEY` | — | Azure OpenAI key |
| `AZURE_OPENAI_API_VERSION` | `2024-10-21` | Azure OpenAI API version |
| `AZURE_OPENAI_DEPLOYMENT` | — | Azure OpenAI embedding deployment name |

## Ollama (Local LLM)

When using Ollama, all completions and embeddings go through Ollama — no OpenAI/Anthropic fallback. Two deployment modes:

### Option A: Native Ollama on macOS (recommended — GPU-accelerated via Metal)

```bash
# 1. Install and start Ollama on your Mac
brew install ollama
ollama serve

# 2. Pull required models
ollama pull llama3.1:8b
ollama pull nomic-embed-text

# 3. Set .env
DEFAULT_LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_MODEL=llama3.1:8b
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_DIMENSION=768

# 4. Start stack (Ollama is NOT in Docker — backend reaches it via host.docker.internal)
docker compose up
```

### Option B: Ollama in Docker (CPU-only, fully self-contained)

```bash
# .env
DEFAULT_LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_MODEL=llama3.1:8b
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_DIMENSION=768

# Start stack with Ollama Docker profile
docker compose --profile ollama-docker up

# Pull required models inside the container
docker compose exec ollama ollama pull llama3.1:8b
docker compose exec ollama ollama pull nomic-embed-text
```

> **Why Option A is faster on macOS:** Docker on Mac runs inside a Linux VM with no GPU passthrough. Native Ollama uses Apple Metal for GPU-accelerated inference. Expect ~5-10x faster responses.

### Embedding dimension

`nomic-embed-text` produces **768**-dimension vectors. Set `EMBEDDING_DIMENSION=768` in `.env`. Migration `002_configurable_embedding_dim` handles initial column creation. On subsequent provider switches, `ensure_embedding_dimensions()` (in `setup_service.py`, called from `main.py` lifespan) detects dimension mismatches at startup, resizes all vector columns, and nulls stale embeddings so they regenerate in the background.

### Embedding generation

Embeddings are generated in **background asyncio tasks** (non-blocking):
- **On startup:** after auto-setup seeds, `launch_background_embeddings()` fires a background task
- **On introspect:** background task launched after schema introspection
- **On CRUD:** each create/update of glossary term, metric, sample query, or knowledge document embeds inline
- **Progress tracking:** in-memory tracker (`embedding_progress.py`), exposed at `GET /api/v1/embeddings/status`, displayed as a frontend progress banner (auto-polls every 2s, auto-hides when complete)

### Graceful degradation

If the embedding model is unavailable (not pulled, or Ollama is down), the query pipeline falls back to keyword-only context matching instead of crashing. Vector search failures in `schema_linker.py` trigger a session rollback and keyword fallback. Embedding-based search resumes automatically once the model is available.

### Key implementation details

- `OllamaProvider` (`app/llm/providers/ollama_provider.py`) uses `httpx` to call Ollama REST API
- Completions use `format: "json"` to force JSON output mode
- `repair_json()` in `app/llm/utils.py` handles common local model JSON issues (markdown fences, Python booleans, trailing commas)
- Embeddings: tries `/api/embed` (Ollama 0.4+), falls back to `/api/embeddings` (legacy) automatically
- `get_embedding_provider()` follows the configured provider — Ollama embeds locally, Anthropic falls back to OpenAI

## Architecture Conventions

- **Connectors:** Extend `BaseConnector` ABC in `app/connectors/`, register in `connector_registry.py`. Built-in: PostgreSQL (`asyncpg`), BigQuery (`google-cloud-bigquery`, lazy-loaded), Databricks (`databricks-sql-connector`, lazy-loaded). BigQuery uses service account JSON stored encrypted in connection_string field. Databricks uses JSON config (`server_hostname`, `http_path`, `access_token`, `catalog`) stored encrypted; supports both Unity Catalog (INFORMATION_SCHEMA) and Hive metastore (SHOW/DESCRIBE fallback)
- **LLM Providers:** Extend `BaseLLMProvider` ABC in `app/llm/providers/`, register via `provider_registry`
- **API routes:** All under `/api/v1`, defined in `app/api/v1/endpoints/`, aggregated in `app/api/v1/router.py`
- **ORM models:** UUID primary keys, `created_at`/`updated_at` timestamps, pgvector `VECTOR(settings.embedding_dimension)` for embeddings
- **Services:** Business logic in `app/services/`, never in endpoints directly
- **Knowledge:** Import text/HTML content, auto-detect HTML, section-aware chunking (450 words, 80 overlap), vector + keyword search for relevant chunks injected into LLM prompt. URL fetching server-side via `httpx`. Service in `app/services/knowledge_service.py`
- **SQL safety:** Read-only transactions enforced at connector level, static SQL blocklist in `app/utils/sql_sanitizer.py` (includes BigQuery-specific `EXPORT DATA` / `LOAD DATA` and Databricks-specific `COPY INTO` / `OPTIMIZE` / `VACUUM` blocks)

## Platform plumbing (Phase 0)

Foundational layers added under `app/core/` and `app/jobs/`. All optional
dependencies degrade gracefully — the app boots without `structlog` /
`prometheus_client` installed.

- **Secrets** (`app/core/secrets.py`): `SecretsProvider` ABC behind connection-string encryption. Default `env` backend = Fernet (preserves original behaviour); `aws`/`gcp`/`azure`/`vault` are registered seams (`register_secrets_backend`). `connection_service.py` calls `get_secrets_provider()`.
- **Telemetry** (`app/core/telemetry.py`): `configure_logging()` (structlog→stdlib fallback, `console`/`json`), per-request `X-Request-ID` via `ObservabilityMiddleware`, Prometheus metrics at `GET /metrics` (`setup_metrics`). Request id flows into logs + `AppError` responses.
- **Rate limiting** (`app/core/rate_limit.py`): in-memory `SlidingWindowRateLimiter` wired to `/query` endpoints via `install_rate_limiting` (enforces `MAX_QUERIES_PER_MINUTE`). Swap the store for Redis for multi-replica deploys.
- **Jobs** (`app/jobs/`): `JobQueue` ABC + `InProcessJobQueue` (asyncio, default) with an `arq`/Redis seam. `launch_background_embeddings` submits through `get_job_queue()`.
- **Health** (`app/api/v1/endpoints/health.py`): `GET /health/live` (process) and `GET /health/ready` (DB + job queue + LLM provider, 503 on failure) for K8s probes.
- **LLM endpoints:** Azure OpenAI provider (`azure_openai`) added so the pipeline can run inside a customer VPC; registered in `provider_registry`.
- **Tests/CI:** unit tests in `backend/tests/` (no DB/LLM needed); `.github/workflows/ci.yml` runs pytest (gating) + ruff/mypy/frontend build (advisory until pre-existing lint debt is cleared). Optional deps: `pip install -e ".[observability,jobs]"`.
