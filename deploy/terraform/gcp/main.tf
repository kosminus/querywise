locals {
  labels = merge({
    "app" = "querywise"
  }, var.labels)

  network_id = var.create_network ? google_compute_network.this[0].id : var.network_id

  db_password = var.db_password != "" ? var.db_password : random_password.db[0].result
  jwt_secret  = var.jwt_secret != "" ? var.jwt_secret : random_password.jwt[0].result

  # Cloud SQL private IP + Memorystore host. Generated password uses a URL-safe
  # alphabet so it drops into the DSN without escaping.
  database_url = "postgresql+asyncpg://${var.db_username}:${local.db_password}@${google_sql_database_instance.this.private_ip_address}:5432/${var.db_name}"
  redis_url    = "redis://${google_redis_instance.this.host}:${google_redis_instance.this.port}/0"

  bucket_name = var.bucket_name != "" ? var.bucket_name : "${var.name_prefix}-${var.project_id}"

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
