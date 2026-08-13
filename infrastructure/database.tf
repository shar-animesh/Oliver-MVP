resource "random_password" "sql_administrator" {
    length           = 32
    special          = true
    override_special = "!#$%&*+-.:=?@_"
}

resource "random_password" "sql_admin_reader" {
    length           = 32
    special          = true
    override_special = "!#$%&*+-.:=?@_"
}

resource "azurerm_mssql_server" "oliver" {
    name                          = "sql-${local.unique_name}"
    resource_group_name           = azurerm_resource_group.oliver.name
    location                      = azurerm_resource_group.oliver.location
    version                       = "12.0"
    administrator_login           = var.sql_administrator_login
    administrator_login_password  = random_password.sql_administrator.result
    minimum_tls_version           = "1.2"
    public_network_access_enabled = true
    tags                          = local.common_tags
}

resource "azurerm_mssql_firewall_rule" "azure_services" {
    name             = "AllowAzureServices"
    server_id        = azurerm_mssql_server.oliver.id
    start_ip_address = "0.0.0.0"
    end_ip_address   = "0.0.0.0"
}

resource "azurerm_mssql_database" "oliver" {
    name                        = var.sql_database_name
    server_id                   = azurerm_mssql_server.oliver.id
    sku_name                    = var.sql_database_sku
    max_size_gb                 = var.sql_database_max_size_gb
    auto_pause_delay_in_minutes = var.sql_database_auto_pause_minutes
    min_capacity                = var.sql_database_min_capacity
    zone_redundant              = false
    tags                        = local.common_tags
}

locals {
    oliver_database_url = format(
        "mssql+pyodbc://%s:%s@%s:1433/%s?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no",
        var.sql_administrator_login,
        urlencode(random_password.sql_administrator.result),
        azurerm_mssql_server.oliver.fully_qualified_domain_name,
        azurerm_mssql_database.oliver.name,
    )

    admin_database_url = format(
        "mssql+pyodbc://%s:%s@%s:1433/%s?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no",
        var.sql_admin_reader_login,
        urlencode(random_password.sql_admin_reader.result),
        azurerm_mssql_server.oliver.fully_qualified_domain_name,
        azurerm_mssql_database.oliver.name,
    )
}
