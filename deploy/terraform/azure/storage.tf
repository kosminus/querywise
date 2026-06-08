# Optional storage account + container for exports / pg_dump backups.

resource "azurerm_storage_account" "this" {
  count                    = var.create_storage ? 1 : 0
  name                     = local.storage_account_name
  resource_group_name      = local.rg_name
  location                 = var.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  account_kind             = "StorageV2"
  min_tls_version          = "TLS1_2"

  tags = local.tags
}

resource "azurerm_storage_container" "data" {
  count                 = var.create_storage ? 1 : 0
  name                  = "exports"
  storage_account_name  = azurerm_storage_account.this[0].name
  container_access_type = "private"
}
