# Development Guide

## Local Setup (without Docker)

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

### Tests & Linting

```bash
cd backend
pytest                 # Run tests
ruff check .           # Lint
ruff format .          # Format
mypy .                 # Type check

cd ../frontend
npm run lint           # ESLint
npm run build          # Type check + production build
```

## Project Structure

```
querywise/
├── docker-compose.yml              # Dev: app-db, sample-db, backend, frontend
├── docker-compose.prod.yml         # Prod: + redis, migrate, arq worker, nginx edge
├── .env.example                    # Environment variable template (dev)
├── .env.prod.example               # Environment variable template (prod)
├── CLAUDE.md                       # Claude Code project conventions
├── CHANGELOG.md                    # Release notes
├── README.md                       # Project overview
├── docs/                           # MCP, API reference, configuration, this guide
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
│   │   │   │   ├── knowledge.py    # Knowledge document CRUD + URL fetch
│   │   │   │   ├── query.py        # POST /query (full pipeline), POST /query/sql-only
│   │   │   │   ├── query_history.py# History list + favorite toggle
│   │   │   │   ├── saved_queries.py# Saved query CRUD + run/clone/export + charts
│   │   │   │   └── dashboards.py   # Dashboard + tile CRUD, layout, tile run
│   │   │   └── schemas/            # Pydantic request/response models
│   │   ├── services/
│   │   │   ├── query_service.py    # Full pipeline orchestrator
│   │   │   ├── connection_service.py # CRUD + encryption + test
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
│   │   │   ├── utils.py            # JSON repair for local model output
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
│   │   │   ├── base_connector.py   # BaseConnector ABC
│   │   │   ├── connector_registry.py # Plugin registry + connection caching
│   │   │   ├── postgresql/
│   │   │   │   └── connector.py    # PostgreSQL (asyncpg, connection pooling)
│   │   │   ├── bigquery/
│   │   │   │   └── connector.py    # BigQuery (google-cloud-bigquery, service account auth)
│   │   │   └── databricks/
│   │   │       └── connector.py    # Databricks (databricks-sql-connector, PAT auth)
│   │   └── utils/
│   │       └── sql_sanitizer.py    # Regex blocklist (DDL/DML/admin/injection)
│   ├── scripts/
│   │   └── seed_ifrs9_metadata.py  # Seeds glossary, metrics, dictionary via API
│   └── tests/
│       └── fixtures/
│           └── sample_seed.sql     # IFRS 9 banking sample data
│
└── frontend/
    ├── Dockerfile
    ├── package.json
    ├── vite.config.ts              # Dev proxy: /api → localhost:8000
    ├── tsconfig.json
    └── src/
        ├── main.tsx                # MantineProvider + QueryClient + Router
        ├── App.tsx                 # Route definitions
        ├── api/                    # Axios clients (one per resource)
        ├── components/
        │   ├── layout/             # Mantine AppShell with sidebar nav
        │   ├── charts/             # Recharts renderer (line/bar/area/pie/scatter)
        │   ├── common/             # Shared inputs, badges, version history
        │   ├── savedQueries/       # Run drawer + form modal
        │   └── dashboards/         # Grid, tile card, filters bar, modals
        ├── hooks/                  # React Query hooks per domain
        ├── pages/                  # Route pages (Query, Dashboards, Catalog, ...)
        └── types/                  # TypeScript interfaces
```

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
