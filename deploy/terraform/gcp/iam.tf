# Service account for the external-secrets operator. Grant it accessor on the
# app secret, then bind it to the in-cluster external-secrets KSA with Workload
# Identity (the iam.workloadIdentityUser binding references the GKE workload
# identity pool, created with the cluster — hence kept out of this data module):
#
#   gcloud iam service-accounts add-iam-policy-binding <sa_email> \
#     --role roles/iam.workloadIdentityUser \
#     --member "serviceAccount:<project>.svc.id.goog[external-secrets/external-secrets]"

resource "google_service_account" "external_secrets" {
  account_id   = "${var.name_prefix}-ext-secrets"
  display_name = "QueryWise external-secrets accessor"
}

resource "google_secret_manager_secret_iam_member" "accessor" {
  secret_id = google_secret_manager_secret.app.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.external_secrets.email}"
}
