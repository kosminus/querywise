# Memorystore for Redis — result cache + the arq job queue. Reachable on the
# authorized VPC's private IP.

resource "google_redis_instance" "this" {
  name           = "${var.name_prefix}-redis"
  tier           = var.redis_ha ? "STANDARD_HA" : "BASIC"
  memory_size_gb = var.redis_memory_gb
  region         = var.region
  redis_version  = "REDIS_7_0"

  authorized_network = local.network_id

  labels = local.labels
}
