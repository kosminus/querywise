# QueryWise → Governed Self-Service Data Platform — Consolidated Plan

> **Date:** 2026-06-04
> **Goal:** Evolve QueryWise from a single-tenant text-to-SQL tool into a **governed,
> self-service semantic data platform** — multiple users and teams discover, govern, and
> query company data through trusted business definitions and AI-assisted SQL.
>
> **This plan is a synthesis** of six prior drafts. It takes:
> - the **code-grounded spine, sequencing, and "durable artifact" thesis** from `planclaud.md`,
> - the **governance/trust depth and SaaS-ready schema** from `plancodex.md`,
> - the **concrete deployment/packaging artifacts** from `qwenplan.md`,
> and deliberately **rejects** shared-multi-tenant-first (`miniplan.md`) and write/ingestion
> scope-creep (`plandeep.md`).

---

## 1. The locked decision

**Single-tenant, multi-user — self-hostable, SaaS-ready, read-only.**

- **Single-tenant** — each deployment serves one company; isolation is by `workspace_id`
  *within* the deployment. No shared-DB multi-tenancy.
- **Multi-user** — real users, teams, roles, ownership, audit.
- **Self-hostable** — packaged to run in the customer's VPC / on-prem; **data never leaves
  their environment**. Managed SaaS later = a *fleet of isolated single-tenant instances*,
  not a rewrite.
- **SaaS-ready schema** — carry an `organization_id` from day one (default org auto-created
  on boot) even while single-tenant, so the managed offering needs no migration later.
  *(This is the one place we follow `plancodex` over `planclaud`: cheap now, no rewrite later.)*
- **Read-only preserved** — the connector contract stays SELECT-only. Transforms, ingestion,
  and streaming are explicitly **out of scope** (that is a different product; see Non-Goals).

### Why this shape
QueryWise is a *data-adjacent* tool: a deployment holds warehouse credentials, sampled data
values sent to an LLM, the company's semantic IP (glossary/metrics), and query results that
may be regulated (the bundled sample is IFRS 9 banking data). Buyers in this category refuse
to put warehouse keys + results into a shared multi-tenant SaaS. Single-tenant gives physical
isolation and a clean compliance story ("your data stays in your account") with a small delta
from today's code.

---

## 2. Current state (verified baseline)

| Capability | State |
|---|---|
| NL → SQL → answer pipeline — 4 agents (Composer → Validator → ErrorHandler → Interpreter), retry loop in `query_service.py` | ✅ Solid |
| Semantic layer (glossary, metrics, dictionary, knowledge, sample queries) — all pgvector-embedded | ✅ Core differentiator |
| Connectors — Postgres (always), BigQuery / Databricks (optional), `BaseConnector` ABC, **read-only enforced** | ✅ |
| Provider registry + complexity router (Anthropic / OpenAI / Ollama) | ✅ |
| Query history / audit | ⚠️ Per-execution; `user_id` is **free-text string**, not a FK |
| Auth / users / RBAC | ❌ None — no login, no middleware |
| Workspaces / teams | ❌ Data keyed only to `connection_id` |
| Durable artifacts (saved queries, charts, dashboards) | ❌ Answers are one-shot |
| Async job runner / scheduling | ❌ Embeddings run via `asyncio.create_task` in `setup_service.py`; no queue, no Redis |
| Catalog / discovery UX | ⚠️ Schema cache (`CachedTable`/`Column`/`Relationship`) exists, no browse UI |
| Governance (audit log, policy, PII, certification) | ❌ Only read-only + SQL blocklist (`sql_sanitizer.py`) |
| Observability / cost | ⚠️ Token fields exist on `QueryExecution`, nothing aggregated |
| Secrets | ⚠️ Single Fernet `ENCRYPTION_KEY`, SHA256-derived |
| Migrations | Alembic, 3 versions (001–003) |
| Deployment | docker-compose only (app-db pgvector, sample-db, backend, frontend, optional ollama) |
| Rate limiting | ⚠️ `max_queries_per_minute=30` defined but **never enforced** |

**Core gap:** the unit of value today is a *single ephemeral answer*. A self-service platform's
unit of value is a *durable, shareable, governed artifact* (certified metric → chart → dashboard
→ scheduled report).

---

## 3. The four product pillars

1. **Identity & access** — real auth, users, teams, roles, ownership, audit.
2. **Durable analytics artifacts** — saved questions → charts → dashboards → scheduled reports.
3. **Discovery & trust** — data catalog over the schema cache + semantic layer, with certification,
   lineage, and policy.
4. **Platform plumbing** — async job runner, caching, observability, cost controls, deployability.

---

## 4. Phased roadmap

Sequence: **Phase 0–1 are foundations (~6–7 wks), Phase 2 delivers the headline self-service value,
Phases 3–4 make it trustworthy and automated.** Packaging runs as a parallel track from Phase 0.
Rough total: **~4–5 months** for a small team to a credible v1.

> **Why this order (load-bearing):** every artifact in Phases 2–4 needs an owner + ACL, and
> everything later needs durable async jobs. Retrofitting ownership onto shared artifacts, or
> migrating sync→async after the surface has grown, is far more painful than doing it first.

---

### Phase 0 — Production hardening & async foundation (2–3 wks) · *no new product surface*

**Why first:** scheduling, dashboards, and large extracts all need durable jobs; the deployability
story needs pluggable secrets + LLM endpoints while the surface is still small.

- **Async job runner.** Add a task queue — **`arq`** (async-native, Redis) to match the
  async-everywhere convention; Celery/RQ acceptable. Move embedding generation (currently
  `launch_background_embeddings` / `asyncio.create_task` in `setup_service.py`) and long-running
  queries onto it. *(Alternative for tiny deploys: a DB-backed `jobs` table + worker process,
  upgrade to Redis when concurrency grows — per `plancodex`.)*
- **Observability.** Structured JSON logging (`structlog`) with request IDs propagated through
  the pipeline and background tasks; OpenTelemetry tracing across context build → route → compose
  → validate → execute → interpret; Prometheus `/metrics`. Aggregate the existing
  `llm_input_tokens` / `llm_output_tokens` into a cost view.
- **Pluggable secrets backend.** Abstract the Fernet `ENCRYPTION_KEY` path in `connection_service.py`
  behind a `SecretsProvider` interface: env (default) → AWS Secrets Manager / GCP Secret Manager /
  Azure Key Vault / HashiCorp Vault. Track credential version + last-rotation time.
- **Pluggable LLM/embedding endpoint.** Extend the provider registry with **Bedrock / Vertex /
  Azure OpenAI** so the whole pipeline can run inside a customer VPC (already have Anthropic/
  OpenAI/Ollama).
- **Enforce rate limiting.** Wire the unused `max_queries_per_minute` into middleware.
- **Health checks.** `/health/live` (process) and `/health/ready` (app DB, worker, LLM provider,
  embedding provider) for K8s probes.
- **Test & CI baseline.** Integration tests for the pipeline, connectors, semantic context builder,
  SQL sanitizer, and Alembic up/down — *before* the refactors land.

**Touches:** new `app/jobs/`, `app/core/secrets.py`, `app/core/telemetry.py`; refactor
`setup_service.py`, `connection_service.py`, `llm/provider_registry.py`, `app/main.py`.

**Exit:** embeddings run on the queue; traces visible; secrets pluggable; one non-default LLM
backend (Bedrock/Vertex/Azure) works end-to-end; `/health/ready` green.

---

### Phase 1 — Identity, teams & ownership (3–4 wks) · *the unlock for everything else*

Biggest structural change; gates Phases 2–4.

- **AuthN:** OIDC/OAuth2 (Google / Okta / Entra) + session/JWT middleware in FastAPI; magic-link
  as the lowest-friction default for first-run. Frontend login flow. `DISABLE_AUTH=true` escape
  hatch for local dev (sidesteps OIDC setup).
- **New core models:** `Organization` (default org auto-created on boot), `User`, `Team`/`Workspace`
  (isolation unit within the company), `Membership` (user ↔ team, role: `admin | editor | viewer`),
  `ApiKey` for programmatic access.
- **AuthZ:** role checks as FastAPI dependencies (`get_current_user`, `get_org_context`,
  `require_role`) — enforce in **services**, not endpoints (matches existing convention).
- **Re-key data.** Add `organization_id` to all core tables (SaaS-ready) and `workspace_id` to
  `DatabaseConnection` (today's cascade root); promote existing `created_by` columns on
  glossary/metric/sample_query to real `User` FKs; make `QueryExecution.user_id` a real FK.
- **Migration (nullable → backfill → NOT NULL):** create a default org + workspace, assign all
  existing rows, verify zero orphans, then enforce NOT NULL. Add `(org_id, created_at)` indexes.
  Rollback = `DISABLE_AUTH=true` + Alembic downgrade + pg_dump restore.

**Touches:** new `app/db/models/{organization,user,team,membership,api_key}.py`, `app/core/auth.py`,
`alembic/versions/004_*`; service authorization in `connection_service.py`, `query_service.py`,
metadata services; `frontend/` login + auth context + workspace switcher.

**Exit:** SSO login works; a viewer cannot edit the semantic layer; connections/artifacts scoped
to workspaces; existing data migrated into the default org/workspace with no loss; cross-org reads
denied even though the deployment is single-tenant.

---

### Phase 2 — Durable analytics artifacts (4–6 wks) · *the core self-service value*

Turn one-shot answers into saved, reusable, shareable objects.

- **`SavedQuery`** — named, owned NL question + pinned SQL + typed parameters (`{{date_from}}`,
  `{{region}}`), re-runnable, versioned, clone/fork. (Query history already captures the raw material.)
- **Visualizations** — backend returns typed result metadata; frontend gets a chart layer
  (Mantine + Recharts/ECharts). Persist `chart_config` per saved query (table, line, bar, pie,
  area, scatter).
- **`Dashboard` + `DashboardTile`** — compose saved queries/charts on a grid; per-tile refresh;
  dashboard-level filters (date ranges, dimensions) that flow into SQL (reuse the metrics layer's
  existing `dimensions`/`filters`); sharing scoped by workspace/team.
- **Result persistence + caching** — store result snapshots; add a result cache keyed by
  `(final_sql, connection, params, freshness_window)` so dashboards don't re-hit the warehouse on
  every load. **Decide TTL/invalidation here** (warehouse data changes underneath; invalidate on
  schema change + TTL + manual refresh).
- **Export** — CSV / Excel / JSON for results; PDF for dashboards (later).

**Touches:** new models `saved_query.py`, `chart.py`, `dashboard.py`, `dashboard_tile.py`,
`result_snapshot.py`; endpoints + schemas; extend `query_service.py` for snapshots/cache (Redis or
cache table); new `frontend/src/pages/` (SavedQueries, Charts, Dashboards) + chart components.

**Exit:** a user saves a question, charts it, pins it to a shared dashboard with a date filter, and
reloads it from cache without re-querying the warehouse.

---

### Phase 3 — Discovery, catalog & trust (3–4 wks) · *self-service vs. expert-only*

- **Data catalog UI** over `CachedTable` / `CachedColumn` / `CachedRelationship` + semantic models:
  browse + hybrid full-text (`tsvector`) **and** embedding (pgvector) search across tables, columns,
  glossary, metrics, knowledge. Facets by schema/table/tag/owner. (Embeddings already exist; this is
  mostly read-side + UX.)
- **Column profiling** — null rate, distinct count, min/max, sample values; computed as a job after
  introspection or on a schedule; injected into LLM context ("`credit_rating` has 2.3% nulls; values
  A–E").
- **Certification / trust signals** — mark metrics and saved queries `certified | draft | deprecated`;
  show owner + last-validated. Promote the existing `SampleQuery.is_validated` concept platform-wide.
- **Semantic versioning & approval** — version every semantic object; draft → review → certified →
  deprecated lifecycle with reviewer + changelog + diff view. Validate metric SQL before approval
  (missing columns, ambiguous joins, blocked columns, dialect compatibility).
- **Lightweight lineage** — parse generated SQL (`sqlglot`) to record which tables/columns a saved
  query/dashboard touches; "what depends on this metric" impact view.

**Touches:** new `api/v1/endpoints/catalog.py`; lineage extractor; profiling job; status/version
fields on metric/saved-query models; `frontend/src/pages/CatalogPage.tsx`, semantic approval UI.

**Exit:** a non-technical user searches the catalog, sees certified metrics with owners, and views
what a metric depends on.

---

### Phase 4 — Scheduling, distribution & governance (3–5 wks) · *enterprise self-service*

- **Audit log** — durable `audit_events` for every important action (login, connection CRUD,
  credential rotation, introspection, query generated/executed/blocked, metric created/approved,
  knowledge imported). Fire-and-forget so it never fails the main request; org-scoped; exportable.
- **Scheduled reports** (on the Phase 0 job runner) — run a saved query/dashboard on cron; deliver
  via email/Slack; snapshot + alert-on-threshold.
- **Policy engine** — enforce *before* the connector executes: max rows / max execution time by
  role, allowed schemas/tables by role, blocked columns, role-based **column masking** for PII,
  optional human-approval gate for sensitive tables, "certified-metrics-only" mode per workspace.
  Surface a clear explanation when a query is blocked.
- **Cost & usage analytics** — capture scanned bytes / slot-ms / DBU per execution (BigQuery
  `INFORMATION_SCHEMA.JOBS`, Databricks query profile, PG `pg_stat_statements`); dashboards for
  slowest queries, error rate, most-queried tables, cost per team — built on Phase 0 telemetry.

**Touches:** scheduler in `app/jobs/`; notification adapters (email/Slack); policy layer in
`query_service.py` + connector execution path; `audit_events`, `data_policies`, `cost_attribution`
models; usage dashboards in `frontend/`.

**Exit:** a dashboard emails a team every morning; viewers see PII masked; admins see per-team
cost/usage; every important mutation writes an audit event; a blocked query explains why.

---

### Parallel track — Packaging & deployability (starts Phase 0, hardens through Phase 4)

Makes "single-tenant, multi-deployment" real. *(Deliverables lifted from `qwenplan.md`.)*

- **Hardened images** — multi-stage, non-root, healthchecks; `docker-compose.prod.yml` (app-db
  pgvector, redis, backend + worker replicas, frontend, nginx/TLS) for small/on-prem.
- **Helm chart** (EKS/GKE/AKS) — deployments for backend/worker/frontend, HPA, PDB, ingress,
  external-secrets, configmap/secret.
- **Terraform modules** — AWS (ECS/EKS + RDS/Aurora pgvector + ElastiCache + S3 + Secrets Manager),
  GCP (Cloud Run/GKE + Cloud SQL pgvector + Memorystore + GCS + Secret Manager), Azure equivalents.
  Customer deploys in their own VPC; data never leaves their account.
- **Build-once artifact** — one image configured entirely by env (`AUTH_PROVIDER`, `SECRETS_BACKEND`,
  `LLM_ENDPOINT`, `DATABASE_URL`, `REDIS_URL`). BYO secrets (Phase 0) + BYO LLM endpoint (Phase 0).
- **Observability wiring** — Prometheus metrics, OTel export to Jaeger/Tempo or Cloud Trace, JSON
  logs to CloudWatch/Cloud Logging/Loki.
- **CI/CD** — test → lint/typecheck → build/push image → Helm deploy (staging → prod).
- **Ops** — backup/restore (`pg_dump` + encryption), Alembic-based upgrade path, config reference,
  DR runbook, quarterly credential rotation.
- **(Deferred) SaaS control plane** — provisioning, billing, fleet upgrades for managed
  single-tenant instances. Build only when there's pull for managed hosting; it's additive because
  each tenant is already an isolated instance.

---

## 5. New data model (additions)

```
# Phase 1 — identity (organization_id is SaaS-ready; deployment stays single-tenant)
Organization(id, name, slug, settings, created_at)          # default org auto-created on boot
User(id, email, name, sso_subject, status, created_at)
Team(id, org_id→Organization, name, created_at)             # = Workspace, isolation unit
Membership(id, user_id→User, team_id→Team, role)            # admin|editor|viewer
ApiKey(id, user_id→User, name, key_hash, expires_at, permissions)

DatabaseConnection  + organization_id, + workspace_id→Team, + owner_id, + is_private
GlossaryTerm/Metric/SampleQuery/Knowledge  + organization_id, created_by→User (promote to FK)
QueryExecution      + organization_id, user_id→User (promote to FK)

# Phase 2 — artifacts
SavedQuery(id, org_id, workspace_id, owner_id, name, nl_question, pinned_sql,
           params, version, status, is_public, created_at, updated_at)
Chart(id, org_id, saved_query_id→SavedQuery, chart_type, config)
Dashboard(id, org_id, workspace_id, owner_id, name, layout, filters)
DashboardTile(id, dashboard_id→Dashboard, chart_id→Chart, position, refresh_interval)
ResultSnapshot(id, saved_query_id, columns, rows, row_count, params_used, taken_at)

# Phase 3 — trust
SemanticVersion(id, entity_type, entity_id, version, snapshot, changed_by, change_reason)
ColumnProfile(id, org_id, column_id→CachedColumn, row_count, null_count, distinct_count,
              min, max, sample_values, profiled_at)
ColumnLineage(id, org_id, query_execution_id, source_table, source_column,
              target_table, target_column, transform_type, confidence)
# + certification_state on MetricDefinition / SavedQuery

# Phase 4 — governance
AuditEvent(id, org_id, event_type, actor_id, payload, created_at)
DataPolicy(id, org_id, name, connection_id, filter_condition_sql, applies_to_roles,
           blocked_columns, max_rows, max_runtime, priority, enabled)
ApprovalRequest(id, org_id, query_execution_id, requester_id, approver_id, status, reason)
CostAttribution(id, org_id, query_execution_id, cost_usd, scanned_bytes, slot_ms, source_provider)
Schedule(id, org_id, target_type, target_id, cron, delivery, recipients, threshold)
```

Isolation within a deployment is via `workspace_id`; `organization_id` exists for the future
managed-SaaS fleet but is **not** used to share one DB across customers today.

---

## 6. Concrete first technical changes (mapped to real files)

| Change | Files / area |
|---|---|
| Async job runner (`arq`/Redis) | new `app/jobs/`; refactor `setup_service.py` `launch_background_embeddings` |
| Pluggable secrets (`SecretsProvider`) | new `app/core/secrets.py`; `services/connection_service.py` |
| Pluggable LLM endpoint (Bedrock/Vertex/Azure) | `llm/provider_registry.py`, `llm/providers/` |
| Observability (structlog + OTel + Prometheus) | new `app/core/telemetry.py`; `app/main.py` |
| Enforce rate limit | middleware in `app/main.py` (wire existing `max_queries_per_minute`) |
| Health checks | `app/api/v1/endpoints/health.py` |
| `Organization`/`User`/`Team`/`Membership` + migration | `app/db/models/`, `alembic/versions/004_*` |
| Auth middleware + `get_current_user`/`get_org_context` | new `app/core/auth.py`; wire in `app/main.py` |
| `organization_id` + `workspace_id` backfill | `db/models/connection.py` + all metadata models, migration |
| AuthZ checks in services | `connection_service.py`, `query_service.py`, metadata services |
| `SavedQuery`/`Chart`/`Dashboard`/`DashboardTile` | new models, `api/v1/endpoints/`, `schemas/` |
| Result cache + snapshots | extend `query_service.py`; Redis or cache table |
| Catalog search + profiling | `api/v1/endpoints/catalog.py`; profiling job in `app/jobs/` |
| Semantic versioning + certification | status/version fields on metric/sample-query models |
| Lineage extractor | `sqlglot` over `QueryExecution.final_sql` |
| Audit log + policy engine | `audit_events`, `data_policies`; hook into `query_service.py` execution path |
| Charting + dashboard UI | `frontend/src/pages/`, new hooks/api clients |
| Helm chart + Terraform modules | new `deploy/` (helm/, terraform/aws|gcp|azure) |

---

## 7. Key risks & decisions

- **Auth retrofit is load-bearing.** Every artifact in Phases 2–4 needs an owner + ACL. Don't defer Phase 1.
- **Sync → async migration** touches the pipeline; do it early (Phase 0) while the surface is small.
- **Result caching + freshness** is subtle (warehouse data changes). Decide TTL/invalidation before dashboards depend on it.
- **Governance scope creep.** Row/column security can balloon; start with role-based column masking + row-filter injection.
- **LLM cost at platform scale.** Scheduled dashboards multiply LLM/warehouse calls — the result cache and `llm/router.py` heuristics become cost-critical.
- **Multi-tenant data leakage** (once managed SaaS arrives) — RLS + query-level scoping + audit + pen-test. Until then, isolation is physical (one deployment per customer).
- **Single-tenant ops cost.** Managed SaaS = N instances; defer the control plane until demand justifies it.

### Decisions to confirm before build
1. Job queue: **`arq`** (recommended) vs Celery/RQ vs DB-backed table.
2. First OIDC IdPs: Google / Okta / Entra (+ magic-link for first-run).
3. Charting library: Recharts vs ECharts vs Visx.
4. Result cache store: Redis vs Postgres table.
5. First non-default LLM backend for VPC deploys: Bedrock vs Vertex vs Azure OpenAI.
6. Secrets backend priority order: AWS SM / GCP SM / Azure KV / Vault.

---

## 8. Non-goals (first version)

- **No shared multi-tenant SaaS first** — single-tenant; `organization_id` is schema-ready only.
- **No write path** — connectors stay read-only. No transforms (CTAS), no ingestion, no streaming/CDC.
  That is a separate data-engineering product, not this evolution.
- **No dashboards before auth, jobs, catalog, audit, and policy** exist.
- **No new connectors** before the connector contract is hardened and tested.
- **No raw result storage by default** unless a retention policy is explicit.
- **No LLM-generated SQL bypassing semantic governance or policy.**

---

## 9. Rollout summary

| Phase | Focus | Duration | Headline deliverables |
|---|---|---|---|
| **0** | Hardening & async foundation | 2–3 wks | arq jobs, structlog+OTel+Prometheus, pluggable secrets/LLM, health, rate limit, tests |
| **1** | Identity, teams & ownership | 3–4 wks | OIDC auth, Org/User/Team/Membership, org+workspace scoping, audit FKs, migration |
| **2** | Durable analytics artifacts | 4–6 wks | Saved queries, charts, dashboards, result cache/snapshots, export |
| **3** | Discovery, catalog & trust | 3–4 wks | Catalog search, profiling, certification, semantic versioning/approval, lineage |
| **4** | Scheduling, distribution & governance | 3–5 wks | Audit log, scheduled reports, policy engine + masking, cost/usage analytics |
| **‖** | Packaging (parallel) | from Phase 0 | Prod compose, Helm, Terraform (AWS/GCP/Azure), CI/CD, BYO secrets/LLM, backups |

**Total: ~4–5 months** to a deployable, governed, multi-user single-tenant data platform.

### Positioning
> A deployable semantic data platform that lets teams discover, govern, and query company data
> through trusted business definitions and AI-assisted SQL — **in your cloud or ours.**

---

## Implementation status

| Phase | Status | Reference |
|---|---|---|
| **0** — Production hardening & async foundation | ✅ Implemented | PR #7 (→ v2.0.0) |
| **1** — Identity, teams & ownership | ✅ Backend implemented (frontend pending) | migration `004`; OIDC is a registered seam (magic-link + local live) |
| **2** — Durable analytics artifacts | ⬜ Not started | — |
| **3** — Discovery, catalog & trust | ⬜ Not started | — |
| **4** — Scheduling, distribution & governance | ⬜ Not started | — |

> Integration + Alembic test coverage for the Phase 0 CI baseline is tracked in issue #8.
