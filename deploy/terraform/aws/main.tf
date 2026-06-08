data "aws_caller_identity" "current" {}

data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  tags = merge({
    "app.kubernetes.io/name" = "querywise"
    "ManagedBy"              = "terraform"
  }, var.tags)

  # Default to the first two available AZs when none are supplied.
  azs = length(var.availability_zones) > 0 ? var.availability_zones : slice(data.aws_availability_zones.available.names, 0, 2)

  # Resolve network: created vs. supplied.
  vpc_id             = var.create_vpc ? aws_vpc.this[0].id : var.vpc_id
  private_subnet_ids = var.create_vpc ? aws_subnet.private[*].id : var.private_subnet_ids

  # Master password: supplied or generated.
  db_password = var.db_password != "" ? var.db_password : random_password.db[0].result
  jwt_secret  = var.jwt_secret != "" ? var.jwt_secret : random_password.jwt[0].result

  # DSNs the app/Helm chart consume. The generated DB password uses a URL-safe
  # alphabet (see random_password.db) so no escaping is needed here.
  database_url = "postgresql+asyncpg://${var.db_username}:${local.db_password}@${aws_db_instance.this.address}:5432/${var.db_name}"
  redis_url    = "redis://${aws_elasticache_replication_group.this.primary_endpoint_address}:6379/0"

  bucket_name = var.s3_bucket_name != "" ? var.s3_bucket_name : "${var.name_prefix}-${data.aws_caller_identity.current.account_id}"

  # Keys mirror what the backend reads from env / the Helm Secret. Empty values
  # are dropped so optional provider keys don't create blank entries.
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
  count = var.db_password == "" ? 1 : 0
  # URL-safe alphabet so the password drops cleanly into the DSN.
  length           = 32
  special          = true
  override_special = "-_"
}

resource "random_password" "jwt" {
  count   = var.jwt_secret == "" ? 1 : 0
  length  = 48
  special = false
}
