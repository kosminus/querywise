# Configuration

Core settings for local and Docker use. The production-focused catalogue lives in
[`deploy/ops/config-reference.md`](../deploy/ops/config-reference.md); the full
templates are [`.env.example`](../.env.example) (dev) and
[`.env.prod.example`](../.env.prod.example) (prod).

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://querywise:querywise_dev@localhost:5432/querywise` | App metadata database connection |
| `ENVIRONMENT` | `development` | Environment name |
| `DEBUG` | `false` | Enable debug mode |
| `ENCRYPTION_KEY` | `dev-encryption-key-change-in-production` | Fernet key for encrypting stored connection strings |
| `CORS_ORIGINS` | `["http://localhost:5173"]` | Allowed CORS origins (JSON list) |
| `DEFAULT_LLM_PROVIDER` | `anthropic` | Default LLM provider (`anthropic`, `openai`, `ollama`, `azure_openai`) |
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

## Choosing an LLM Provider

```bash
# --- Ollama (fully local, no API keys) ---
DEFAULT_LLM_PROVIDER=ollama
OLLAMA_MODEL=llama3.1:8b
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_DIMENSION=768

# --- Anthropic (Claude) ---
# DEFAULT_LLM_PROVIDER=anthropic
# DEFAULT_LLM_MODEL=claude-sonnet-4-20250514
# ANTHROPIC_API_KEY=your-anthropic-api-key
# OPENAI_API_KEY=your-openai-api-key          # Required for embeddings
# EMBEDDING_DIMENSION=1536

# --- OpenAI ---
# DEFAULT_LLM_PROVIDER=openai
# DEFAULT_LLM_MODEL=gpt-4o
# OPENAI_API_KEY=your-openai-api-key
# EMBEDDING_DIMENSION=1536
```

### Ollama setup (Docker)

```bash
# Start the stack (includes the Ollama service)
docker compose up

# Provide Ollama models on the host, or pull them in Docker (CPU) — first time only
docker compose exec ollama ollama pull llama3.1:8b
docker compose exec ollama ollama pull nomic-embed-text
```

> **GPU support:** Uncomment the `deploy.resources` section in
> `docker-compose.yml` under the `ollama` service to enable NVIDIA GPU
> acceleration. On macOS, running Ollama natively (`brew install ollama`) with
> `OLLAMA_BASE_URL=http://host.docker.internal:11434` is ~5–10x faster than the
> CPU-only Docker container, because native Ollama uses Apple Metal.

### Switching providers

When you change `EMBEDDING_DIMENSION` (e.g., 768 → 1536), the startup check
automatically resizes vector columns and **clears all existing embeddings** —
they are not portable across providers (different dimensions and incompatible
vector spaces). Embeddings regenerate automatically in the background with the
new provider. Your metadata (glossary, metrics, dictionary) is preserved; only
the embedding vectors are reset.

## Connecting to a Host Database from Docker

If QueryWise is running in Docker but your target PostgreSQL is running on the host machine, use:

`postgresql://<user>:<password>@host.docker.internal:<port>/<database>`

Example:

`postgresql://qadmin:your-password@host.docker.internal:5434/Adventureworks_aw`

On Linux, if `host.docker.internal` is not resolvable in your containers, add this to the `backend` service in `docker-compose.yml`:

```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

## Connecting to BigQuery

1. Select **BigQuery** as the connector type in the Add Connection form
2. Enter your GCP **Project ID**
3. Paste your **service account JSON key** (the full contents of the key file)
4. Set the **Dataset** name (BigQuery's equivalent of a schema)
5. Click Create, then Test and Introspect

The service account needs the **BigQuery User** role (or equivalent) to run queries. The connection credentials are encrypted at rest using Fernet encryption.

## Connecting to Databricks

1. Select **Databricks** as the connector type in the Add Connection form
2. Enter the **Server hostname** (e.g., `dbc-a1b2345c-d6e7.cloud.databricks.com`)
3. Enter the **HTTP path** for your SQL warehouse or all-purpose cluster (e.g., `/sql/1.0/warehouses/abc123`)
4. Enter a **Personal Access Token** (`dapi...`)
5. Set the **Catalog** (defaults to `main`) and **Schema** (defaults to `default`)
6. Click Create, then Test and Introspect

Works with both **Unity Catalog** (full INFORMATION_SCHEMA introspection including PKs/FKs) and **Hive metastore** (falls back to SHOW/DESCRIBE commands). Credentials are encrypted at rest.
