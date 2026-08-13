resource "azuread_application" "admin_dashboard" {
    display_name     = "Oliver Admin Dashboard (${var.environment})"
    sign_in_audience = "AzureADMyOrg"

    web {
        redirect_uris = ["${local.admin_frontend_origin}/.auth/login/aad/callback"]

        implicit_grant {
            access_token_issuance_enabled = false
            id_token_issuance_enabled     = true
        }
    }
}

resource "azuread_service_principal" "admin_dashboard" {
    client_id = azuread_application.admin_dashboard.client_id
}

resource "azuread_application_password" "admin_dashboard" {
    application_id = azuread_application.admin_dashboard.id
    display_name   = "Container Apps authentication"
    end_date       = var.admin_auth_secret_end_date
}

resource "azurerm_key_vault_secret" "admin_auth_client_secret" {
    name         = "admin-auth-client-secret"
    value        = azuread_application_password.admin_dashboard.value
    key_vault_id = azurerm_key_vault.oliver.id
}

resource "azapi_resource" "admin_frontend_auth" {
    type      = "Microsoft.App/containerApps/authConfigs@2025-01-01"
    name      = "current"
    parent_id = azurerm_container_app.admin_frontend.id

    body = {
        properties = {
            globalValidation = {
                redirectToProvider        = "azureactivedirectory"
                unauthenticatedClientAction = "RedirectToLoginPage"
            }
            identityProviders = {
                azureActiveDirectory = {
                    registration = {
                        clientId                = azuread_application.admin_dashboard.client_id
                        clientSecretSettingName = "entra-client-secret"
                        openIdIssuer            = "https://login.microsoftonline.com/${data.azurerm_client_config.current.tenant_id}/v2.0"
                    }
                }
            }
            platform = {
                enabled = true
            }
        }
    }
}
