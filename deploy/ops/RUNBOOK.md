# QueryWise — Operations & DR Runbook

Operational procedures for a production QueryWise deployment: backups, restore /
disaster recovery, schema upgrades, and credential rotation. Pairs with the
deploy artifacts in [`../`](../) (Helm chart, Terraform, CI/CD).

Two stateful systems hold everything that matters:

| System | Holds | Recovery source |
|--------|-------|-----------------|
| **App Postgres (pgvector)** | metadata, semantic layer, saved queries, dashboards, users, history, embeddings | logical backups (below) + managed PITR |
| **Cloud secret store** | `ENCRYPTION_KEY`, `JWT_SECRET`, DSNs, LLM keys | your IaC / secret manager |

Redis is a **cache + transient job queue** — it is not a source of truth and
needs no backup (embeddings regenerate; the cache repopulates).

---

## 1. Backups

The managed databases provisioned by the Terraform modules already have
**automated snapshots + PITR** (RDS backup retention, Cloud SQL PITR, Azure
flexible-server backups). Logical backups via `backup.sh` are the second layer —
portable, offsite-able, and restorable to any Postgres.

**What's covered:** the entire app database (schema + data, including pgvector
columns) in `pg_dump` custom format, AES-256 encrypted.

### Run a one-off backup

```bash
export DATABASE_URL='postgresql://querywise:…@db-host:5432/querywise'
export BACKUP_PASSPHRASE='…'         # from your secret store
./backup.sh                          # -> ./backups/querywise-<ts>.dump.enc
# Offsite: also set BACKUP_S3_URI=s3://… or BACKUP_GCS_URI=gs://…
```

From a cluster without DB network exposure, exec through a pod:

```bash
kubectl -n querywise exec deploy/querywise-backend -- \
  sh -c 'DATABASE_URL="$DATABASE_URL" BACKUP_PASSPHRASE="$BACKUP_PASSPHRASE" ...'
# or apply the scheduled CronJob — see backup-cronjob.example.yaml
```

### Scheduled backups

Apply [`backup-cronjob.example.yaml`](backup-cronjob.example.yaml) for nightly
encrypted dumps to a PVC (or offsite). **Verify restores quarterly** — an
untested backup is not a backup (see §2.3).

---

## 2. Restore / Disaster Recovery

**Targets:** RPO ≈ last backup / PITR window (minutes with managed PITR); RTO ≈
time to provision a DB + restore (tens of minutes).

### 2.1 Data loss / corruption (DB intact)

Prefer the managed DB's **point-in-time recovery** — restore to a timestamp just
before the bad change (RDS/Cloud SQL/Azure console or Terraform). This avoids
losing everything since the last logical dump.

### 2.2 Restore from a logical backup

```bash
export DATABASE_URL='postgresql://querywise:…@new-db-host:5432/querywise'
export BACKUP_PASSPHRASE='…'
RESTORE_CONFIRM=yes ./restore.sh ./backups/querywise-<ts>.dump.enc
```

Then make the schema current (the dump may predate a migration):

```bash
kubectl -n querywise create job --from=cronjob/none qw-migrate || true   # or:
kubectl -n querywise exec deploy/querywise-backend -- alembic upgrade head
# Simplest: re-run `helm upgrade` — the pre-upgrade hook runs the migration.
```

### 2.3 Full region/cluster loss (clean-room rebuild)

1. **Infra:** `terraform apply` the relevant `deploy/terraform/<cloud>` module in
   the recovery region → new Postgres, Redis, secret store, networking.
2. **Secrets:** restore the cloud secret values (or re-generate — but **keep the
   original `ENCRYPTION_KEY`**, see §4, or stored connection strings become
   undecryptable).
3. **Data:** `restore.sh` the latest backup into the new Postgres.
4. **App:** point kubeconfig at the recovery cluster, install external-secrets,
   `helm upgrade --install` the chart. The migrate hook reconciles the schema.
5. **DNS/TLS:** repoint the hostname to the new ingress; re-issue certs.
6. **Verify:** `GET /api/v1/health/ready` is 200; run a known query; confirm a
   saved query + dashboard render.

---

## 3. Schema upgrades (Alembic)

Migrations live in `backend/alembic/versions`. The normal path is automatic:

- **Helm:** every `helm upgrade` runs `alembic upgrade head` as a
  `pre-install`/`pre-upgrade` hook Job **before** new backend pods roll, so code
  and schema move together and replicas never race (the migrate hook is the only
  place migrations run).
- **Compose:** the `migrate` service runs once before backend/worker start.

**Manual** (rarely needed):

```bash
kubectl -n querywise exec deploy/querywise-backend -- alembic current
kubectl -n querywise exec deploy/querywise-backend -- alembic upgrade head
```

**Rollback:** Alembic `downgrade` exists but data-dropping migrations are not
safely reversible — prefer rolling **forward** with a fix migration, or restore
from backup (§2). Always take a backup before a major upgrade.

---

## 4. Credential rotation (quarterly)

Rotate on a quarterly cadence (and immediately on suspected compromise). All
secrets live in the cloud secret store; external-secrets syncs them into the
`querywise-secrets` Kubernetes Secret, then restart pods to pick up changes:

```bash
kubectl -n querywise rollout restart deploy/querywise-backend deploy/querywise-worker
```

| Secret | Procedure | Blast radius |
|--------|-----------|--------------|
| **DB password** | Change the master password on the managed DB (cloud/Terraform), update `DATABASE_URL` in the secret store, restart pods. | Brief; pods reconnect. |
| **`JWT_SECRET`** | New random value in the secret store, restart pods. | All sessions invalidated + pending magic links — users re-login. |
| **LLM API keys** | Rotate at the provider, update the secret, restart pods. | None if overlapping validity. |
| **User API keys** | Per-user via `/api-keys` (only the SHA-256 hash is stored; plaintext shown once). | Per key. |
| **`ENCRYPTION_KEY`** | ⚠️ **Do not blind-rotate.** This Fernet key encrypts stored DB-connection strings; a new key cannot decrypt existing ones. To rotate: decrypt each connection with the old key and re-save with the new one (or re-enter connection credentials in the UI), *then* swap the key. Keep the old key available until every connection is re-encrypted. | Connections become unusable until re-encrypted. |

> Prefer cloud-managed rotation where available (e.g. Secrets Manager rotation
> for the DB password) so rotation is automatic and audited.

---

## 5. Quick reference

```bash
# Health
kubectl -n querywise get pods
curl -fsS https://<host>/api/v1/health/ready

# Logs (JSON in prod — pipe to jq)
kubectl -n querywise logs deploy/querywise-backend --tail=200

# Roll back a bad release (Helm keeps history)
helm -n querywise history querywise
helm -n querywise rollback querywise <REVISION>

# Scale
kubectl -n querywise scale deploy/querywise-backend --replicas=4   # if HPA disabled
```

See [`config-reference.md`](config-reference.md) for every tunable and which
ones must change for production.
