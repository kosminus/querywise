# Deploying QueryWise

Production deployment artifacts. Single-tenant per deployment; isolation is by
workspace within the auto-created default organization. The app is a
**build-once image configured entirely by env** — the same backend/frontend
images run under Docker Compose, Helm, or any of the cloud targets.

| Target | Where | Best for |
|--------|-------|----------|
| **Docker Compose (prod)** | [`../docker-compose.prod.yml`](../docker-compose.prod.yml) | Small / on-prem, single host |
| **Helm chart** | [`helm/querywise/`](helm/querywise) | EKS / GKE / AKS |
| **Terraform — AWS** | [`terraform/aws/`](terraform/aws) | RDS pgvector + ElastiCache + Secrets Manager + S3, in your VPC |
| **Terraform — GCP** | [`terraform/gcp/`](terraform/gcp) | Cloud SQL pgvector + Memorystore + Secret Manager + GCS |
| **Terraform — Azure** | [`terraform/azure/`](terraform/azure) | Postgres flexible server + Cache for Redis + Key Vault + Blob |
| **Ops** | [`ops/`](ops) | Backup/restore, DR runbook, config reference |

External dependencies (not bundled in the Helm chart): **managed PostgreSQL 16
with the `pgvector` extension** and **Redis** (cache + the arq job queue). The
Terraform modules provision these; for the chart you supply their DSNs via the
release Secret.

## Images

Built from `backend/Dockerfile.prod` and `frontend/Dockerfile.prod`:

```bash
docker build -f backend/Dockerfile.prod  -t ghcr.io/your-org/querywise-backend:1.0.0  backend
docker build -f frontend/Dockerfile.prod -t ghcr.io/your-org/querywise-frontend:1.0.0 frontend
docker push ghcr.io/your-org/querywise-backend:1.0.0
docker push ghcr.io/your-org/querywise-frontend:1.0.0
```

Both run **non-root**; the frontend serves the SPA and the backend is uvicorn
with an arq worker alongside. The SPA is built same-origin (`VITE_API_URL=""`),
so the edge / ingress routes `/api` + `/mcp` to the backend and everything else
to the frontend.

## Helm

```bash
# 1. Provide secrets — ideally via external-secrets / sealed-secrets:
kubectl create namespace querywise
kubectl -n querywise create secret generic querywise-secrets \
  --from-literal=DATABASE_URL='postgresql+asyncpg://user:pass@host:5432/querywise' \
  --from-literal=REDIS_URL='redis://host:6379/0' \
  --from-literal=ENCRYPTION_KEY='...' \
  --from-literal=JWT_SECRET='...' \
  --from-literal=OPENAI_API_KEY='...'

# 2. Install (a pre-upgrade hook runs `alembic upgrade head` before pods roll):
helm upgrade --install querywise deploy/helm/querywise \
  -n querywise \
  -f deploy/helm/querywise/values-production.example.yaml \
  --set secrets.existingSecret=querywise-secrets
```

Key chart features:

- **Migration hook** — `alembic upgrade head` runs as a `pre-install`/`pre-upgrade`
  Job (ordered after the config/secret hooks) so schema changes land before new
  backend code serves and the N replicas never race.
- **Scaling** — backend HPA (CPU), PodDisruptionBudgets on backend + frontend,
  dedicated arq `worker` Deployment.
- **Secrets seam** — `secrets.existingSecret` to bring your own (external-secrets
  operator, sealed-secrets, cloud sync) instead of putting values in the release.
- **Service account annotations** — for IRSA (EKS) / Workload Identity (GKE) /
  Azure Workload Identity.

See [`helm/querywise/values.yaml`](helm/querywise/values.yaml) for the full set
of knobs and [`values-production.example.yaml`](helm/querywise/values-production.example.yaml)
for a realistic production override.

### Validate locally

```bash
helm lint deploy/helm/querywise
helm template querywise deploy/helm/querywise | kubeconform -strict -summary
```

## CI/CD

Two GitHub Actions workflows under [`../.github/workflows`](../.github/workflows):

- **`deploy-validate.yml`** (PRs touching `deploy/**`) — `helm lint` + `helm
  template | kubeconform -strict`, and `terraform fmt -check` + `validate` for
  each of aws/gcp/azure. Keeps a broken chart or module from merging.
- **`release.yml`** — builds + pushes both images to GHCR
  (`ghcr.io/<owner>/querywise-{backend,frontend}`, tagged with the commit SHA,
  branch, semver, and `latest`), then deploys with Helm via the
  [`helm-deploy`](../.github/actions/helm-deploy) composite action:
  - **push to `main`** → deploy to the **staging** environment
  - **push tag `v*`** → deploy to the **production** environment (gate it with
    required reviewers in the environment's protection rules for manual approval)
  - **manual run** → build only

Both deploys pin the release to the exact commit SHA (`--wait --atomic`, so a
failed rollout auto-reverts) and inject only the image coordinates; everything
else comes from the chart defaults plus an optional committed overlay
`deploy/helm/querywise/values-<environment>.yaml` (see the `*-staging` /
`*-production` examples).

### Required GitHub config

| What | Where | Value |
|------|-------|-------|
| `DEPLOY_ENABLED` | Repository **variable** (Actions → Variables) | `true` to enable the deploy jobs; unset/anything else and they are skipped (the workflow still builds + pushes images) |
| `KUBE_CONFIG` | Environment secret on **staging** and **production** | base64-encoded kubeconfig for that cluster |
| Required reviewers | **production** environment protection rules | who approves prod deploys |
| Packages: write | repo default `GITHUB_TOKEN` | already granted in the workflow |

The clusters are expected to run the **external-secrets operator** syncing the
cloud secret store (provisioned by Terraform) into the `querywise-secrets`
Kubernetes Secret the chart references.

## Operations

Day-2 procedures live in [`ops/`](ops):

- **Backups** — [`ops/backup.sh`](ops/backup.sh): `pg_dump` (custom format) →
  AES-256 (openssl) → `querywise-<ts>.dump.enc`, with optional S3/GCS upload and
  local retention. Schedule it in-cluster with
  [`ops/backup-cronjob.example.yaml`](ops/backup-cronjob.example.yaml).
- **Restore** — [`ops/restore.sh`](ops/restore.sh): decrypt → `pg_restore
  --clean --if-exists` (guarded by `RESTORE_CONFIRM=yes`).
- **Runbook** — [`ops/RUNBOOK.md`](ops/RUNBOOK.md): backup/restore, full-region
  DR rebuild, the Alembic upgrade path, and quarterly credential rotation
  (including the `ENCRYPTION_KEY` caveat).
- **Config reference** — [`ops/config-reference.md`](ops/config-reference.md):
  every production-critical setting, where it's set, and what's a secret.
