# Azure Cache for Redis — result cache + the arq job queue. TLS-only (6380);
# the backend connects with rediss:// using the primary access key.

resource "azurerm_redis_cache" "this" {
  name                = "${var.name_prefix}-redis"
  location            = var.location
  resource_group_name = local.rg_name

  capacity = var.redis_capacity
  family   = var.redis_sku == "Premium" ? "P" : "C"
  sku_name = var.redis_sku

  non_ssl_port_enabled = false
  minimum_tls_version  = "1.2"

  tags = local.tags
}
