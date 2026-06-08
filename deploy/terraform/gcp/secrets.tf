# Secret Manager holds the assembled app secret (DSNs + keys) as a JSON blob.
# The external-secrets operator on GKE reads it (via the service account below,
# bound with Workload Identity) and syncs it into the Kubernetes Secret the Helm
# chart references. Keys map 1:1 to the backend's env vars.

resource "google_secret_manager_secret" "app" {
  secret_id = "${var.name_prefix}-app"
  labels    = local.labels

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "app" {
  secret      = google_secret_manager_secret.app.id
  secret_data = jsonencode(local.secret_payload)
}
