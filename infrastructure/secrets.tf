resource "azurerm_user_assigned_identity" "workloads" {
    name                = "id-${local.name_prefix}-workloads"
    resource_group_name = azurerm_resource_group.oliver.name
    location            = azurerm_resource_group.oliver.location
    tags                = local.common_tags
}

resource "azurerm_role_assignment" "workloads_acr_pull" {
    scope                = azurerm_container_registry.oliver.id
    role_definition_name = "AcrPull"
    principal_id         = azurerm_user_assigned_identity.workloads.principal_id
}

resource "azurerm_key_vault_secret" "model_api_key" {
    name         = "model-api-key"
    value        = var.model_api_key
    key_vault_id = azurerm_key_vault.oliver.id
}

resource "azurerm_key_vault_secret" "internal_api_key" {
    name         = "internal-api-key"
    value        = random_password.internal_api_key.result
    key_vault_id = azurerm_key_vault.oliver.id
}

resource "azurerm_key_vault_secret" "oliver_database_url" {
    name         = "oliver-database-url"
    value        = local.oliver_database_url
    key_vault_id = azurerm_key_vault.oliver.id
}

resource "azurerm_key_vault_secret" "sql_administrator_password" {
    name         = "sql-administrator-password"
    value        = random_password.sql_administrator.result
    key_vault_id = azurerm_key_vault.oliver.id
}

resource "azurerm_key_vault_secret" "admin_database_url" {
    name         = "admin-database-url"
    value        = local.admin_database_url
    key_vault_id = azurerm_key_vault.oliver.id
}

resource "azurerm_key_vault_secret" "sql_admin_reader_password" {
    name         = "sql-admin-reader-password"
    value        = random_password.sql_admin_reader.result
    key_vault_id = azurerm_key_vault.oliver.id
}
