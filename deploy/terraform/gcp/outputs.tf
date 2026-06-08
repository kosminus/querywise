output "network_id" {
  description = "VPC the data plane runs in."
  value       = local.network_id
}

output "db_private_ip" {
  description = "Cloud SQL private IP."
  value       = google_sql_database_instance.this.private_ip_address
}

output "db_instance_connection_name" {
  description = "Cloud SQL connection name (for the auth proxy, if used)."
  value       = google_sql_database_instance.this.connection_name
}

output "redis_host" {
  description = "Memorystore host."
  value       = google_redis_instance.this.host
}

output "app_secret_id" {
  description = "Secret Manager secret id holding the assembled app secret. Point external-secrets at this."
  value       = google_secret_manager_secret.app.secret_id
}

output "external_secrets_sa_email" {
  description = "Service account email to bind to the external-secrets KSA via Workload Identity."
  value       = google_service_account.external_secrets.email
}

output "bucket_name" {
  description = "Exports/backups bucket (empty if disabled)."
  value       = var.create_bucket ? google_storage_bucket.data[0].name : ""
}

output "database_url" {
  description = "asyncpg DSN (also stored in the app secret)."
  value       = local.database_url
  sensitive   = true
}

output "redis_url" {
  description = "Redis DSN (also stored in the app secret)."
  value       = local.redis_url
  sensitive   = true
}
