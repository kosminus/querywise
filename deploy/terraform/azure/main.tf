data "azurerm_client_config" "current" {}

locals {
  tags = merge({
    "app"       = "querywise"
    "managedBy" = "terraform"
  }, var.tags)

  rg_name = var.create_resource_group ? azurerm_resource_group.this[0].name : var.resource_group_name

  db_subnet_id        = var.create_vnet ? azurerm_subnet.db[0].id : var.db_subnet_id
  private_dns_zone_id = var.create_vnet ? azurerm_private_dns_zone.pg[0].id : var.private_dns_zone_id

  db_password = var.db_password != "" ? var.db_password : random_password.db[0].result
  jwt_secret  = var.jwt_secret != "" ? var.jwt_secret : random_password.jwt[0].result

  # Postgres flexible server FQDN; Azure Cache for Redis is TLS-only on 6380 and
  # authenticates with the access key (rediss:// DSN).
  database_url = "postgresql+asyncpg://${var.db_username}:${local.db_password}@${azurerm_postgresql_flexible_server.this.fqdn}:5432/${var.db_name}"
  redis_url    = "rediss://:${azurerm_redis_cache.this.primary_access_key}@${azurerm_redis_cache.this.hostname}:6380/0"

  # Storage account name: 3-24 lowercase alphanumeric, globally unique.
  storage_account_name = substr("${replace(lower(var.name_prefix), "/[^a-z0-9]/", "")}${random_string.suffix.result}", 0, 24)

  secret_payload = { for k, v in {
    DATABASE_URL           = local.database_url
    REDIS_URL              = local.redis_url
    ENCRYPTION_KEY         = var.encryption_key
    JWT_SECRET             = local.jwt_secret
    DEFAULT_ADMIN_PASSWORD = var.default_admin_password
    OPENAI_API_KEY         = var.openai_api_key
    ANTHROPIC_API_KEY      = var.anthropic_api_key
    AZURE_OPENAI_API_KEY   = var.azure_openai_api_key
  } : k => v if v != null && v != "" }
}

resource "random_string" "suffix" {
  length  = 6
  upper   = false
  special = false
}

resource "random_password" "db" {
  count            = var.db_password == "" ? 1 : 0
  length           = 32
  special          = true
  override_special = "-_"
}

resource "random_password" "jwt" {
  count   = var.jwt_secret == "" ? 1 : 0
  length  = 48
  special = false
}

resource "azurerm_resource_group" "this" {
  count    = var.create_resource_group ? 1 : 0
  name     = var.resource_group_name != "" ? var.resource_group_name : "${var.name_prefix}-rg"
  location = var.location
  tags     = local.tags
}
