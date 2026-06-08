# VNet + a subnet delegated to the Postgres flexible server, plus the private
# DNS zone it needs for VNet integration. Set create_vnet = false to supply your
# own delegated subnet + DNS zone.

resource "azurerm_virtual_network" "this" {
  count               = var.create_vnet ? 1 : 0
  name                = "${var.name_prefix}-vnet"
  location            = var.location
  resource_group_name = local.rg_name
  address_space       = [var.vnet_cidr]
  tags                = local.tags
}

resource "azurerm_subnet" "db" {
  count                = var.create_vnet ? 1 : 0
  name                 = "${var.name_prefix}-pg"
  resource_group_name  = local.rg_name
  virtual_network_name = azurerm_virtual_network.this[0].name
  address_prefixes     = [var.db_subnet_cidr]

  delegation {
    name = "fs"
    service_delegation {
      name    = "Microsoft.DBforPostgreSQL/flexibleServers"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}

resource "azurerm_private_dns_zone" "pg" {
  count               = var.create_vnet ? 1 : 0
  name                = "${var.name_prefix}.private.postgres.database.azure.com"
  resource_group_name = local.rg_name
  tags                = local.tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "pg" {
  count                 = var.create_vnet ? 1 : 0
  name                  = "${var.name_prefix}-pg-link"
  resource_group_name   = local.rg_name
  private_dns_zone_name = azurerm_private_dns_zone.pg[0].name
  virtual_network_id    = azurerm_virtual_network.this[0].id
}
