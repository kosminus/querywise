# Key Vault holds the assembled app secret (DSNs + keys) as a JSON blob. The
# external-secrets operator on AKS reads it (via the managed identity in
# identity.tf, federated to its KSA) and syncs it into the Kubernetes Secret the
# Helm chart references. Keys map 1:1 to the backend's env vars.

locals {
  key_vault_name = substr("${var.name_prefix}-kv-${random_string.suffix.result}", 0, 24)
}

resource "azurerm_key_vault" "this" {
  name                       = local.key_vault_name
  location                   = var.location
  resource_group_name        = local.rg_name
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  enable_rbac_authorization  = true
  purge_protection_enabled   = true
  soft_delete_retention_days = 7
  tags                       = local.tags
}

# Let the principal running Terraform write secrets (RBAC mode).
resource "azurerm_role_assignment" "tf_secrets_officer" {
  scope                = azurerm_key_vault.this.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}

resource "azurerm_key_vault_secret" "app" {
  name         = "querywise-app"
  value        = jsonencode(local.secret_payload)
  key_vault_id = azurerm_key_vault.this.id

  depends_on = [azurerm_role_assignment.tf_secrets_officer]
}
