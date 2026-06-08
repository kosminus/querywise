# QueryWise — Production Config Reference

Every backend setting is an environment variable. The **full catalogue with
defaults** lives in [`../../.env.example`](../../.env.example) and the project
`CLAUDE.md`; this page is the **production-focused** view — what to change, where
to set it, and what's a secret.

## Where settings come from

| Layer | Carries | Source of truth |
|-------|---------|-----------------|
| **Compose (prod)** | everything | `.env.prod` (from `.env.prod.example`) |
| **Helm — non-secret** | tunables, feature flags | `config:` map → ConfigMap (`values.yaml`) |
| **Helm — secret** | keys, DSNs | `querywise-secrets` Secret via `secrets.existingSecret` |
| **Terraform** | DSNs + keys assembled into the cloud secret store | `*.tfvars` |

Secrets must **never** sit in `values.yaml` or a committed overlay — they flow
cloud secret store → external-secrets → `querywise-secrets`.

## Must-set for production

| Setting | Why | Notes |
|---------|-----|-------|
| `DATABASE_URL` | app database | secret; managed pgvector Postgres |
| `REDIS_URL` | cache + arq queue | secret; `JOB_BACKEND=arq` in prod |
| `ENCRYPTION_KEY` | encrypts stored connection strings | **secret; never rotate blind** (see RUNBOOK §4) |
| `JWT_SECRET` | session/magic-link signing | secret; rotating logs everyone out |
| `DISABLE_AUTH=false` | enforce login | **never `true` in prod** |
| `AUTH_COOKIE_SECURE=true` | HTTPS-only session cookie | TLS terminates at the edge/ingress |
| `CORS_ORIGINS` | allowed browser origins | JSON list; same-origin needs none |
| `AUTO_SETUP_SAMPLE_DB=false` | no IFRS-9 seed in prod | point at real warehouses |
| LLM provider + key | SQL generation + embeddings | `DEFAULT_LLM_PROVIDER` + the matching `*_API_KEY` (secret) |
| `EMBEDDING_DIMENSION` | vector column size | 1536 (OpenAI/Anthropic) / 768 (Ollama nomic) — must match the model |

## Operational tunables (non-secret)

| Setting | Default | Effect |
|---------|---------|--------|
| `UVICORN_WORKERS` | 4 | uvicorn processes per backend pod/container |
| `LOG_FORMAT` | `json` (prod) | structured logs for aggregation |
| `LOG_LEVEL` | `INFO` | verbosity |
| `ENABLE_METRICS` | `true` | Prometheus at `GET /metrics` |
| `OTEL_ENABLED` / `OTEL_EXPORTER_OTLP_ENDPOINT` | `false` / — | tracing to Jaeger/Tempo/Collector |
| `RATE_LIMIT_ENABLED` / `MAX_QUERIES_PER_MINUTE` | `true` / 30 | `/query` throttle |
| `DEFAULT_QUERY_TIMEOUT_SECONDS` / `DEFAULT_MAX_ROWS` | 30 / 1000 | query guardrails |
| `SECRETS_BACKEND` | `env` | `aws`/`gcp`/`azure`/`vault` for managed connection-string encryption |

## Scaling knobs (Helm `values.yaml`)

| Value | Purpose |
|-------|---------|
| `backend.autoscaling.{enabled,min,max,targetCPU}` | HPA on the API |
| `backend.replicaCount` | fixed replicas when HPA off |
| `worker.replicaCount` | arq worker concurrency (separate pods) |
| `frontend.replicaCount` | edge replicas |
| `*.podDisruptionBudget` | availability during node drains |
| `ingress.{host,className,annotations,tls}` | routing + TLS |
| `image.{backend,frontend}.{repository,tag}` | which images (CI injects `tag`) |

## Cross-checks

- `EMBEDDING_DIMENSION` must match the embedding model, or startup resizes the
  vector columns and nulls embeddings (they regenerate in the background).
- `JOB_BACKEND=arq` ⇒ a running `worker` and a reachable `REDIS_URL`.
- `AUTH_COOKIE_SECURE=true` ⇒ the app is served over HTTPS (else the cookie is
  dropped and login silently fails).
