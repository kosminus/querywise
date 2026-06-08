output "resource_group_name" {
  description = "Resource group the data plane runs in."
  value       = local.rg_name
}

output "db_fqdn" {
  description = "Postgres flexible server FQDN."
  value       = azurerm_postgresql_flexible_server.this.fqdn
}

output "redis_hostname" {
  description = "Azure Cache for Redis hostname."
  value       = azurerm_redis_cache.this.hostname
}

output "key_vault_name" {
  description = "Key Vault holding the app secret. Point external-secrets at this."
  value       = azurerm_key_vault.this.name
}

output "app_secret_name" {
  description = "Key Vault secret name with the assembled app config (JSON)."
  value       = azurerm_key_vault_secret.app.name
}

output "external_secrets_identity_client_id" {
  description = "Client id of the managed identity to federate to the external-secrets KSA."
  value       = azurerm_user_assigned_identity.external_secrets.client_id
}

output "storage_account_name" {
  description = "Exports/backups storage account (empty if disabled)."
  value       = var.create_storage ? azurerm_storage_account.this[0].name : ""
}

output "database_url" {
  description = "asyncpg DSN (also stored in Key Vault)."
  value       = local.database_url
  sensitive   = true
}

output "redis_url" {
  description = "Redis DSN (also stored in Key Vault)."
  value       = local.redis_url
  sensitive   = true
}
