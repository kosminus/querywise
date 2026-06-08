# -- General -----------------------------------------------------------------
variable "project_id" {
  description = "GCP project id."
  type        = string
}

variable "region" {
  description = "GCP region."
  type        = string
  default     = "us-central1"
}

variable "name_prefix" {
  description = "Prefix for resource names."
  type        = string
  default     = "querywise"
}

variable "labels" {
  description = "Extra labels applied to resources that support them."
  type        = map(string)
  default     = {}
}

# -- Network -----------------------------------------------------------------
# Cloud SQL private IP needs a VPC with a private-services-access peering range.
variable "create_network" {
  description = "Create a VPC + subnet + private-services-access peering. If false, supply network_id (must already have PSA configured)."
  type        = bool
  default     = true
}

variable "subnet_cidr" {
  description = "Primary subnet CIDR (when create_network = true)."
  type        = string
  default     = "10.43.0.0/20"
}

variable "network_id" {
  description = "Existing VPC self_link/id (when create_network = false)."
  type        = string
  default     = ""
}

# -- Cloud SQL (PostgreSQL + pgvector) ---------------------------------------
variable "db_name" {
  description = "Application database name."
  type        = string
  default     = "querywise"
}

variable "db_username" {
  description = "Application database user."
  type        = string
  default     = "querywise"
}

variable "db_password" {
  description = "DB password. Empty = generate one (stored in Secret Manager)."
  type        = string
  default     = ""
  sensitive   = true
}

variable "db_tier" {
  description = "Cloud SQL machine tier."
  type        = string
  default     = "db-custom-2-7680"
}

variable "db_disk_size" {
  description = "Cloud SQL disk size (GiB)."
  type        = number
  default     = 50
}

variable "db_ha" {
  description = "Regional (HA) availability instead of zonal."
  type        = bool
  default     = true
}

variable "db_deletion_protection" {
  description = "Block accidental destroy of the instance."
  type        = bool
  default     = true
}

# -- Memorystore (Redis) -----------------------------------------------------
variable "redis_memory_gb" {
  description = "Memorystore capacity (GiB)."
  type        = number
  default     = 1
}

variable "redis_ha" {
  description = "STANDARD_HA tier instead of BASIC."
  type        = bool
  default     = true
}

# -- GCS ---------------------------------------------------------------------
variable "create_bucket" {
  description = "Create a GCS bucket for exports/backups."
  type        = bool
  default     = true
}

variable "bucket_name" {
  description = "Bucket name. Empty = \"<name_prefix>-<project_id>\"."
  type        = string
  default     = ""
}

# -- Application secrets ------------------------------------------------------
variable "encryption_key" {
  description = "Fernet key for connection-string encryption (REQUIRED — see README)."
  type        = string
  sensitive   = true
}

variable "jwt_secret" {
  description = "HS256 JWT signing secret. Empty = generate one."
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
  description = "OpenAI API key."
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
