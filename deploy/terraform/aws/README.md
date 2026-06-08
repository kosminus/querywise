# QueryWise on AWS — Terraform (data plane + secrets)

Provisions the **managed dependencies** the QueryWise Helm chart needs, in your
own VPC — your data never leaves your account:

- **RDS PostgreSQL 16** (pgvector-ready, encrypted, Multi-AZ, gp3, TLS enforced)
- **ElastiCache Redis** (result cache + the arq job queue)
- **Secrets Manager** secret with the assembled DSNs + keys
- **S3** bucket for exports / `pg_dump` backups (optional)
- **VPC + private subnets** (optional — or drop into an existing VPC)
- **IAM policy** to read the app secret (for the external-secrets IRSA role)

**Compute is intentionally out of scope.** Provision EKS (or ECS) separately —
BYO, or the upstream [`terraform-aws-modules/eks`](https://github.com/terraform-aws-modules/terraform-aws-eks)
module — then deploy the app with the Helm chart in [`../../helm/querywise`](../../helm/querywise).
Keeping the data plane and the cluster in separate states means a `helm`
rollback or cluster rebuild never risks the database.

## Usage

```bash
cp terraform.tfvars.example terraform.tfvars   # then edit
terraform init
terraform apply
```

Wire the outputs into the cluster. The recommended path is the
**external-secrets operator** reading the Secrets Manager secret:

1. `terraform output secret_access_policy_arn` → attach to an IAM role whose
   trust policy references your EKS OIDC provider, bound to the external-secrets
   ServiceAccount (IRSA).
2. Create an `ExternalSecret` that pulls `terraform output app_secret_name`
   with a `dataFrom` extract into a Kubernetes Secret named `querywise-secrets`
   (its keys — `DATABASE_URL`, `REDIS_URL`, `ENCRYPTION_KEY`, `JWT_SECRET`,
   `OPENAI_API_KEY`, … — already match the backend's env).
3. Install the chart pointing at it:

   ```bash
   helm upgrade --install querywise ../../helm/querywise -n querywise \
     --set secrets.existingSecret=querywise-secrets \
     --set config.AUTO_SETUP_SAMPLE_DB=false
   ```

Make sure `allowed_security_group_ids` includes the EKS node/pod security group
so pods can reach Postgres + Redis.

> **Quick-start without external-secrets:** feed the DSNs straight into the
> chart's own Secret — but `database_url` / `redis_url` are sensitive outputs, so
> avoid this for anything but a sandbox.

## pgvector

The `vector` extension ships with RDS PostgreSQL 16 and is created by the app's
Alembic migrations (`CREATE EXTENSION IF NOT EXISTS vector`) on first
`helm upgrade` (the migration hook). No parameter-group change required.

## Notes

- `db_deletion_protection = true` (default) blocks `terraform destroy` of the DB
  and forces a final snapshot. Set to `false` for throwaway environments.
- The master DB password and JWT secret are generated if not supplied and stored
  only in Secrets Manager / Terraform state — keep your state backend encrypted.
