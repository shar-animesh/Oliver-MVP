data "azurerm_client_config" "current" {}

resource "random_string" "suffix" {
    length  = 6
    upper   = false
    special = false
}

resource "random_password" "internal_api_key" {
    length  = 48
    special = false
}

locals {
    name_prefix = "${var.resource_prefix}-${var.environment}"
    unique_name = "${replace(var.resource_prefix, "-", "")}${var.environment}${random_string.suffix.result}"

    common_tags = merge(
        {
            application = "oliver"
            environment = var.environment
            managed-by  = "terraform"
        },
        var.tags,
    )
}

resource "azurerm_resource_group" "oliver" {
    name     = "rg-${local.name_prefix}"
    location = var.location
    tags     = local.common_tags
}

resource "azurerm_log_analytics_workspace" "oliver" {
    name                = "log-${local.name_prefix}"
    location            = azurerm_resource_group.oliver.location
    resource_group_name = azurerm_resource_group.oliver.name
    sku                 = "PerGB2018"
    retention_in_days   = var.log_retention_days
    tags                = local.common_tags
}

resource "azurerm_application_insights" "oliver" {
    name                = "appi-${local.name_prefix}"
    location            = azurerm_resource_group.oliver.location
    resource_group_name = azurerm_resource_group.oliver.name
    workspace_id        = azurerm_log_analytics_workspace.oliver.id
    application_type    = "web"
    tags                = local.common_tags
}

resource "azurerm_container_registry" "oliver" {
    name                = "acr${local.unique_name}"
    resource_group_name = azurerm_resource_group.oliver.name
    location            = azurerm_resource_group.oliver.location
    sku                 = var.container_registry_sku
    admin_enabled       = false
    tags                = local.common_tags
}

resource "azurerm_container_app_environment" "oliver" {
    name                       = "cae-${local.name_prefix}"
    location                   = azurerm_resource_group.oliver.location
    resource_group_name        = azurerm_resource_group.oliver.name
    log_analytics_workspace_id = azurerm_log_analytics_workspace.oliver.id
    tags                       = local.common_tags
}

resource "azurerm_key_vault" "oliver" {
    name                       = "kv-${local.unique_name}"
    location                   = azurerm_resource_group.oliver.location
    resource_group_name        = azurerm_resource_group.oliver.name
    tenant_id                  = data.azurerm_client_config.current.tenant_id
    sku_name                   = "standard"
    soft_delete_retention_days = 7
    purge_protection_enabled   = var.environment == "prod"
    tags                       = local.common_tags

    access_policy {
        tenant_id = data.azurerm_client_config.current.tenant_id
        object_id = data.azurerm_client_config.current.object_id

        secret_permissions = [
            "Delete",
            "Get",
            "List",
            "Purge",
            "Recover",
            "Set",
        ]
    }

    access_policy {
        tenant_id = data.azurerm_client_config.current.tenant_id
        object_id = azurerm_user_assigned_identity.workloads.principal_id

        secret_permissions = [
            "Get",
            "List",
        ]
    }
}
