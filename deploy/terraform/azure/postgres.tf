# Azure Database for PostgreSQL flexible server, v16. pgvector must be
# allow-listed via the azure.extensions server parameter; the extension itself
# is then created by the app's Alembic migrations (`CREATE EXTENSION ... vector`).

resource "azurerm_postgresql_flexible_server" "this" {
  name                = "${var.name_prefix}-pg"
  resource_group_name = local.rg_name
  location            = var.location
  version             = "16"

  administrator_login    = var.db_username
  administrator_password = local.db_password

  sku_name   = var.db_sku
  storage_mb = var.db_storage_mb

  # VNet-integrated (private) access.
  delegated_subnet_id = local.db_subnet_id
  private_dns_zone_id = local.private_dns_zone_id

  backup_retention_days = var.db_backup_retention_days

  dynamic "high_availability" {
    for_each = var.db_ha ? [1] : []
    content {
      mode = "ZoneRedundant"
    }
  }

  tags = local.tags

  # The private DNS zone link must exist before the server is created.
  depends_on = [azurerm_private_dns_zone_virtual_network_link.pg]
}

resource "azurerm_postgresql_flexible_server_database" "app" {
  name      = var.db_name
  server_id = azurerm_postgresql_flexible_server.this.id
  collation = "en_US.utf8"
  charset   = "UTF8"
}

# Allow-list pgvector so the app can `CREATE EXTENSION vector`.
resource "azurerm_postgresql_flexible_server_configuration" "extensions" {
  name      = "azure.extensions"
  server_id = azurerm_postgresql_flexible_server.this.id
  value     = "VECTOR"
}
