# -- General -----------------------------------------------------------------
variable "region" {
  description = "AWS region to deploy into."
  type        = string
}

variable "name_prefix" {
  description = "Prefix for all resource names (e.g. \"querywise-prod\")."
  type        = string
  default     = "querywise"
}

variable "tags" {
  description = "Extra tags applied to every resource."
  type        = map(string)
  default     = {}
}

# -- Network -----------------------------------------------------------------
# Either let the module create a VPC, or supply an existing one.
variable "create_vpc" {
  description = "Create a VPC + private subnets. If false, supply vpc_id and private_subnet_ids."
  type        = bool
  default     = true
}

variable "vpc_cidr" {
  description = "CIDR for the created VPC (when create_vpc = true)."
  type        = string
  default     = "10.42.0.0/16"
}

variable "availability_zones" {
  description = "AZs to spread data subnets across (>= 2 for Multi-AZ / ElastiCache)."
  type        = list(string)
  default     = []
}

variable "vpc_id" {
  description = "Existing VPC id (when create_vpc = false)."
  type        = string
  default     = ""
}

variable "private_subnet_ids" {
  description = "Existing private subnet ids for RDS/ElastiCache (when create_vpc = false)."
  type        = list(string)
  default     = []
}

variable "allowed_security_group_ids" {
  description = "Security groups (e.g. the EKS node/pod SG) allowed to reach Postgres/Redis."
  type        = list(string)
  default     = []
}

variable "allowed_cidr_blocks" {
  description = "CIDRs allowed to reach Postgres/Redis (use sparingly; prefer SG references)."
  type        = list(string)
  default     = []
}

# -- PostgreSQL (pgvector) ---------------------------------------------------
variable "db_name" {
  description = "Application database name."
  type        = string
  default     = "querywise"
}

variable "db_username" {
  description = "Master username for the app database."
  type        = string
  default     = "querywise"
}

variable "db_password" {
  description = "Master password. Leave empty to generate one (stored in Secrets Manager)."
  type        = string
  default     = ""
  sensitive   = true
}

variable "db_engine_version" {
  description = "PostgreSQL engine version (16.x supports the pgvector extension)."
  type        = string
  default     = "16.4"
}

variable "db_instance_class" {
  description = "RDS instance class."
  type        = string
  default     = "db.t4g.medium"
}

variable "db_allocated_storage" {
  description = "Initial storage (GiB)."
  type        = number
  default     = 50
}

variable "db_max_allocated_storage" {
  description = "Storage autoscaling ceiling (GiB). Set equal to allocated to disable."
  type        = number
  default     = 200
}

variable "db_multi_az" {
  description = "Run the database Multi-AZ for HA."
  type        = bool
  default     = true
}

variable "db_backup_retention_days" {
  description = "Automated backup retention (days)."
  type        = number
  default     = 7
}

variable "db_deletion_protection" {
  description = "Block accidental `terraform destroy` of the database."
  type        = bool
  default     = true
}

# -- ElastiCache (Redis) -----------------------------------------------------
variable "redis_node_type" {
  description = "ElastiCache node type."
  type        = string
  default     = "cache.t4g.small"
}

variable "redis_engine_version" {
  description = "Redis engine version."
  type        = string
  default     = "7.1"
}

variable "redis_replicas" {
  description = "Number of replica nodes (0 = single primary, no HA)."
  type        = number
  default     = 1
}

# -- S3 (exports / backups) --------------------------------------------------
variable "create_s3_bucket" {
  description = "Create an S3 bucket for exports/backups."
  type        = bool
  default     = true
}

variable "s3_bucket_name" {
  description = "Bucket name. Empty = \"<name_prefix>-<account_id>\"."
  type        = string
  default     = ""
}

# -- Application secrets (assembled into the Secrets Manager secret) ----------
variable "encryption_key" {
  description = "Fernet key for connection-string encryption (REQUIRED — generate with the python one-liner in the README)."
  type        = string
  sensitive   = true
}

variable "jwt_secret" {
  description = "HS256 signing secret for session/magic-link JWTs. Empty = generate one."
  type        = string
  default     = ""
  sensitive   = true
}

variable "default_admin_password" {
  description = "Optional bootstrap admin password."
  type        = string
  default     = ""
  sensitive   = true
}

variable "openai_api_key" {
  description = "OpenAI API key (completions + embeddings)."
  type        = string
  default     = ""
  sensitive   = true
}

variable "anthropic_api_key" {
  description = "Anthropic API key (optional)."
  type        = string
  default     = ""
  sensitive   = true
}

variable "azure_openai_api_key" {
  description = "Azure OpenAI key (optional)."
  type        = string
  default     = ""
  sensitive   = true
}
