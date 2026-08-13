locals {
    oliver_name         = "ca-${local.name_prefix}-oliver"
    admin_backend_name  = "ca-${local.name_prefix}-admin-api"
    admin_frontend_name = "ca-${local.name_prefix}-admin-web"

    admin_frontend_origin = "https://${local.admin_frontend_name}.${azurerm_container_app_environment.oliver.default_domain}"
}

resource "azurerm_container_app" "oliver" {
    name                         = local.oliver_name
    resource_group_name          = azurerm_resource_group.oliver.name
    container_app_environment_id = azurerm_container_app_environment.oliver.id
    revision_mode                = "Single"
    tags                         = local.common_tags

    identity {
        type         = "UserAssigned"
        identity_ids = [azurerm_user_assigned_identity.workloads.id]
    }

    registry {
        server   = azurerm_container_registry.oliver.login_server
        identity = azurerm_user_assigned_identity.workloads.id
    }

    secret {
        name                = "model-api-key"
        key_vault_secret_id = azurerm_key_vault_secret.model_api_key.versionless_id
        identity            = azurerm_user_assigned_identity.workloads.id
    }

    secret {
        name                = "internal-api-key"
        key_vault_secret_id = azurerm_key_vault_secret.internal_api_key.versionless_id
        identity            = azurerm_user_assigned_identity.workloads.id
    }

    secret {
        name                = "database-url"
        key_vault_secret_id = azurerm_key_vault_secret.oliver_database_url.versionless_id
        identity            = azurerm_user_assigned_identity.workloads.id
    }

    template {
        min_replicas = var.container_min_replicas
        max_replicas = var.container_max_replicas

        container {
            name   = "oliver"
            image  = "${azurerm_container_registry.oliver.login_server}/oliver:${var.oliver_image_tag}"
            cpu    = 0.5
            memory = "1Gi"

            env {
                name  = "ENV"
                value = var.environment == "prod" ? "production" : var.environment
            }

            env {
                name        = "OPENAI_API_KEY"
                secret_name = "model-api-key"
            }

            env {
                name  = "OPENAI_BASE_URL"
                value = var.model_base_url
            }

            env {
                name  = "OPENAI_MODEL"
                value = var.model_name
            }

            env {
                name  = "OPENAI_REASONING_EFFORT"
                value = var.reasoning_effort
            }

            env {
                name        = "INTERNAL_API_KEY"
                secret_name = "internal-api-key"
            }

            env {
                name        = "DATABASE_URL"
                secret_name = "database-url"
            }

            env {
                name  = "APPLICATIONINSIGHTS_CONNECTION_STRING"
                value = azurerm_application_insights.oliver.connection_string
            }
        }
    }

    ingress {
        external_enabled           = true
        allow_insecure_connections = false
        target_port                = 8000
        transport                  = "auto"

        traffic_weight {
            latest_revision = true
            percentage      = 100
        }
    }

    depends_on = [
        azurerm_key_vault.oliver,
        azurerm_role_assignment.workloads_acr_pull,
        terraform_data.oliver_image,
        terraform_data.run_database_migrations,
    ]
}

resource "azurerm_container_app" "admin_backend" {
    name                         = local.admin_backend_name
    resource_group_name          = azurerm_resource_group.oliver.name
    container_app_environment_id = azurerm_container_app_environment.oliver.id
    revision_mode                = "Single"
    tags                         = local.common_tags

    identity {
        type         = "UserAssigned"
        identity_ids = [azurerm_user_assigned_identity.workloads.id]
    }

    registry {
        server   = azurerm_container_registry.oliver.login_server
        identity = azurerm_user_assigned_identity.workloads.id
    }

    secret {
        name                = "database-url"
        key_vault_secret_id = azurerm_key_vault_secret.admin_database_url.versionless_id
        identity            = azurerm_user_assigned_identity.workloads.id
    }

    template {
        min_replicas = var.admin_backend_min_replicas
        max_replicas = var.admin_backend_max_replicas

        container {
            name   = "admin-backend"
            image  = "${azurerm_container_registry.oliver.login_server}/admin-backend:${var.admin_backend_image_tag}"
            cpu    = 0.5
            memory = "1Gi"

            env {
                name  = "ENV"
                value = var.environment == "prod" ? "production" : var.environment
            }

            env {
                name  = "OLIVER_CORS_ORIGINS"
                value = local.admin_frontend_origin
            }

            env {
                name        = "DATABASE_URL"
                secret_name = "database-url"
            }

            env {
                name  = "APPLICATIONINSIGHTS_CONNECTION_STRING"
                value = azurerm_application_insights.oliver.connection_string
            }
        }
    }

    ingress {
        external_enabled           = false
        allow_insecure_connections = true
        target_port                = 8000
        transport                  = "auto"

        traffic_weight {
            latest_revision = true
            percentage      = 100
        }
    }

    depends_on = [
        azurerm_key_vault.oliver,
        azurerm_role_assignment.workloads_acr_pull,
        terraform_data.admin_backend_image,
        terraform_data.configure_database_access,
    ]
}

resource "azurerm_container_app" "admin_frontend" {
    name                         = local.admin_frontend_name
    resource_group_name          = azurerm_resource_group.oliver.name
    container_app_environment_id = azurerm_container_app_environment.oliver.id
    revision_mode                = "Single"
    tags                         = local.common_tags

    identity {
        type         = "UserAssigned"
        identity_ids = [azurerm_user_assigned_identity.workloads.id]
    }

    registry {
        server   = azurerm_container_registry.oliver.login_server
        identity = azurerm_user_assigned_identity.workloads.id
    }

    secret {
        name                = "entra-client-secret"
        key_vault_secret_id = azurerm_key_vault_secret.admin_auth_client_secret.versionless_id
        identity            = azurerm_user_assigned_identity.workloads.id
    }

    template {
        min_replicas = var.admin_frontend_min_replicas
        max_replicas = var.admin_frontend_max_replicas

        container {
            name   = "admin-frontend"
            image  = "${azurerm_container_registry.oliver.login_server}/admin-frontend:${var.admin_frontend_image_tag}"
            cpu    = 0.25
            memory = "0.5Gi"

            env {
                name  = "ADMIN_BACKEND_URL"
                value = "https://${azurerm_container_app.admin_backend.ingress[0].fqdn}"
            }
        }
    }

    ingress {
        external_enabled           = true
        allow_insecure_connections = false
        target_port                = 80
        transport                  = "auto"

        traffic_weight {
            latest_revision = true
            percentage      = 100
        }
    }

    depends_on = [
        azurerm_container_app.admin_backend,
        azurerm_role_assignment.workloads_acr_pull,
        terraform_data.admin_frontend_image,
    ]
}

resource "azurerm_container_app_job" "database_migrations" {
    name                         = "job-${local.name_prefix}-migrations"
    location                     = azurerm_resource_group.oliver.location
    resource_group_name          = azurerm_resource_group.oliver.name
    container_app_environment_id = azurerm_container_app_environment.oliver.id
    replica_timeout_in_seconds   = 900
    replica_retry_limit          = 1
    tags                         = local.common_tags

    identity {
        type         = "UserAssigned"
        identity_ids = [azurerm_user_assigned_identity.workloads.id]
    }

    registry {
        server   = azurerm_container_registry.oliver.login_server
        identity = azurerm_user_assigned_identity.workloads.id
    }

    secret {
        name                = "database-url"
        key_vault_secret_id = azurerm_key_vault_secret.oliver_database_url.versionless_id
        identity            = azurerm_user_assigned_identity.workloads.id
    }

    secret {
        name                = "model-api-key"
        key_vault_secret_id = azurerm_key_vault_secret.model_api_key.versionless_id
        identity            = azurerm_user_assigned_identity.workloads.id
    }

    secret {
        name                = "internal-api-key"
        key_vault_secret_id = azurerm_key_vault_secret.internal_api_key.versionless_id
        identity            = azurerm_user_assigned_identity.workloads.id
    }

    manual_trigger_config {
        parallelism              = 1
        replica_completion_count = 1
    }

    template {
        container {
            name    = "migrations"
            image   = "${azurerm_container_registry.oliver.login_server}/oliver:${var.oliver_image_tag}"
            cpu     = 0.5
            memory  = "1Gi"
            command = ["/bin/sh"]
            args    = ["-c", "uv run --no-sync alembic upgrade head"]

            env {
                name        = "DATABASE_URL"
                secret_name = "database-url"
            }

            env {
                name        = "OPENAI_API_KEY"
                secret_name = "model-api-key"
            }

            env {
                name  = "OPENAI_MODEL"
                value = var.model_name
            }

            env {
                name  = "OPENAI_BASE_URL"
                value = var.model_base_url
            }

            env {
                name        = "INTERNAL_API_KEY"
                secret_name = "internal-api-key"
            }
        }
    }

    depends_on = [
        azurerm_key_vault.oliver,
        azurerm_role_assignment.workloads_acr_pull,
        terraform_data.oliver_image,
    ]
}

resource "azurerm_container_app_job" "database_access" {
    name                         = "job-${local.name_prefix}-database-access"
    location                     = azurerm_resource_group.oliver.location
    resource_group_name          = azurerm_resource_group.oliver.name
    container_app_environment_id = azurerm_container_app_environment.oliver.id
    replica_timeout_in_seconds   = 300
    replica_retry_limit          = 1
    tags                         = local.common_tags

    identity {
        type         = "UserAssigned"
        identity_ids = [azurerm_user_assigned_identity.workloads.id]
    }

    secret {
        name                = "sql-administrator-password"
        key_vault_secret_id = azurerm_key_vault_secret.sql_administrator_password.versionless_id
        identity            = azurerm_user_assigned_identity.workloads.id
    }

    secret {
        name                = "sql-admin-reader-password"
        key_vault_secret_id = azurerm_key_vault_secret.sql_admin_reader_password.versionless_id
        identity            = azurerm_user_assigned_identity.workloads.id
    }

    manual_trigger_config {
        parallelism              = 1
        replica_completion_count = 1
    }

    template {
        container {
            name    = "database-access"
            image   = "mcr.microsoft.com/mssql-tools"
            cpu     = 0.25
            memory  = "0.5Gi"
            command = ["/bin/bash"]
            args = [
                "-c",
                <<-EOT
                    /opt/mssql-tools18/bin/sqlcmd \
                        -S "$SQL_SERVER" \
                        -d "$SQL_DATABASE" \
                        -U "$SQL_ADMIN_LOGIN" \
                        -P "$SQL_ADMIN_PASSWORD" \
                        -C \
                        -b \
                        -Q "IF DATABASE_PRINCIPAL_ID(N'${var.sql_admin_reader_login}') IS NULL CREATE USER [${var.sql_admin_reader_login}] WITH PASSWORD = '$SQL_ADMIN_READER_PASSWORD' ELSE ALTER USER [${var.sql_admin_reader_login}] WITH PASSWORD = '$SQL_ADMIN_READER_PASSWORD'; IF IS_ROLEMEMBER(N'db_datareader', N'${var.sql_admin_reader_login}') <> 1 ALTER ROLE db_datareader ADD MEMBER [${var.sql_admin_reader_login}]; DENY INSERT, UPDATE, DELETE, EXECUTE TO [${var.sql_admin_reader_login}];"
                EOT
            ]

            env {
                name  = "SQL_SERVER"
                value = azurerm_mssql_server.oliver.fully_qualified_domain_name
            }

            env {
                name  = "SQL_DATABASE"
                value = azurerm_mssql_database.oliver.name
            }

            env {
                name  = "SQL_ADMIN_LOGIN"
                value = var.sql_administrator_login
            }

            env {
                name        = "SQL_ADMIN_PASSWORD"
                secret_name = "sql-administrator-password"
            }

            env {
                name        = "SQL_ADMIN_READER_PASSWORD"
                secret_name = "sql-admin-reader-password"
            }
        }
    }

    depends_on = [
        azurerm_key_vault.oliver,
        terraform_data.run_database_migrations,
    ]
}

resource "terraform_data" "configure_database_access" {
    triggers_replace = [
        azurerm_container_app_job.database_access.id,
        var.sql_admin_reader_login,
        nonsensitive(sha256(random_password.sql_administrator.result)),
        nonsensitive(sha256(random_password.sql_admin_reader.result)),
    ]

    provisioner "local-exec" {
        command = <<-EOT
            execution_name=$(az containerapp job start --name ${azurerm_container_app_job.database_access.name} --resource-group ${azurerm_resource_group.oliver.name} --query name --output tsv)
            for attempt in $(seq 1 30); do
                status=$(az containerapp job execution show --name "$execution_name" --job-name ${azurerm_container_app_job.database_access.name} --resource-group ${azurerm_resource_group.oliver.name} --query properties.status --output tsv)
                if [ "$status" = "Succeeded" ]; then
                    exit 0
                fi
                if [ "$status" = "Failed" ]; then
                    exit 1
                fi
                sleep 10
            done
            exit 1
        EOT
    }
}

resource "terraform_data" "run_database_migrations" {
    triggers_replace = [
        terraform_data.oliver_image.id,
        azurerm_container_app_job.database_migrations.id,
    ]

    provisioner "local-exec" {
        command = <<-EOT
            execution_name=$(az containerapp job start --name ${azurerm_container_app_job.database_migrations.name} --resource-group ${azurerm_resource_group.oliver.name} --query name --output tsv)
            for attempt in $(seq 1 90); do
                status=$(az containerapp job execution show --name "$execution_name" --job-name ${azurerm_container_app_job.database_migrations.name} --resource-group ${azurerm_resource_group.oliver.name} --query properties.status --output tsv)
                if [ "$status" = "Succeeded" ]; then
                    exit 0
                fi
                if [ "$status" = "Failed" ]; then
                    exit 1
                fi
                sleep 10
            done
            exit 1
        EOT
    }
}
