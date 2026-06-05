# Changelog

All notable changes to QueryWise are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - Unreleased

Start of the platform line: evolving QueryWise from a single-tenant text-to-SQL
tool into a governed, self-service semantic data platform. This release covers
**Phase 0 — production hardening & async/observability foundation** (no new
product surface; all optional dependencies degrade gracefully).

### Added
- **Pluggable secrets backend** (`app/core/secrets.py`) — `SecretsProvider` ABC
  behind connection-string encryption. Default `env` (Fernet) backend preserves
  prior behaviour; `aws`/`gcp`/`azure`/`vault` registered as seams.
- **Observability** (`app/core/telemetry.py`) — structured logging
  (structlog→stdlib fallback, `console`/`json`), per-request `X-Request-ID`
  middleware, Prometheus metrics at `GET /metrics`, and OpenTelemetry tracing
  (`OTEL_ENABLED`) with spans across the query pipeline.
- **Rate limiting** (`app/core/rate_limit.py`) — sliding-window limiter
  enforcing `MAX_QUERIES_PER_MINUTE` on `/query` endpoints.
- **Async job runner** (`app/jobs/`) — `JobQueue` ABC with `InProcessJobQueue`
  (default) and `ArqJobQueue` (Redis); named-job registry and an arq worker
  entrypoint (`arq app.jobs.worker.WorkerSettings`).
- **Health probes** — `GET /health/live` and `GET /health/ready` (database, job
  queue, LLM provider) for Kubernetes.
- **Azure OpenAI provider** (`azure_openai`) so the pipeline can run inside a
  customer VPC.
- **Tests & CI** — unit test suite under `backend/tests/` (no DB/LLM required)
  and a GitHub Actions workflow (pytest gating; ruff/mypy/frontend advisory).
- New optional dependency extras: `observability` and `jobs`.

### Changed
- `connection_service.py` now encrypts/decrypts via the configured secrets
  backend instead of a hard-wired Fernet key.
- Background embedding generation is submitted through the job queue rather than
  a bare `asyncio.create_task`.

## [1.0.0] - 2026-06-04

First stable release: natural-language-to-SQL with a semantic metadata layer.

### Added
- NL → SQL → answer pipeline — Composer, Validator, Error Handler, and
  Interpreter agents with an automatic retry loop.
- Semantic layer — glossary, metrics, data dictionary, knowledge documents, and
  validated sample queries, all pgvector-embedded.
- Connectors (read-only) — PostgreSQL, BigQuery, and Databricks (Unity Catalog
  + Hive metastore).
- LLM providers — Anthropic, OpenAI, and Ollama, selected by a complexity router.
- Knowledge import with section-aware chunking and hybrid vector + keyword
  retrieval.
- MCP server exposing QueryWise tools at `/mcp`.
- IFRS 9 sample database with automatic connection, introspection, and metadata
  seeding on first boot.

[2.0.0]: https://github.com/kosminus/querywise/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/kosminus/querywise/releases/tag/v1.0.0
