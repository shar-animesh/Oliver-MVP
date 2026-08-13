variable "subscription_id" {
    description = "Azure subscription that hosts Oliver. Set ARM_SUBSCRIPTION_ID instead when preferred."
    type        = string
    default     = null
    nullable    = true
}

variable "location" {
    description = "Azure region for all Oliver resources."
    type        = string
    default     = "westeurope"
}

variable "environment" {
    description = "Deployment environment name."
    type        = string
    default     = "dev"

    validation {
        condition     = contains(["dev", "test", "prod"], var.environment)
        error_message = "environment must be dev, test, or prod."
    }
}

variable "resource_prefix" {
    description = "Short lowercase prefix used in Azure resource names."
    type        = string
    default     = "oliver"

    validation {
        condition     = can(regex("^[a-z][a-z0-9-]{1,15}$", var.resource_prefix))
        error_message = "resource_prefix must start with a letter and contain 2-16 lowercase letters, numbers, or hyphens."
    }
}

variable "mailbox_address" {
    description = "Microsoft 365 shared mailbox monitored and used for replies."
    type        = string
}

variable "model_api_key" {
    description = "Azure OpenAI API key stored as an Azure Key Vault secret. Supply it through TF_VAR_model_api_key."
    type        = string
    sensitive   = true
}

variable "model_base_url" {
    description = "Azure OpenAI v1 base URL, for example https://RESOURCE.openai.azure.com/openai/v1/."
    type        = string

    validation {
        condition     = can(regex("^https://[A-Za-z0-9.-]+\\.openai\\.azure\\.com/openai/v1/$", var.model_base_url))
        error_message = "model_base_url must be an Azure OpenAI endpoint such as https://RESOURCE.openai.azure.com/openai/v1/."
    }
}

variable "model_name" {
    description = "Azure OpenAI model deployment name used by Oliver and Azure web search."
    type        = string
}

variable "sql_administrator_login" {
    description = "Azure SQL server administrator used by Oliver migrations."
    type        = string
    default     = "oliverdbadmin"
}

variable "sql_admin_reader_login" {
    description = "Contained read-only database user used by the admin backend."
    type        = string
    default     = "oliver_admin_reader"

    validation {
        condition     = can(regex("^[A-Za-z][A-Za-z0-9_]{2,63}$", var.sql_admin_reader_login))
        error_message = "sql_admin_reader_login must contain 3-64 letters, numbers, or underscores and start with a letter."
    }
}

variable "sql_database_name" {
    description = "Azure SQL database owned by Oliver."
    type        = string
    default     = "oliver"
}

variable "sql_database_sku" {
    description = "Azure SQL compute SKU. GP_S_Gen5_1 supports serverless auto-pause."
    type        = string
    default     = "GP_S_Gen5_1"
}

variable "sql_database_max_size_gb" {
    description = "Maximum database size in GiB."
    type        = number
    default     = 32
}

variable "sql_database_auto_pause_minutes" {
    description = "Idle minutes before the serverless database pauses."
    type        = number
    default     = 60
}

variable "sql_database_min_capacity" {
    description = "Minimum serverless vCore capacity."
    type        = number
    default     = 0.5
}

variable "reasoning_effort" {
    description = "Reasoning effort sent to the configured model provider."
    type        = string
    default     = "high"
}

variable "oliver_image_tag" {
    description = "Oliver image tag already pushed to the Terraform-managed registry."
    type        = string
    default     = "latest"
}

variable "admin_backend_image_tag" {
    description = "Admin backend image tag already pushed to the Terraform-managed registry."
    type        = string
    default     = "latest"
}

variable "admin_frontend_image_tag" {
    description = "Admin frontend image tag already pushed to the Terraform-managed registry."
    type        = string
    default     = "latest"
}

variable "container_min_replicas" {
    description = "Minimum number of Oliver API replicas."
    type        = number
    default     = 0
}

variable "container_max_replicas" {
    description = "Maximum number of Oliver API replicas."
    type        = number
    default     = 3
}

variable "admin_backend_min_replicas" {
    description = "Minimum number of admin backend replicas."
    type        = number
    default     = 0
}

variable "admin_backend_max_replicas" {
    description = "Maximum number of admin backend replicas."
    type        = number
    default     = 2
}

variable "admin_frontend_min_replicas" {
    description = "Minimum number of admin frontend replicas."
    type        = number
    default     = 0
}

variable "admin_frontend_max_replicas" {
    description = "Maximum number of admin frontend replicas."
    type        = number
    default     = 2
}

variable "admin_auth_secret_end_date" {
    description = "Expiration time for the Container Apps Entra application credential. Rotate before this date."
    type        = string
    default     = "2028-08-12T00:00:00Z"
}

variable "log_retention_days" {
    description = "Log Analytics retention period."
    type        = number
    default     = 30
}

variable "container_registry_sku" {
    description = "Azure Container Registry SKU."
    type        = string
    default     = "Basic"
}

variable "tags" {
    description = "Additional Azure resource tags."
    type        = map(string)
    default     = {}
}
