# -- Network -----------------------------------------------------------------
output "vpc_id" {
  description = "VPC the data plane runs in."
  value       = local.vpc_id
}

output "private_subnet_ids" {
  description = "Private subnets used by RDS/ElastiCache."
  value       = local.private_subnet_ids
}

output "rds_security_group_id" {
  description = "Attach app compute here is not needed; reference for rules/debugging."
  value       = aws_security_group.rds.id
}

output "redis_security_group_id" {
  value       = aws_security_group.redis.id
  description = "Redis security group id."
}

# -- Endpoints ---------------------------------------------------------------
output "db_endpoint" {
  description = "RDS Postgres endpoint (host)."
  value       = aws_db_instance.this.address
}

output "redis_endpoint" {
  description = "ElastiCache primary endpoint (host)."
  value       = aws_elasticache_replication_group.this.primary_endpoint_address
}

# -- Secrets -----------------------------------------------------------------
output "app_secret_arn" {
  description = "Secrets Manager ARN holding the assembled app secret (DSNs + keys). Point external-secrets at this."
  value       = aws_secretsmanager_secret.app.arn
}

output "app_secret_name" {
  description = "Secrets Manager name of the app secret."
  value       = aws_secretsmanager_secret.app.name
}

output "secret_access_policy_arn" {
  description = "IAM policy granting read of the app secret — attach to the external-secrets IRSA role."
  value       = aws_iam_policy.secret_read.arn
}

# -- Storage -----------------------------------------------------------------
output "s3_bucket_name" {
  description = "Exports/backups bucket (empty if disabled)."
  value       = var.create_s3_bucket ? aws_s3_bucket.data[0].bucket : ""
}

# -- Convenience: DSNs (sensitive) -------------------------------------------
output "database_url" {
  description = "asyncpg DSN for the backend (also stored in the app secret)."
  value       = local.database_url
  sensitive   = true
}

output "redis_url" {
  description = "Redis DSN for cache + arq (also stored in the app secret)."
  value       = local.redis_url
  sensitive   = true
}
