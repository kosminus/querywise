# Optional bucket for exports / pg_dump backups. Uniform access + versioned.

resource "google_storage_bucket" "data" {
  count                       = var.create_bucket ? 1 : 0
  name                        = local.bucket_name
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = false
  labels                      = local.labels

  versioning {
    enabled = true
  }
}
