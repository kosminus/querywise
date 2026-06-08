# QueryWise on Azure — Terraform (data plane + secrets)

Provisions the managed dependencies the Helm chart needs, in your subscription:

- **Azure Database for PostgreSQL flexible server 16** (pgvector allow-listed,
  VNet-integrated/private, zone-redundant HA, TLS-only)
- **Azure Cache for Redis** (result cache + the arq job queue, TLS-only)
- **Key Vault** secret with the assembled DSNs + keys
- **Storage account + container** for exports / `pg_dump` backups (optional)
- **VNet + delegated subnet + private DNS zone** (optional — or BYO)
- **User-assigned managed identity** with Key Vault read, for external-secrets

**Compute (AKS) is out of scope** — BYO or the upstream
[`Azure/aks`](https://registry.terraform.io/modules/Azure/aks/azurerm/latest)
module — then deploy with the Helm chart in [`../../helm/querywise`](../../helm/querywise),
keeping the cluster in a separate state from the database.

## Usage

```bash
az login
cp terraform.tfvars.example terraform.tfvars   # then edit
terraform init
terraform apply
```

Wire it up with the external-secrets operator on AKS (Workload Identity):

1. Federate the managed identity to the external-secrets KSA:
   ```bash
   az identity federated-credential create \
     --identity-name querywise-prod-ext-secrets \
     --resource-group "$(terraform output -raw resource_group_name)" \
     --issuer "$(az aks show -g <rg> -n <cluster> --query oidcIssuerProfile.issuerUrl -o tsv)" \
     --subject system:serviceaccount:external-secrets:external-secrets \
     --audience api://AzureADTokenExchange
   ```
2. Create an `ExternalSecret` (provider `azurekv`) that pulls the
   `querywise-app` secret with a `dataFrom` extract into a Kubernetes Secret
   named `querywise-secrets` (its keys already match the backend's env).
3. Install the chart:
   ```bash
   helm upgrade --install querywise ../../helm/querywise -n querywise \
     --set secrets.existingSecret=querywise-secrets
   ```

AKS must reach the Postgres private endpoint and the Redis host — peer its VNet
with the one created here (or set `create_vnet = false` and deploy into the
cluster's VNet).

## pgvector

`azure.extensions = VECTOR` is set here so the server permits the extension; the
app's Alembic migrations then run `CREATE EXTENSION IF NOT EXISTS vector` on
first `helm upgrade` (the migration hook).

## Notes

- The Terraform principal needs rights to assign roles on the Key Vault (it
  grants itself **Key Vault Secrets Officer** to write the secret).
- Key Vault has purge protection on — a destroyed vault is recoverable for 7
  days and the name stays reserved.
- Generated DB password / JWT secret live only in Key Vault + Terraform state —
  keep your state backend encrypted.
