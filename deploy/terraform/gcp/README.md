# QueryWise on GCP — Terraform (data plane + secrets)

Provisions the managed dependencies the Helm chart needs, in your project:

- **Cloud SQL PostgreSQL 16** (pgvector-ready, private IP, regional HA, PITR, TLS-only)
- **Memorystore for Redis** (result cache + the arq job queue)
- **Secret Manager** secret with the assembled DSNs + keys
- **GCS** bucket for exports / `pg_dump` backups (optional)
- **VPC + private-services-access** peering (optional — or BYO VPC with PSA)
- **Service account** with `secretAccessor` for the external-secrets operator

**Compute (GKE / Cloud Run) is out of scope** — BYO or the upstream
[`terraform-google-modules/kubernetes-engine`](https://github.com/terraform-google-modules/terraform-google-kubernetes-engine)
module — then deploy with the Helm chart in [`../../helm/querywise`](../../helm/querywise),
keeping the cluster in a separate state from the database.

## Usage

```bash
cp terraform.tfvars.example terraform.tfvars   # then edit
terraform init
terraform apply
```

Wire it up with the external-secrets operator on GKE:

1. Bind the service account to the external-secrets KSA with Workload Identity:
   ```bash
   gcloud iam service-accounts add-iam-policy-binding \
     "$(terraform output -raw external_secrets_sa_email)" \
     --role roles/iam.workloadIdentityUser \
     --member "serviceAccount:PROJECT.svc.id.goog[external-secrets/external-secrets]"
   ```
2. Create an `ExternalSecret` that pulls `terraform output app_secret_id` with a
   `dataFrom` extract into a Kubernetes Secret named `querywise-secrets` (its
   keys already match the backend's env).
3. Install the chart:
   ```bash
   helm upgrade --install querywise ../../helm/querywise -n querywise \
     --set secrets.existingSecret=querywise-secrets
   ```

GKE must sit on the same VPC (or a peered one) so pods reach the Cloud SQL
private IP and Memorystore host.

## pgvector

The `vector` extension is created by the app's Alembic migrations on first
`helm upgrade` (the migration hook). No instance flag required.

## Notes

- `db_deletion_protection = true` (default) blocks destroying the instance.
- Generated DB password / JWT secret live only in Secret Manager + Terraform
  state — keep your state backend (a GCS bucket) encrypted and access-controlled.
