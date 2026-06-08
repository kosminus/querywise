# -- General -----------------------------------------------------------------
variable "subscription_id" {
  description = "Azure subscription id. Empty = use the provider's ambient context (ARM_SUBSCRIPTION_ID)."
  type        = string
  default     = ""
}

variable "location" {
  description = "Azure region."
  type        = string
  default     = "eastus"
}

variable "name_prefix" {
  description = "Prefix for resource names."
  type        = string
  default     = "querywise"
}

variable "tags" {
  description = "Extra tags applied to every resource."
  type        = map(string)
  default     = {}
}

# -- Resource group ----------------------------------------------------------
variable "create_resource_group" {
  description = "Create the resource group. If false, it must already exist."
  type        = bool
  default     = true
}

variable "resource_group_name" {
  description = "Resource group name. Empty = \"<name_prefix>-rg\"."
  type        = string
  default     = ""
}

# -- Network -----------------------------------------------------------------
# The Postgres flexible server uses VNet integration (delegated subnet + private
# DNS zone). Set create_vnet = false to supply your own delegated subnet.
variable "create_vnet" {
  description = "Create a VNet + delegated subnet + private DNS zone for Postgres."
  type        = bool
  default     = true
}

variable "vnet_cidr" {
  description = "VNet CIDR (when create_vnet = true)."
  type        = string
  default     = "10.44.0.0/16"
}

variable "db_subnet_cidr" {
  description = "Delegated subnet CIDR for the flexible server."
  type        = string
  default     = "10.44.1.0/24"
}

variable "db_subnet_id" {
  description = "Existing delegated subnet id (when create_vnet = false)."
  type        = string
  default     = ""
}

variable "private_dns_zone_id" {
  description = "Existing private DNS zone id for Postgres (when create_vnet = false)."
  type        = string
  default     = ""
}

# -- PostgreSQL flexible server (pgvector) -----------------------------------
variable "db_name" {
  description = "Application database name."
  type        = string
  default     = "querywise"
}

variable "db_username" {
  description = "Administrator login."
  type        = string
  default     = "querywise"
}

variable "db_password" {
  description = "Admin password. Empty = generate one (stored in Key Vault)."
  type        = string
  default     = ""
  sensitive   = true
}

variable "db_sku" {
  description = "Flexible server SKU."
  type        = string
  default     = "GP_Standard_D2ds_v5"
}

variable "db_storage_mb" {
  description = "Storage (MB). Minimum 32768."
  type        = number
  default     = 65536
}

variable "db_ha" {
  description = "Zone-redundant high availability."
  type        = bool
  default     = true
}

variable "db_backup_retention_days" {
  description = "Backup retention (days)."
  type        = number
  default     = 7
}

# -- Redis -------------------------------------------------------------------
variable "redis_capacity" {
  description = "Redis cache capacity (Standard family C: 0=250MB,1=1GB,...)."
  type        = number
  default     = 1
}

variable "redis_sku" {
  description = "Redis SKU (Basic | Standard | Premium)."
  type        = string
  default     = "Standard"
}

# -- Storage -----------------------------------------------------------------
variable "create_storage" {
  description = "Create a storage account + container for exports/backups."
  type        = bool
  default     = true
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
