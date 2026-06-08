# Secrets Manager holds the assembled app secret (DSNs + keys). The
# external-secrets operator in-cluster syncs this into the Kubernetes Secret the
# Helm chart references (secrets.existingSecret). Keys map 1:1 to the backend's
# env vars, so a SecretStore + ExternalSecret with a "dataFrom" extract is enough.

resource "aws_secretsmanager_secret" "app" {
  name        = "${var.name_prefix}/app"
  description = "QueryWise application secrets (DSNs + keys)"
}

resource "aws_secretsmanager_secret_version" "app" {
  secret_id     = aws_secretsmanager_secret.app.id
  secret_string = jsonencode(local.secret_payload)
}
