# Cloud SQL for PostgreSQL 16. pgvector is available as an extension and is
# created by the app's Alembic migrations (`CREATE EXTENSION IF NOT EXISTS
# vector`) — no instance flag required.

resource "google_sql_database_instance" "this" {
  name                = "${var.name_prefix}-pg"
  database_version    = "POSTGRES_16"
  region              = var.region
  deletion_protection = var.db_deletion_protection

  # Private IP depends on the PSA peering being established first.
  depends_on = [google_service_networking_connection.psa]

  settings {
    tier              = var.db_tier
    availability_type = var.db_ha ? "REGIONAL" : "ZONAL"
    disk_size         = var.db_disk_size
    disk_autoresize   = true
    disk_type         = "PD_SSD"

    ip_configuration {
      ipv4_enabled    = false
      private_network = local.network_id
      ssl_mode        = "ENCRYPTED_ONLY"
    }

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
    }

    user_labels = local.labels
  }
}

resource "google_sql_database" "app" {
  name     = var.db_name
  instance = google_sql_database_instance.this.name
}

resource "google_sql_user" "app" {
  name     = var.db_username
  instance = google_sql_database_instance.this.name
  password = local.db_password
}
