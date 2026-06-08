# QueryWise

A full-stack application that translates natural language questions into SQL queries. It uses a **semantic metadata layer** — business glossary, metrics definitions, data dictionary, and schema context — to give LLMs the context they need to generate accurate SQL against your databases.

[![QueryWise Demo](https://img.youtube.com/vi/nCq6MPodI5I/maxresdefault.jpg)](https://www.youtube.com/watch?v=nCq6MPodI5I)

```
┌─────────────────────────────────────────────┐
│        FRONTEND (React + TypeScript)        │
│  Query Interface │ Semantic Layer Mgmt UI   │
└────────────────────┬────────────────────────┘
                     │ REST API
┌────────────────────▼────────────────────────┐
│           BACKEND (FastAPI)                 │
│                                             │
│  ┌─────────────────────────────────────┐    │
│  │  SEMANTIC LAYER                     │    │
│  │  Context Builder → Prompt Assembler │    │
│  │  (embedding search + keyword match) │    │
│  └──────────────┬──────────────────────┘    │
│                 │                            │
│  ┌──────────────▼──────────────────────┐    │
│  │  LLM ORCHESTRATION                  │    │
│  │  Router → Composer → Validator →    │    │
│  │  Executor → Interpreter → ErrorLoop │    │
│  └──────────────┬──────────────────────┘    │
│                 │                            │
│  ┌──────────────▼──────────────────────┐    │
│  │  CONNECTOR LAYER (plugin system)    │    │
│  │  BaseConnector → PG, BQ, Databricks│   │
│  └─────────────────────────────────────┘    │
└─────────────────────────────────────────────┘
```

## Features

- **Natural language to SQL** — ask questions in plain English, get SQL + results + explanations
- **Semantic metadata layer** — business glossary, metric definitions, data dictionary, knowledge base, sample queries
- **Knowledge import** — import documentation (Confluence, wikis, HTML pages) to inject relevant business context into SQL generation
- **Hybrid context selection** — embedding similarity + keyword matching + foreign key graph traversal
- **Multi-provider LLM** — Anthropic Claude, OpenAI, Ollama (provider-agnostic design)
- **4 specialized LLM agents** — Query Composer, SQL Validator, Result Interpreter, Error Handler
- **Intelligent routing** — routes simple/moderate/complex queries to appropriate models
- **Plugin connector system** — PostgreSQL, BigQuery, and Databricks built-in, extensible to MySQL, Snowflake, and more
- **Security by default** — read-only query execution, SQL blocklist, encrypted connection strings
- **Query history** — full execution log with favorites, retry counts, token usage
- **Schema introspection** — auto-discovers tables, columns, types, relationships from target databases
- **Conversational Assistant** — chat panel for NL queries and semantic layer editing (glossary terms, metrics, dictionary entries, knowledge)
- **Identity, teams, and ownership** — real users, roles (viewer/editor), teams, and workspace-based ownership
- **Saved queries** — name and pin a question + SQL with typed parameters (`{{region}}`); re-run, version, clone, and export (CSV/JSON/XLSX)
- **Charts & result caching** — visualize a saved query (line/bar/area/pie/scatter via Recharts); results are snapshotted to a Postgres cache so re-runs don't re-hit the warehouse
- **Dashboards** — compose saved queries into a shareable, draggable tile grid with dashboard-level filters that flow into every tile's SQL
- **Certification & versioning** — govern metrics, glossary, and saved queries through a `draft → in_review → certified → deprecated` lifecycle (editors submit, admins certify) with a per-entity version history and changelog
- **Data catalog** — hybrid search (embeddings + keyword) across tables, columns, metrics, glossary, and knowledge, with facets and certified-first ranking
- **Lineage** — sqlglot parses saved-query/metric SQL to show what each touches and what depends on a given table (impact view)
- **Production hardening** — rate limiting, async job queue, OpenTelemetry tracing, structured logging, health probes
- **Deploy anywhere** — hardened non-root images, a production Docker Compose stack, a Helm chart (HPA/PDB/ingress/migration hook), Terraform for AWS/GCP/Azure (managed Postgres+pgvector, Redis, secrets, in your own VPC), GitHub Actions CI/CD (build → staging → prod), and ops tooling (encrypted backup/restore + DR runbook) — see [`deploy/`](deploy/)


---

## Quick Start

### Prerequisites

- Docker and Docker Compose
- An LLM API key (Anthropic and/or OpenAI) **or** Ollama for fully local operation

### Run with Docker

```bash
# Clone the repo
git clone <repo-url> querywise
cd querywise

# Create your .env (see .env.example)
cp .env.example .env
# Edit .env to add your API keys (or configure Ollama — see below)

# Start everything
docker compose up
```

| Service | URL |
|---------|-----|
| Frontend | http://localhost:5173 |
| Backend API | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |
| Ollama | http://localhost:11434 |
| App Database (pgvector) | localhost:5432 |
| Sample Database | localhost:5433 |

### Connecting to a Host Database from Docker

If QueryWise is running in Docker but your target PostgreSQL is running on the host machine, use:

`postgresql://<user>:<password>@host.docker.internal:<port>/<database>`

Example:

`postgresql://qadmin:your-password@host.docker.internal:5434/Adventureworks_aw`

On Linux, if `host.docker.internal` is not resolvable in your containers, add this to the `backend` service in `docker-compose.yml`:

```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

### Connecting to BigQuery

1. Select **BigQuery** as the connector type in the Add Connection form
2. Enter your GCP **Project ID**
3. Paste your **service account JSON key** (the full contents of the key file)
4. Set the **Dataset** name (BigQuery's equivalent of a schema)
5. Click Create, then Test and Introspect

The service account needs the **BigQuery User** role (or equivalent) to run queries. The connection credentials are encrypted at rest using Fernet encryption.

### Connecting to Databricks

1. Select **Databricks** as the connector type in the Add Connection form
2. Enter the **Server hostname** (e.g., `dbc-a1b2345c-d6e7.cloud.databricks.com`)
3. Enter the **HTTP path** for your SQL warehouse or all-purpose cluster (e.g., `/sql/1.0/warehouses/abc123`)
4. Enter a **Personal Access Token** (`dapi...`)
5. Set the **Catalog** (defaults to `main`) and **Schema** (defaults to `default`)
6. Click Create, then Test and Introspect

Works with both **Unity Catalog** (full INFORMATION_SCHEMA introspection including PKs/FKs) and **Hive metastore** (falls back to SHOW/DESCRIBE commands). Credentials are encrypted at rest.

### First Steps

1. Open http://localhost:5173
2. The IFRS 9 sample database is **auto-configured** on first startup — connection, schema introspection, glossary, metrics, dictionary, and knowledge are all seeded automatically
3. Go to **Query** and ask a question like "What is the total ECL by stage?"

> **Note:** Auto-setup is controlled by `AUTO_SETUP_SAMPLE_DB=true` (default). Set to `false` to disable. For manual seeding, use `python backend/scripts/seed_ifrs9_metadata.py`.



### Using the Assistant Chat Panel

QueryWise includes a **conversational Assistant** on the Query page. Ask questions in plain English or grow your semantic layer by talking:

- **Ask data questions** — natural language queries use the semantic layer context to generate accurate SQL
- **Add glossary terms** — describe business terms in plain language, the Assistant drafts them for review
- **Create metrics, dictionary entries, and knowledge documents** — editors can add semantic layer definitions conversationally

The Assistant only *drafts* definitions — every write uses the existing REST endpoints, so authorization and auto-embedding are unchanged.

### Using QueryWise from Claude / Cursor / Copilot / Codex (MCP)

QueryWise exposes its semantic layer and query pipeline as an **MCP server**, with two transports:

- **HTTP** at `http://localhost:8000/mcp` (streamable HTTP, mounted on the backend).
- **stdio** via the `querywise-mcp` console script (runs as a subprocess, talks to the same Postgres).

Both modes expose the same 24 tools — `add_metric`, `add_glossary_term`, `list_connections`, `get_semantic_context`, `generate_sql`, `run_sql`, `ask`, `query_history`, etc. — and share the same backing store as the REST API and the web UI.

`DATABASE_URL` is only the QueryWise metadata database. It stores connection
records, schema cache, glossary terms, metrics, dictionary entries, knowledge,
sample queries, and query history. User databases are added separately with the
`create_connection` MCP tool, the web UI, or the REST API.

For any PostgreSQL target connection, use a connection string that is reachable
from the process running the MCP server:

| MCP transport | Where it runs | Target DB hostname must be reachable from |
|---------------|---------------|-------------------------------------------|
| HTTP `http://localhost:8000/mcp` | `backend` container | Docker/backend network |
| Docker stdio via `docker compose exec backend querywise-mcp` | `backend` container | Docker/backend network |
| Local stdio via `querywise-mcp` | Host machine | Host machine |

External PostgreSQL databases work normally as long as firewall, DNS, SSL, and
credentials allow access from that location. For example, if QueryWise/MCP runs
inside Docker and the database is on another server, create the target
connection with something like
`postgresql://user:password@db.example.com:5432/appdb`. If the target database
runs on the host machine while QueryWise runs in Docker, use
`host.docker.internal` as described above.

> **Docker note:** the auto-created IFRS 9 connection is stored as
> `postgresql://sample:sample_dev@sample-db:5432/sampledb`, which is reachable
> from inside the Docker Compose network. If you launch `querywise-mcp` directly
> on your host, it can read the QueryWise metadata DB on `localhost:5432`, but it
> cannot reach the saved target connection host `sample-db`. For the sample DB,
> use HTTP or run stdio inside the `backend` container.

#### Claude Code (CLI) and Codex CLI

HTTP works out of the box:

```bash
claude mcp add --transport http querywise http://localhost:8000/mcp
codex mcp add querywise --url http://localhost:8000/mcp
```

Or stdio if you prefer a subprocess:

```bash
claude mcp add querywise -- querywise-mcp
```

For the Docker stack with the bundled IFRS 9 sample DB, spawn stdio inside the
running backend container instead:

```bash
claude mcp add querywise -- docker compose -f /path/to/querywise/docker-compose.yml exec -T backend querywise-mcp
```

#### Claude Desktop

Claude Desktop's custom connectors require HTTPS, so stdio is the simplest path. Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (or use Settings → Developer → Edit Config) and add:

```json
{
  "mcpServers": {
    "querywise": {
      "command": "docker",
      "args": [
        "compose",
        "-f",
        "/path/to/querywise/docker-compose.yml",
        "exec",
        "-T",
        "backend",
        "querywise-mcp"
      ]
    }
  }
}
```

Restart Claude Desktop. If you'd rather use the HTTP transport, expose the backend via `ngrok http 8000` and paste the HTTPS URL into **Settings → Connectors → Add custom connector**.

If you are not using Docker, install the CLI locally and point `DATABASE_URL` at
the QueryWise metadata database. Any target connections you create must also use
hostnames reachable from the host process:

```json
{
  "mcpServers": {
    "querywise": {
      "command": "querywise-mcp",
      "env": {
        "DATABASE_URL": "postgresql+asyncpg://querywise:querywise_dev@localhost:5432/querywise"
      }
    }
  }
}
```

For example, if you want a host-launched stdio server to query the Docker sample
DB, create or update that target connection with
`postgresql://sample:sample_dev@localhost:5433/sampledb`. An existing auto-seeded
Docker connection that uses `sample-db:5432` will continue to be container-only.

#### Cursor / Windsurf

Add to `.cursor/mcp.json` (project) or the global config:

```json
{
  "mcpServers": {
    "querywise": { "url": "http://localhost:8000/mcp" }
  }
}
```

#### GitHub Copilot (VS Code)

Add to `.vscode/mcp.json`:

```json
{
  "servers": {
    "querywise": { "type": "http", "url": "http://localhost:8000/mcp" }
  }
}
```

#### Codex CLI

In `~/.codex/config.toml`:

```toml
[mcp_servers.querywise]
url = "http://localhost:8000/mcp"
```

For Docker-backed stdio in Codex:

```toml
[mcp_servers.querywise]
command = "docker"
args = ["compose", "-f", "/path/to/querywise/docker-compose.yml", "exec", "-T", "backend", "querywise-mcp"]
```

#### Installing the `querywise-mcp` CLI

Available after `pip install -e ./backend` (or any wheel built from this repo). Verify with:

```bash
querywise-mcp --help        # or just `querywise-mcp` to start the stdio loop
```

Example uses, once connected:

- *"Add a metric `gross_revenue` on the IFRS 9 connection with expression `SUM(exposure_amount)`."*
- *"Ask the IFRS 9 connection: What is the total ECL by stage?"*

### Using Ollama (Fully Local — No API Keys)

QueryWise can run entirely on local hardware using Ollama. No cloud API keys needed.

```bash
# Configure .env for Ollama
DEFAULT_LLM_PROVIDER=ollama
OLLAMA_MODEL=llama3.1:8b
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_DIMENSION=768

# --- Or configure for Anthropic (Claude) ---
# DEFAULT_LLM_PROVIDER=anthropic
# DEFAULT_LLM_MODEL=claude-sonnet-4-20250514
# ANTHROPIC_API_KEY=your-anthropic-api-key
# OPENAI_API_KEY=your-openai-api-key          # Required for embeddings
# EMBEDDING_DIMENSION=1536

# --- Or configure for OpenAI ---
# DEFAULT_LLM_PROVIDER=openai
# DEFAULT_LLM_MODEL=gpt-4o
# OPENAI_API_KEY=your-openai-api-key
# EMBEDDING_DIMENSION=1536

# Start the stack (includes Ollama service)
docker compose up

#Provide ollama models on host or  pull the required models in docker (CPU) (first time only, Ollama only)
docker compose exec ollama ollama pull llama3.1:8b
docker compose exec ollama ollama pull nomic-embed-text
```

**Switching providers:** When you change `EMBEDDING_DIMENSION` (e.g., 768 → 1536), migration `002_configurable_embedding_dim` automatically resizes vector columns and **clears all existing embeddings** — they are not portable across providers (different dimensions and incompatible vector spaces). Embeddings regenerate automatically on first use with the new provider. Your metadata (glossary, metrics, dictionary) is preserved; only the embedding vectors are reset.

> **GPU support:** Uncomment the `deploy.resources` section in `docker-compose.yml` under the `ollama` service to enable NVIDIA GPU acceleration.

---

## Development Setup (without Docker)

### Backend

```bash
cd backend

# Create virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# Install dependencies (add `lineage` for sqlglot-based catalog lineage)
pip install -e ".[llm,dev,lineage]"

# Start PostgreSQL with pgvector (must be running on localhost:5432)
# Run migrations
alembic upgrade head

# Start the dev server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend

```bash
cd frontend

# Install dependencies
npm install

# Start dev server (proxies /api to localhost:8000)
npm run dev
```

### Database Setup

The application requires two PostgreSQL databases:

1. **App database** (with pgvector extension) — stores metadata, glossary, embeddings, query history
2. **Target database** — the database you want to query with natural language

For development, `docker compose up app-db sample-db` starts both databases without the full stack.

---

## Production Deployment

The `docker compose up` flow above is for **local development**. For production,
QueryWise ships a full set of deployment artifacts under [`deploy/`](deploy/) —
the same build-once images configured entirely by environment:

| Target | Where | Best for |
|--------|-------|----------|
| **Docker Compose (prod)** | [`docker-compose.prod.yml`](docker-compose.prod.yml) | Small / on-prem, single host |
| **Helm chart** | [`deploy/helm/querywise/`](deploy/helm/querywise) | EKS / GKE / AKS |
| **Terraform** | [`deploy/terraform/{aws,gcp,azure}/`](deploy/terraform) | Managed Postgres+pgvector, Redis, secrets — in your own VPC |
| **CI/CD** | [`.github/workflows/release.yml`](.github/workflows/release.yml) | Build → push images → Helm deploy (staging → prod) |
| **Ops** | [`deploy/ops/`](deploy/ops) | Encrypted backup/restore, DR runbook, config reference |

Highlights: hardened multi-stage **non-root** images, a one-shot Alembic
migration that runs before new pods roll (replicas never race), backend
autoscaling + PodDisruptionBudgets, secrets via the **external-secrets** seam,
and a same-origin SPA behind an nginx edge. Start at [`deploy/README.md`](deploy/README.md);
the production env template is [`.env.prod.example`](.env.prod.example).

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://querywise:querywise_dev@localhost:5432/querywise` | App metadata database connection |
| `ENVIRONMENT` | `development` | Environment name |
| `DEBUG` | `false` | Enable debug mode |
| `ENCRYPTION_KEY` | `dev-encryption-key-change-in-production` | Fernet key for encrypting stored connection strings |
| `CORS_ORIGINS` | `["http://localhost:5173"]` | Allowed CORS origins (JSON list) |
| `DEFAULT_LLM_PROVIDER` | `anthropic` | Default LLM provider (`anthropic`, `openai`, `ollama`) |
| `DEFAULT_LLM_MODEL` | `claude-sonnet-4-20250514` | Default model for SQL generation |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Model for generating embeddings (OpenAI) |
| `EMBEDDING_DIMENSION` | `1536` | Embedding vector dimension |
| `DEFAULT_QUERY_TIMEOUT_SECONDS` | `30` | Max query execution time |
| `DEFAULT_MAX_ROWS` | `1000` | Max rows returned per query |
| `MAX_RETRY_ATTEMPTS` | `3` | Max SQL correction retries |
| `MAX_QUERIES_PER_MINUTE` | `30` | Rate limit |
| `MAX_CONTEXT_TABLES` | `8` | Max tables included in LLM context |
| `MAX_SAMPLE_QUERIES` | `3` | Max sample queries included in context |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `llama3.1:8b` | Ollama model for completions |
| `OLLAMA_EMBEDDING_MODEL` | `nomic-embed-text` | Ollama model for embeddings (768-dim) |
| `ANTHROPIC_API_KEY` | — | Anthropic API key (required if using Anthropic) |
| `OPENAI_API_KEY` | — | OpenAI API key (required if using OpenAI) |
| `AUTO_SETUP_SAMPLE_DB` | `true` | Auto-create sample DB connection + seed metadata on startup |
| `SAMPLE_DB_CONNECTION_STRING` | `postgresql://sample:sample_dev@sample-db:5432/sampledb` | Connection string for the auto-setup sample database |
| `VITE_API_URL` | `http://localhost:8000` | Frontend: backend API URL |

---

## Project Structure

```
querywise/
├── docker-compose.yml              # Dev: app-db, sample-db, backend, frontend
├── docker-compose.prod.yml         # Prod: + redis, migrate, arq worker, nginx edge
├── .env.example                    # Environment variable template (dev)
├── .env.prod.example               # Environment variable template (prod)
├── CLAUDE.md                       # Claude Code project conventions
├── CHANGELOG.md                    # Release notes
├── README.md                       # This file
├── deploy/                         # Production deployment artifacts
│   ├── helm/querywise/             # Helm chart (HPA, PDB, ingress, migration hook)
│   ├── terraform/{aws,gcp,azure}/  # Managed Postgres+pgvector, Redis, secrets
│   └── ops/                        # backup/restore, DR runbook, config reference
├── .github/workflows/              # CI (tests/lint) + release (build → deploy)
│
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml              # Python deps (fastapi, sqlalchemy, pgvector, etc.)
│   ├── alembic.ini                 # Migration config
│   ├── alembic/
│   │   ├── env.py                  # Async migration environment
│   │   └── versions/               # Migration files
│   ├── app/
│   │   ├── main.py                 # FastAPI app factory with CORS + lifespan
│   │   ├── config.py               # Pydantic BaseSettings (env vars)
│   │   ├── core/
│   │   │   ├── exceptions.py       # AppError, NotFoundError, ConnectionError, etc.
│   │   │   └── exception_handlers.py
│   │   ├── db/
│   │   │   ├── base.py             # SQLAlchemy DeclarativeBase
│   │   │   ├── session.py          # Async engine + session factory
│   │   │   └── models/
│   │   │       ├── connection.py   # DatabaseConnection (encrypted conn strings)
│   │   │       ├── schema_cache.py # CachedTable, CachedColumn, CachedRelationship
│   │   │       ├── glossary.py     # GlossaryTerm (with embedding vector)
│   │   │       ├── metric.py       # MetricDefinition (with embedding vector)
│   │   │       ├── dictionary.py   # DictionaryEntry (value mappings)
│   │   │       ├── knowledge.py    # KnowledgeDocument + KnowledgeChunk (with embedding vector)
│   │   │       ├── sample_query.py # SampleQuery (with embedding vector)
│   │   │       ├── query_history.py# QueryExecution (full audit log)
│   │   │       ├── saved_query.py  # SavedQuery (pinned SQL + typed params)
│   │   │       ├── chart.py        # Chart (viz config per saved query)
│   │   │       ├── result_snapshot.py # ResultSnapshot (result persistence + cache)
│   │   │       ├── dashboard.py    # Dashboard (workspace-scoped, with filters)
│   │   │       └── dashboard_tile.py # DashboardTile (grid position + refresh)
│   │   ├── api/v1/
│   │   │   ├── router.py           # Aggregates all endpoint routers
│   │   │   ├── endpoints/
│   │   │   │   ├── health.py       # GET /health
│   │   │   │   ├── connections.py  # CRUD + test + introspect
│   │   │   │   ├── schemas.py      # Table listing + detail
│   │   │   │   ├── glossary.py     # Business glossary CRUD
│   │   │   │   ├── metrics.py      # Metric definitions CRUD
│   │   │   │   ├── dictionary.py   # Data dictionary CRUD
│   │   │   │   ├── sample_queries.py
│   │   │   │   ├── knowledge.py     # Knowledge document CRUD + URL fetch
│   │   │   │   ├── query.py        # POST /query (full pipeline), POST /query/sql-only
│   │   │   │   ├── query_history.py# History list + favorite toggle
│   │   │   │   ├── saved_queries.py# Saved query CRUD + run/clone/export + charts
│   │   │   │   └── dashboards.py    # Dashboard + tile CRUD, layout, tile run
│   │   │   └── schemas/            # Pydantic request/response models
│   │   ├── services/
│   │   │   ├── query_service.py    # Full pipeline orchestrator
│   │   │   ├── connection_service.py# CRUD + encryption + test
│   │   │   ├── schema_service.py   # Introspect + cache
│   │   │   ├── embedding_service.py# Generate embeddings (OpenAI or Ollama)
│   │   │   ├── knowledge_service.py# Knowledge import (HTML parsing, chunking, embedding)
│   │   │   └── setup_service.py    # Auto-setup sample DB on startup
│   │   ├── semantic/               # *** Core IP ***
│   │   │   ├── context_builder.py  # Orchestrates all context selection
│   │   │   ├── schema_linker.py    # Vector + keyword search for relevant tables
│   │   │   ├── glossary_resolver.py# Resolves business terms, metrics, dictionary, knowledge
│   │   │   ├── prompt_assembler.py # Formats context into structured LLM prompt
│   │   │   └── relevance_scorer.py # Weighted scoring (embedding + keyword + FK)
│   │   ├── llm/
│   │   │   ├── base_provider.py    # BaseLLMProvider ABC
│   │   │   ├── provider_registry.py# Factory + caching for providers
│   │   │   ├── router.py           # Complexity estimation + model routing
│   │   │   ├── utils.py                # JSON repair for local model output
│   │   │   ├── providers/
│   │   │   │   ├── anthropic_provider.py # Claude (complete + stream)
│   │   │   │   ├── openai_provider.py    # GPT (complete + stream + embeddings)
│   │   │   │   └── ollama_provider.py    # Ollama (complete + stream + embeddings)
│   │   │   ├── agents/
│   │   │   │   ├── query_composer.py     # NL question → SQL
│   │   │   │   ├── sql_validator.py      # Static + schema validation
│   │   │   │   ├── result_interpreter.py # Results → NL summary
│   │   │   │   └── error_handler.py      # Error → corrected SQL (max 3 retries)
│   │   │   └── prompts/
│   │   │       ├── composer_prompts.py
│   │   │       └── interpreter_prompts.py
│   │   ├── connectors/
│   │   │   ├── base_connector.py    # BaseConnector ABC
│   │   │   ├── connector_registry.py# Plugin registry + connection caching
│   │   │   ├── postgresql/
│   │   │   │   └── connector.py     # PostgreSQL (asyncpg, connection pooling)
│   │   │   ├── bigquery/
│   │   │   │   └── connector.py     # BigQuery (google-cloud-bigquery, service account auth)
│   │   │   └── databricks/
│   │   │       └── connector.py     # Databricks (databricks-sql-connector, PAT auth)
│   │   └── utils/
│   │       └── sql_sanitizer.py     # Regex blocklist (DDL/DML/admin/injection)
│   ├── scripts/
│   │   └── seed_ifrs9_metadata.py   # Seeds glossary, metrics, dictionary via API
│   └── tests/
│       └── fixtures/
│           └── sample_seed.sql      # IFRS 9 banking sample data
│
└── frontend/
    ├── Dockerfile
    ├── package.json
    ├── vite.config.ts               # Dev proxy: /api → localhost:8000
    ├── tsconfig.json
    └── src/
        ├── main.tsx                 # MantineProvider + QueryClient + Router
        ├── App.tsx                  # Route definitions
        ├── api/
        │   ├── client.ts           # Axios instance (session cookie + workspace header)
        │   ├── connectionApi.ts    # Connection endpoints
        │   ├── queryApi.ts         # Query + history endpoints
        │   ├── glossaryApi.ts      # Glossary + metrics + dictionary endpoints
        │   ├── knowledgeApi.ts     # Knowledge document CRUD + URL fetch
        │   ├── savedQueriesApi.ts  # Saved query CRUD + run/clone/export + charts
        │   └── dashboardsApi.ts    # Dashboard + tile CRUD, layout, tile run
        ├── components/
        │   ├── layout/
        │   │   └── AppLayout.tsx   # Mantine AppShell with sidebar nav
        │   ├── charts/
        │   │   └── ChartView.tsx   # Recharts renderer (line/bar/area/pie/scatter)
        │   ├── common/
        │   │   └── ParamInputs.tsx # Typed param/filter inputs (shared)
        │   ├── savedQueries/       # Run drawer + form modal
        │   └── dashboards/         # Grid, tile card, filters bar, modals
        ├── hooks/
        │   ├── useConnections.ts   # React Query hooks for connections
        │   ├── useSavedQueries.ts  # Saved query + chart hooks
        │   └── useDashboards.ts    # Dashboard + tile hooks
        ├── pages/
        │   ├── QueryPage.tsx       # NL input → SQL preview → results table
        │   ├── ConnectionsPage.tsx # Add/edit/delete/test/introspect connections
        │   ├── GlossaryPage.tsx    # Business glossary term management
        │   ├── MetricsPage.tsx     # Metric definition management
        │   ├── DictionaryPage.tsx  # Column value mapping management
        │   ├── KnowledgePage.tsx   # Knowledge document import/manage (text + URL fetch)
        │   ├── HistoryPage.tsx     # Query execution history + favorites
        │   ├── SavedQueriesPage.tsx# Saved queries: run, chart, export
        │   ├── DashboardsPage.tsx  # Dashboard list
        │   └── DashboardDetailPage.tsx # Dashboard grid + filters
        └── types/
            └── api.ts              # TypeScript interfaces
```

---

## How It Works

### Query Pipeline

When a user asks a natural language question, the system runs a 7-step pipeline:

```
"What is the total ECL by stage?"
    │
    ▼
┌─ 1. CONTEXT BUILDING ──────────────────────────────────┐
│  • Embed the question (OpenAI or Ollama nomic-embed-text) │
│  • Vector search: find similar tables, glossary, metrics │
│  • Keyword search: match table/column names directly     │
│  • FK expansion: include related JOIN tables             │
│  • Score & prune to top 8 tables                         │
│  • Resolve glossary terms, metrics, knowledge, dictionary│
│  • Assemble structured prompt with schema + context      │
└──────────────────────────────┬──────────────────────────┘
                               ▼
┌─ 2. LLM ROUTING ────────────────────────────────────────┐
│  Estimate query complexity (simple/moderate/complex)     │
│  Route to appropriate model (haiku → sonnet → opus)     │
└──────────────────────────────┬──────────────────────────┘
                               ▼
┌─ 3. SQL GENERATION ─────────────────────────────────────┐
│  QueryComposerAgent generates SQL from the prompt       │
│  Returns: SQL + explanation + confidence + tables_used   │
└──────────────────────────────┬──────────────────────────┘
                               ▼
┌─ 4. VALIDATION ─────────────────────────────────────────┐
│  Static check: regex blocklist (DDL, DML, injections)   │
│  Schema check: verify tables/columns exist via sqlparse │
│  If invalid → ErrorHandlerAgent retries (max 3x)       │
└──────────────────────────────┬──────────────────────────┘
                               ▼
┌─ 5. EXECUTION ──────────────────────────────────────────┐
│  Run SQL via connector (PG / BigQuery / Databricks)      │
│  Read-only transaction, statement timeout, row limit    │
│  If DB error → ErrorHandlerAgent retries (max 3x)      │
└──────────────────────────────┬──────────────────────────┘
                               ▼
┌─ 6. INTERPRETATION ─────────────────────────────────────┐
│  ResultInterpreterAgent generates NL summary            │
│  Returns: summary + highlights + suggested follow-ups   │
└──────────────────────────────┬──────────────────────────┘
                               ▼
┌─ 7. HISTORY LOGGING ───────────────────────────────────┐
│  Save to query_executions: question, SQL, results,     │
│  timing, tokens used, retry count, status              │
└─────────────────────────────────────────────────────────┘
```

### Semantic Layer (Hybrid Context Selection)

The context builder is the product's core differentiator. It selects the most relevant schema context for each question using three strategies:

1. **Embedding similarity** (50% weight) — cosine distance search via pgvector against table, column, glossary, and metric embeddings
2. **Keyword matching** (30% weight) — extract keywords from the question, match against table/column names (exact, partial, substring)
3. **FK graph expansion** (20% weight) — walk foreign key relationships from top-scoring tables to include necessary JOIN tables

Additional context layers are resolved independently and injected into the LLM prompt:
- **Glossary & Metrics** — keyword + embedding similarity search
- **Knowledge chunks** — top 5 by vector similarity with keyword ILIKE fallback
- **Dictionary entries** — all value mappings for columns in selected tables
- **Sample queries** — top 3 validated queries by embedding similarity (few-shot examples)

This ensures both semantic matches ("how much revenue" finds `orders`) and exact name matches ("the refunds table" finds `refunds`).

---

## Extending the Application

### Adding a New Database Connector

1. Create `app/connectors/mydb/connector.py` implementing `BaseConnector`:

```python
from app.connectors.base_connector import BaseConnector, ConnectorType

class MyDBConnector(BaseConnector):
    connector_type = ConnectorType.MYSQL  # Add to ConnectorType enum if needed

    async def connect(self, connection_string, **kwargs): ...
    async def disconnect(self): ...
    async def test_connection(self) -> bool: ...
    async def introspect_schemas(self) -> list[str]: ...
    async def introspect_tables(self, schema) -> list[TableInfo]: ...
    async def execute_query(self, sql, params, timeout_seconds, max_rows) -> QueryResult: ...
    async def get_sample_values(self, schema, table, column, limit) -> list: ...
```

2. Register in `app/connectors/connector_registry.py`:

```python
from app.connectors.mydb.connector import MyDBConnector
_CONNECTOR_CLASSES[ConnectorType.MYSQL] = MyDBConnector
```

### Adding a New LLM Provider

1. Create `app/llm/providers/my_provider.py` implementing `BaseLLMProvider`:

```python
from app.llm.base_provider import BaseLLMProvider, LLMProviderType

class MyProvider(BaseLLMProvider):
    provider_type = LLMProviderType.OLLAMA

    async def complete(self, messages, config) -> LLMResponse: ...
    async def stream(self, messages, config) -> AsyncIterator[str]: ...
    async def generate_embedding(self, text) -> list[float]: ...
    def list_models(self) -> list[str]: ...
```

2. Register in `app/llm/provider_registry.py`.

---

## API Reference

All endpoints are under `/api/v1`.

### Connections

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/connections` | List all connections |
| `POST` | `/connections` | Create connection |
| `GET` | `/connections/{id}` | Get connection |
| `PUT` | `/connections/{id}` | Update connection |
| `DELETE` | `/connections/{id}` | Delete connection |
| `POST` | `/connections/{id}/test` | Test connection |
| `POST` | `/connections/{id}/introspect` | Introspect schema |

### Schema

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/connections/{id}/tables` | List tables |
| `GET` | `/tables/{table_id}` | Table detail (columns, relationships) |

### Semantic Layer

| Method | Path | Description |
|--------|------|-------------|
| `GET/POST` | `/connections/{id}/glossary` | List/create glossary terms |
| `GET/PUT/DELETE` | `/connections/{id}/glossary/{term_id}` | Get/update/delete term |
| `GET/POST` | `/connections/{id}/metrics` | List/create metrics |
| `GET/PUT/DELETE` | `/connections/{id}/metrics/{metric_id}` | Get/update/delete metric |
| `GET/POST` | `/columns/{col_id}/dictionary` | List/create dictionary entries |
| `PUT/DELETE` | `/columns/{col_id}/dictionary/{entry_id}` | Update/delete entry |
| `GET/POST` | `/connections/{id}/knowledge` | List/create knowledge documents |
| `GET/DELETE` | `/connections/{id}/knowledge/{doc_id}` | Get/delete knowledge document |
| `POST` | `/knowledge/fetch-url` | Fetch URL and return parsed content |
| `GET/POST` | `/connections/{id}/sample-queries` | List/create sample queries |
| `PUT/DELETE` | `/connections/{id}/sample-queries/{sq_id}` | Update/delete sample query |

### Query

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/query` | Execute NL query (full pipeline) |
| `POST` | `/query/sql-only` | Generate SQL without executing |

### Saved Queries

| Method | Path | Description |
|--------|------|-------------|
| `GET/POST` | `/connections/{id}/saved-queries` | List/create saved queries |
| `GET/PUT/DELETE` | `/connections/{id}/saved-queries/{sq_id}` | Get/update/delete saved query |
| `POST` | `/connections/{id}/saved-queries/{sq_id}/run` | Run (cache-first; `refresh` to bypass) |
| `POST` | `/connections/{id}/saved-queries/{sq_id}/clone` | Clone a saved query |
| `GET` | `/connections/{id}/saved-queries/{sq_id}/export` | Export results (`format=csv\|json\|xlsx`) |
| `GET/POST` | `/connections/{id}/saved-queries/{sq_id}/charts` | List/create charts |
| `PUT/DELETE` | `/connections/{id}/saved-queries/{sq_id}/charts/{chart_id}` | Update/delete chart |

### Dashboards

| Method | Path | Description |
|--------|------|-------------|
| `GET/POST` | `/dashboards` | List/create dashboards (workspace-scoped) |
| `GET/PUT/DELETE` | `/dashboards/{id}` | Get/update/delete dashboard |
| `POST` | `/dashboards/{id}/tiles` | Add a tile |
| `PUT/DELETE` | `/dashboards/{id}/tiles/{tile_id}` | Update/delete a tile |
| `PUT` | `/dashboards/{id}/layout` | Bulk-save tile positions |
| `POST` | `/dashboards/{id}/tiles/{tile_id}/run` | Run a tile with dashboard filters |

### History

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/query-history` | List query history |
| `GET` | `/query-history/{id}` | Get single execution |
| `PATCH` | `/query-history/{id}/favorite` | Toggle favorite |

### Health

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |

---

## Sample Database

The project includes a sample **IFRS 9 banking database** (auto-seeded via Docker) modelling Expected Credit Loss (ECL) provisioning, staging, and impairment:

| Table | Rows | Description |
|-------|------|-------------|
| `counterparties` | 20 | Bank customers/borrowers with segment (retail/corporate/sme), credit rating, default flag |
| `facilities` | 25 | Loan facilities — mortgage, corporate loan, consumer loan, credit card, overdraft |
| `exposures` | 25 | Monthly exposure snapshots — EAD, carrying amount, IFRS 9 stage (1/2/3), days past due |
| `ecl_provisions` | 25 | Expected Credit Loss calculations — PD, LGD, ECL 12-month, ECL lifetime per exposure |
| `collateral` | 14 | Collateral linked to facilities — property, cash, guarantee, securities |
| `staging_history` | 30 | Stage transition audit trail — from/to stage, reason, effective date |

Connection string: `postgresql://sample:sample_dev@sample-db:5432/sampledb` (from within Docker) or `postgresql://sample:sample_dev@localhost:5433/sampledb` (from host).

### Pre-seeded Metadata

All metadata is **auto-seeded on startup** when `AUTO_SETUP_SAMPLE_DB=true` (default). For manual seeding, run:

```bash
python backend/scripts/seed_ifrs9_metadata.py
```

Auto-setup populates:
- **10 glossary terms**: EAD, PD, LGD, ECL, Stage 1/2/3, SICR, Coverage Ratio, NPL
- **8 metrics**: Total ECL, Total EAD, Coverage Ratio, Stage 1/2/3 Exposure, Average PD, NPL Ratio
- **43 dictionary entries**: stage codes, facility types, customer segments, collateral types, staging reasons, credit ratings, default flags, currencies, revolving indicators
- **1 knowledge document**: IFRS 9 Staging & ECL Policy Summary (staging criteria, ECL calculation, collateral rules, stage migration, reporting dimensions)

---

## Security

- **Read-only execution** — PostgreSQL queries run inside `SET TRANSACTION READ ONLY`; BigQuery and Databricks enforce read-only via SQL blocklist
- **SQL blocklist** — static regex patterns block DDL (`DROP`, `ALTER`, `CREATE`), DML (`INSERT`, `UPDATE`, `DELETE`), admin commands (`GRANT`, `COPY`, `EXECUTE`), injection patterns (`pg_sleep`, `dblink`, stacked queries), BigQuery-specific operations (`EXPORT DATA`, `LOAD DATA`), and Databricks-specific operations (`COPY INTO`, `OPTIMIZE`, `VACUUM`)
- **Encrypted credentials** — connection strings encrypted at rest using Fernet (AES-128-CBC)
- **Statement timeout** — configurable per connection (default 30s)
- **Row limits** — configurable per connection (default 1000 rows)
- **CORS** — restricted to configured origins
- **Connection strings never exposed** — API returns `has_connection_string: boolean`, never the actual string

---

## License

MIT
