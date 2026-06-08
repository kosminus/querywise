# Read-only access to the app secret, for the external-secrets operator's IRSA
# role. Attach `secret_access_policy_arn` to the IAM role you bind to the
# external-secrets ServiceAccount (the role's trust policy references the EKS
# OIDC provider — created with the cluster, hence kept out of this data module).

data "aws_iam_policy_document" "secret_read" {
  statement {
    sid    = "ReadAppSecret"
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue",
      "secretsmanager:DescribeSecret",
    ]
    resources = [aws_secretsmanager_secret.app.arn]
  }
}

resource "aws_iam_policy" "secret_read" {
  name        = "${var.name_prefix}-secret-read"
  description = "Read the QueryWise app secret (for external-secrets IRSA)"
  policy      = data.aws_iam_policy_document.secret_read.json
}
