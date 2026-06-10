# CLAUDE.md

## Project Overview

QueryWise — a text-to-SQL application with a semantic metadata layer. Users ask natural language questions, an LLM generates SQL using business context, executes against their database, and returns human-readable answers. The conversational Assistant enables editing the semantic layer in plain language. Answers become durable, shareable artifacts: saved queries (pinned SQL + typed params), charts, and workspace dashboards.

## Tech Stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy (async), asyncpg, pgvector, Alembic
- **Frontend:** React 19, TypeScript, Vite, Mantine UI, React Query, React Router
- **Databases:** PostgreSQL 16 with pgvector extension (app metadata), PostgreSQL 16 (sample/target DB), Google BigQuery, Databricks
- **LLM:** Provider-agnostic (Anthropic Claude, OpenAI, Ollama, Azure OpenAI)

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

The same container hosts a second database, **`opsdb`** — a deliberately hostile operational-style schema (no FKs, `tenant_id` scoping, soft deletes, int status codes, lookup tables, business-logic views, a dead `customers_bak` table) used to exercise the semantic layer compiler. Connection string: `postgresql://sample:sample_dev@sample-db:5432/opsdb`. The container runs with `pg_stat_statements` preloaded; populate query logs with `python backend/scripts/run_ops_workload.py`. Fixtures: `backend/tests/fixtures/ops_seed.sql` (+ `ops_extensions.sql`). Init scripts only apply on a fresh volume (`docker compose down -v`).

**Auto-setup** (`AUTO_SETUP_SAMPLE_DB=true`, default): On first `docker compose up`, the backend automatically creates the connection, introspects the schema, seeds all metadata (10 glossary terms, 8 metrics, 43 dictionary entries across 12 columns, 1 knowledge document), and launches background embedding generation. Logic in `app/services/setup_service.py`, called from `main.py` lifespan hook. Idempotent — safe to restart.

**Startup sequence** (in `main.py` lifespan):
1. `ensure_embedding_dimensions()` — checks vector column dimensions match `EMBEDDING_DIMENSION`, resizes + nulls stale embeddings if mismatched (handles provider switching)
2. `auto_setup_sample_db()` — connection, introspection, seeds, then launches background embedding generation (non-blocking)

For manual seeding (if auto-setup disabled): `python backend/scripts/seed_ifrs9_metadata.py`

## Backend Commands

Run from `backend/`:

```bash
pip install -e ".[llm,dev,bigquery,databricks,lineage]"  # Install all deps (add export,observability,jobs as needed)
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
├── pages/               # Route pages (Query, SavedQueries, Dashboards, Connections, Glossary, Metrics, Dictionary, Knowledge, History)
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
| `OTEL_ENABLED` | `false` | Enable OpenTelemetry tracing (console exporter, or OTLP if endpoint set) |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | — | OTLP/HTTP traces endpoint (e.g. `http://jaeger:4318/v1/traces`) |
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
| `DISABLE_AUTH` | `false` | Local-dev escape hatch — treat every request as the default admin (no login). **Never enable in production** |
| `AUTH_PROVIDER` | `local` | Interactive login backend: `local` (password + magic-link), `magic_link`, or `oidc` (registered seam, not yet implemented) |
| `JWT_SECRET` | `dev-jwt-secret-change-in-production` | HS256 signing secret for session + magic-link JWTs |
| `JWT_ACCESS_TTL_MINUTES` | `720` | Session lifetime (minutes) |
| `MAGIC_LINK_TTL_MINUTES` | `15` | Magic-link token lifetime (minutes) |
| `AUTH_COOKIE_NAME` | `qw_session` | Session cookie name (HTTP-only) |
| `AUTH_COOKIE_SECURE` | `false` | Set `true` behind TLS (HTTPS-only cookie) |
| `AUTH_COOKIE_SAMESITE` | `lax` | Session cookie SameSite (`lax`/`strict`/`none`) |
| `DEFAULT_ORG_SLUG` | `default` | Slug of the auto-created default organization |
| `DEFAULT_ADMIN_EMAIL` | `admin@querywise.local` | Bootstrapped admin user (created on boot + in migration 004) |
| `DEFAULT_ADMIN_PASSWORD` | — | If set, the bootstrapped admin gets this local-login password |

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
- **Telemetry** (`app/core/telemetry.py`): `configure_logging()` (structlog→stdlib fallback, `console`/`json`), per-request `X-Request-ID` via `ObservabilityMiddleware`, Prometheus metrics at `GET /metrics` (`setup_metrics`), and OpenTelemetry tracing via `configure_tracing()` + `start_span()` (no-op when `OTEL_ENABLED=false`). The query pipeline (`query_service.py`) emits spans for build_context → compose → validate → execute → interpret. Request id flows into logs + `AppError` responses.
- **Rate limiting** (`app/core/rate_limit.py`): in-memory `SlidingWindowRateLimiter` wired to `/query` endpoints via `install_rate_limiting` (enforces `MAX_QUERIES_PER_MINUTE`). Swap the store for Redis for multi-replica deploys.
- **Jobs** (`app/jobs/`): `JobQueue` ABC with `InProcessJobQueue` (asyncio, default) and `ArqJobQueue` (Redis). Jobs are registered by name in `registry.py`; `launch_background_embeddings` submits `"generate_embeddings"` through `get_job_queue()`. For arq, run a worker: `JOB_BACKEND=arq arq app.jobs.worker.WorkerSettings` (embedding progress then lives in the worker process).
- **Health** (`app/api/v1/endpoints/health.py`): `GET /health/live` (process) and `GET /health/ready` (DB + job queue + LLM provider, 503 on failure) for K8s probes.
- **LLM endpoints:** Azure OpenAI provider (`azure_openai`) added so the pipeline can run inside a customer VPC; registered in `provider_registry`.
- **Tests/CI:** unit tests in `backend/tests/` (no DB/LLM needed); `.github/workflows/ci.yml` installs `.[llm,dev,observability,lineage]` and runs pytest (gating) + ruff/mypy/frontend build (advisory until pre-existing lint debt is cleared). The lineage tests need `sqlglot` (the `[lineage]` extra) and `pytest.importorskip` past it otherwise. Optional deps: `pip install -e ".[observability,jobs]"`.

## Identity & auth (Phase 1)

Real users, teams, roles, and ownership. Single-tenant per deployment; isolation is by `workspace_id` (a `Team`) within the auto-created default `Organization`. `organization_id` is carried on every core table so a future managed-SaaS fleet needs no migration. Migration `004` creates the identity tables, seeds the default org/workspace/admin, backfills all existing rows, and promotes the free-text `created_by`/`user_id` columns to real `User` FKs.

- **Identity models** (`app/db/models/`): `Organization`, `User`, `Team` (= workspace), `Membership` (role `admin|editor|viewer`, ranked in `ROLE_RANK`), `ApiKey` (only the SHA-256 hash stored).
- **Primitives** (`app/core/security.py`): PBKDF2 password hashing (stdlib), HS256 JWTs with a `purpose` claim (`session` / `magic_link`), and API-key gen/hash. Dependency-light + unit-tested.
- **Request plumbing** (`app/core/auth.py`): `get_current_user` (API key → Bearer → HTTP-only `qw_session` cookie), `get_org_context` → `AuthContext` (active workspace via `X-Workspace-Id` header, else earliest membership), and `require_role(...)`. `DISABLE_AUTH=true` short-circuits to the bootstrapped admin for local dev.
- **Login** (`app/services/auth_service.py`, `app/api/v1/endpoints/auth.py`): password + magic-link, both issuing a session-cookie JWT. Magic-link delivery (email/Slack) lands in Phase 4 — the token is logged and, outside production, returned by `POST /auth/magic-link`. `app/core/auth_providers.py` is a name-keyed seam (`local`/`magic_link`/`oidc`); **OIDC is registered but not implemented**.
- **AuthZ in services** (per the existing convention): `connection_service` scopes by org+workspace and enforces role; metadata endpoints authorize through the connection (the cascade root) via `app/api/v1/deps.py` (`require_connection_read/write`, `require_column_read/write`). Non-request entry points — startup auto-setup, the MCP server, the seed script via `DISABLE_AUTH` — act under `identity_service.system_context()` (admin in the default workspace).
- **Endpoints:** `/auth/*` (login, register, magic-link request/verify, logout, me, providers), `/teams` + `/teams/{id}/members` (admin-managed), `/api-keys` (per-user, plaintext shown once).
- **Heads-up:** once auth is enforced, the current (pre-auth) frontend gets 401s — run with `DISABLE_AUTH=true` until the Phase 1 frontend (login + auth context + workspace switcher) lands.

## Durable analytics artifacts (Phase 2)

One-shot answers become saved, owned, re-runnable, shareable objects. Two milestones; migrations `005` (artifacts) and `006` (dashboards).

- **Models** (`app/db/models/`): `SavedQuery` (pinned SQL + typed `params` + `version`/`status`), `Chart` (viz config per saved query), `ResultSnapshot` (result persistence that doubles as the cache), `Dashboard` + `DashboardTile`.
- **Scoping:** saved queries / charts / snapshots are **connection-scoped** (carry `organization_id` + `connection_id`, authorize through the connection via `require_connection_read/write`), matching the semantic-layer convention. `Dashboard` is the first **workspace-scoped** artifact (`workspace_id`); its endpoints use `get_org_context` + `ctx.require_role(...)` directly (like `teams.py`), and `dashboard_service._assert_access` mirrors `connection_service._assert_access`.
- **Re-runs & cache** (`app/services/saved_query_service.py`): `render_sql` substitutes `{{param}}` placeholders with **type-safe, escaped SQL literals** (defense-in-depth atop the read-only blocklist), then `run_saved_query` is cache-first — a `ResultSnapshot` keyed by `sha256(final_sql + params + connection_id)` within `RESULT_CACHE_TTL_SECONDS` (default 300), with a `refresh` override. Execution reuses `query_service.execute_raw_sql`.
- **Dashboards** (`app/services/dashboard_service.py`): tiles run via `run_saved_query` (so they inherit connection auth + the cache). Dashboard-level **filters reuse the param system** — filter values are passed as supplied params and a tile only consumes the `{{name}}`s its SQL references. `_finalize` refreshes server-side `onupdate` timestamps after UPDATEs to avoid async lazy-load errors during response serialization.
- **Export:** client-side CSV/JSON in the frontend; backend CSV/JSON/XLSX for saved queries (XLSX needs the optional `export` extra → `openpyxl`).
- **Endpoints:** `/connections/{id}/saved-queries` (+ `/run`, `/clone`, `/export`, `/charts`), `/dashboards` (+ `/tiles`, `/layout`, `/tiles/{id}/run`).
- **Frontend:** Recharts (`components/charts/ChartView.tsx`) for viz; `react-grid-layout` for the dashboard grid; shared typed `components/common/ParamInputs.tsx` for params/filters. Charts are managed inside the saved-query view (no separate Charts page). Note: the frontend container's anonymous `node_modules` volume means new deps (recharts, react-grid-layout) need `docker compose exec frontend npm install` or an image rebuild.

## Discovery, catalog & trust (Phase 3)

Makes the semantic layer discoverable and trustworthy. Two milestones; migrations `007` (certification + versioning) and `008` (catalog lineage). **Column profiling is deferred** to a later milestone.

- **Certification lifecycle** (`app/services/versioning_service.py`): metrics, glossary terms, sample queries, and saved queries carry `status` (`draft|in_review|certified|deprecated`), an integer `version`, and `certified_by_id`/`certified_at`. Transitions go through one governed endpoint per entity (`POST /connections/{id}/{entity}/{eid}/status`); the state machine (`_ALLOWED_TRANSITIONS`) and role gate (`_ROLE_FOR_TARGET`) live in the service — **editor** submits-for-review/reverts, **admin** certifies/deprecates. Certifying runs a lightweight SQL check (`check_sql_safety` + a sqlglot parse). One service handles all four entity types via `_SNAPSHOT_FIELDS` / `_SQL_FIELD` maps.
- **Versioning & changelog** (`SemanticVersion` model): every content edit (PUT → `record_edit`, bumps version) and status transition appends an append-only snapshot. Exposed at `GET .../{entity}/{eid}/versions` (+ `/{version}`); `versioning_service.diff` gives a field-level diff. UI: shared `frontend/src/components/common/{CertificationBadge,StatusActions,VersionHistory}.tsx`, wired into the Metrics/Glossary/SavedQueries pages.
- **Catalog search** (`app/services/catalog_service.py`, `app/api/v1/endpoints/catalog.py`): `GET /connections/{id}/catalog/search` runs a hybrid search across tables, columns, metrics, glossary, sample/saved queries, and knowledge — **reusing the existing pgvector embeddings + the keyword scorer** (`semantic/relevance_scorer.py`), no tsvector. Hits merge into a uniform `CatalogHit`; certified items are boosted (`rank_hits`). `GET .../catalog/facets` returns schemas/owners/tags/type+status counts. Connection-scoped via `require_connection_read`. Frontend: `pages/CatalogPage.tsx` (search + facet sidebar + detail/lineage drawer).
- **Lineage** (`app/services/lineage_service.py`, `ArtifactDependency` model): saved-query `pinned_sql` and metric `sql_expression` are parsed with **sqlglot** (optional `[lineage]` extra; lazy import, degrades to a no-op if absent) into table/column edges, recomputed on create/update (best-effort, never blocks the write). Per-artifact "what this touches" at `GET .../{saved-queries|metrics}/{id}/lineage`; impact view "what depends on this table" at `GET .../catalog/lineage?table=&column=`. Connector type → sqlglot dialect via `dialect_for`.
- **Endpoints:** `/connections/{id}/catalog/{search,facets,lineage}`, plus `/status`, `/versions`, `/versions/{v}`, and `/lineage` sub-resources on the metric/glossary/sample-query/saved-query routers.
- **Heads-up:** existing rows migrate to `status='draft'`, `version=1`. The saved-query PUT routes any `status` change through the governed lifecycle (no raw status writes). sqlglot is a new optional dep — install the `[lineage]` extra (or rebuild the backend image) for lineage to populate.

## Semantic layer compiler (Slice 1)

Attacks the cold-start problem: point QueryWise at an operational DB with an empty semantic layer and get reviewable draft objects. Migration `013`.

- **Engine** (`app/semantic_compiler/`): self-contained package (dataclasses + pure functions, no FastAPI/ORM imports — standalone-CLI extractable). Collectors gather evidence (catalog via the connector, `pg_stats`/CHECK/enums/unique indexes, `pg_get_viewdef`, `pg_stat_statements`); `sqlmeta.py` (sqlglot, graceful degradation) extracts join pairs/aggregates/GROUP BY/WHERE; inference modules emit `Finding`s with evidence + confidence: **join inference without FKs** (naming + value-overlap probe + log co-occurrence; failed probe kills the candidate), dictionaries (enum/CHECK/lookup-table labels/most_common_vals — note pg_stats `n_distinct` is negative when it scales with rows), view→metric extraction, recurring log aggregates, dead tables, tenant scoping (call-weighted log confirmation required), PII (name + sampled value shape), fan-out warnings (1:N parent-measure double-count). The LLM pass (`app/llm/agents/semantic_annotator.py`) only names/describes — output merges onto naming fields, never structure; runs fine without a provider. Output is hard-capped per kind (`Thresholds`) — review fatigue kills draft tools.
- **Staging, not drafts** (`CompilationRun`/`CompilationFinding`, `app/services/compilation_service.py`): findings never touch semantic tables until accepted (draft metrics/glossary feed the context builder today). Accept dispatches per kind through existing creation paths (embed + lineage), landing as `status='draft'`; policies (`PII masking`, `dead tables`, row filters) are created **disabled**; fan-out guidance becomes a knowledge doc (so the prompt assembler picks it up via RAG). Runs as a background job (`semantic_compilation`) with progress (`compilation_progress.py`).
- **Rematerialization:** `introspect_and_cache` wipes cached tables (cascading to inferred relationships + dictionary entries), so accepted findings are **name-keyed** and `rematerialize_accepted` re-creates them after every introspect. `cached_relationships` gained `origin` (`fk|inferred`), `confidence`, `cardinality`, `evidence`.
- **Endpoints:** `/connections/{id}/compilation/runs` (+ `/runs/{rid}`), `/compilation/findings` (+ `/{fid}/accept`, `/{fid}/dismiss`, `/bulk`). Frontend: `pages/CompilerPage.tsx` (run button, progress, findings grouped by kind with evidence + confidence, bulk accept/dismiss).
- **Eval:** `python backend/scripts/eval_compiler_ifrs9.py` scores recovery of the IFRS 9 seed metadata with FKs hidden (`ignore_declared_fks`). Baseline: relationships 5/5 @ 100% precision, dictionary 79%/89%, glossary table-coverage 10/10; metrics need views/logs (sampledb has neither — expected 0).
- **Heads-up:** `pg_stats` is empty until ANALYZE; `pg_stat_statements` needs the extension + read rights (`pg_read_all_stats`). Every collector degrades to empty and the run records `sources_available` so the UI explains reduced confidence. Collectors are Postgres-only for now — other connectors compile catalog-only.

## Packaging & deployability (parallel track)

Production deployment artifacts under `deploy/` (+ root prod compose), separate from the dev `docker-compose.yml` / `Dockerfile`s (which stay untouched for local work). The whole **Packaging & deployability** parallel track from `planfull.md` is complete: hardened images, prod compose, Helm chart, Terraform for AWS + GCP + Azure, CI/CD (build/push/deploy), and ops (backup/restore, DR runbook, config reference). The only deferred item is the **SaaS control plane** (provisioning/billing/fleet upgrades), which is additive and build-on-demand. Overview: `deploy/README.md`.

- **Hardened images:** `backend/Dockerfile.prod` (multi-stage: builder venv → slim runtime, non-root uid 1001, `curl` healthcheck on `/api/v1/health/live`, `uvicorn --workers ${UVICORN_WORKERS:-4}`, prod extras only — no `[dev]`) and `frontend/Dockerfile.prod` (Vite build → `nginxinc/nginx-unprivileged:1.27-alpine`, non-root uid 101, listens 8080). `.dockerignore` in both dirs.
- **Edge:** `frontend/nginx.conf` serves the SPA bundle (with client-route fallback) and reverse-proxies `/api`, `/mcp` (buffering off for SSE), and health to the backend **same-origin**. Uses Docker's embedded resolver (`127.0.0.11`) + a `set $backend` variable `proxy_pass` so the edge boots even while the backend is starting (a static `upstream` would make nginx refuse to start). Internal `/healthz` for the container healthcheck. TLS terminates here (mount certs + add a 443 block) or upstream at a LB.
- **Same-origin build:** `frontend/src/api/client.ts` uses `?? 'http://localhost:8000'` (not `||`) so the prod build with `VITE_API_URL=""` calls the API at relative `/api/v1`; unset (dev) still falls back to the local backend.
- **Prod stack:** `docker-compose.prod.yml` — `app-db` (pgvector, no host port), `redis` (cache + arq), one-shot `migrate` (`alembic upgrade head`, gated by `service_completed_successfully` so backend replicas never race), `backend` (uvicorn, `JOB_BACKEND=arq`), `worker` (`arq app.jobs.worker.WorkerSettings`), `frontend` (edge, the only published port). Run: `cp .env.prod.example .env.prod` → edit → `docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build`.
- **Config:** `.env.prod.example` is the prod-tuned template (CHANGE_ME secrets, `DISABLE_AUTH=false`, `AUTH_COOKIE_SECURE=true`, `LOG_FORMAT=json`, `AUTO_SETUP_SAMPLE_DB=false`). `.env.prod` is gitignored.
- **Helm chart** (`deploy/helm/querywise/`, EKS/GKE/AKS): backend Deployment (uvicorn) + HPA + PDB, dedicated arq `worker` Deployment, frontend Deployment + PDB, two Services, ingress (path-based: `/api`+`/mcp`→backend, `/`→frontend SPA — same-origin), ServiceAccount (IRSA/Workload-Identity annotations). Managed Postgres+pgvector and Redis are **expected out-of-cluster** (supply DSNs via the release Secret). Config split: non-secret env → ConfigMap, secrets → chart-created Secret **or** `secrets.existingSecret` (external-secrets/sealed-secrets seam). **Migration:** `alembic upgrade head` runs as a `pre-install`/`pre-upgrade` hook Job (weight `-5`); the ConfigMap+Secret are also hooks (weight `-10`) so they exist first, and the Job gates new backend pods so replicas never race. Validate: `helm lint` + `helm template ... | kubeconform -strict` (both pass). `values-production.example.yaml` is a realistic override; `deploy/README.md` has the install flow.
- **Terraform** (`deploy/terraform/{aws,gcp,azure}/`): each provisions the **data plane + secrets** the chart consumes, in the customer's own account/VPC, with the **same shape** — managed Postgres 16 (pgvector via app migrations) + managed Redis (cache + arq) + a secret store holding the assembled DSNs+keys (keys map 1:1 to backend env → external-secrets `dataFrom` into the `querywise-secrets` k8s Secret) + object storage (exports/backups) + optional network + an identity/policy for external-secrets to read the secret. DB password + JWT secret auto-generate if unset; `ENCRYPTION_KEY` is required (Fernet). **Compute (EKS/GKE/AKS) is deliberately out of scope** — BYO or the upstream cluster module, kept in a separate state so cluster rebuilds never risk the DB.
  - **AWS:** RDS (Multi-AZ, gp3, `rds.force_ssl`) + ElastiCache + Secrets Manager + S3; IAM policy for the external-secrets IRSA role.
  - **GCP:** Cloud SQL (private IP via PSA peering) + Memorystore + Secret Manager + GCS; a service account with `secretAccessor` for Workload Identity.
  - **Azure:** Postgres flexible server (VNet-integrated, `azure.extensions=VECTOR` allow-list) + Cache for Redis + Key Vault + Blob; a user-assigned managed identity with Key Vault read for Workload Identity.
  - All three pass `tofu/terraform validate` + `fmt`. `*.tfvars` gitignored; lockfiles committed.
- **CI/CD** (`.github/workflows/`): `ci.yml` (existing — backend tests gating + advisory lint/type, frontend lint/build) is unchanged. **`deploy-validate.yml`** runs on PRs touching `deploy/**` — `helm lint` + `helm template | kubeconform -strict`, and `terraform fmt -check`/`validate` across aws/gcp/azure (matrix). **`release.yml`** builds+pushes both images to GHCR (`querywise-{backend,frontend}`, tagged SHA/branch/semver/latest, gha cache) then deploys via the `.github/actions/helm-deploy` composite action: push to `main` → **staging**, tag `v*` → **production** (gate with environment required-reviewers). Deploys pin the release to the commit SHA with `--wait --atomic` (auto-rollback) and inject only image coords; per-env overlay `values-<environment>.yaml` (committed, non-secret) is applied if present. Each environment needs a `KUBE_CONFIG` secret (base64 kubeconfig); clusters run external-secrets to sync `querywise-secrets`. Lint with `actionlint`.
- **Ops** (`deploy/ops/`): `backup.sh` (`pg_dump` custom format → AES-256/openssl PBKDF2 → `querywise-<ts>.dump.enc`, optional S3/GCS upload, local retention prune) + `restore.sh` (decrypt → `pg_restore --clean --if-exists`, guarded by `RESTORE_CONFIRM=yes`); both strip the `+asyncpg` suffix from `DATABASE_URL`, shellcheck-clean. `backup-cronjob.example.yaml` schedules backups in-cluster (postgres:16 image, script via ConfigMap, `BACKUP_PASSPHRASE`+`DATABASE_URL` from `querywise-secrets`). `RUNBOOK.md` covers backup/restore, managed-DB PITR, full-region DR rebuild, the Alembic upgrade path (migrations only run via the Helm/compose migrate hook), and quarterly credential rotation — **`ENCRYPTION_KEY` must not be blind-rotated** (it Fernet-encrypts stored connection strings; re-encrypt each connection before swapping). `config-reference.md` is the production-focused settings catalogue (the full list is in the env-vars table above / `.env.example`).
