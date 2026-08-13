data "azurerm_managed_api" "office365" {
    name     = "office365"
    location = azurerm_resource_group.oliver.location
}

resource "azurerm_api_connection" "office365" {
    name                = "office365-${local.name_prefix}"
    resource_group_name = azurerm_resource_group.oliver.name
    managed_api_id      = data.azurerm_managed_api.office365.id
    display_name        = "Oliver Office 365 connection (${var.environment})"

    lifecycle {
        ignore_changes = [parameter_values]
    }
}

locals {
    oliver_api_url = "https://${azurerm_container_app.oliver.ingress[0].fqdn}/api/v1/email/respond"

    workflow_definition = jsondecode(
        templatefile(
            "${path.module}/workflow/oliver-email-workflow.json.tftpl",
            {
                mailbox_address = var.mailbox_address
                oliver_api_url   = local.oliver_api_url
            },
        )
    )

    office365_connection = {
        office365 = {
            connectionId   = azurerm_api_connection.office365.id
            connectionName = azurerm_api_connection.office365.name
            id             = data.azurerm_managed_api.office365.id
        }
    }
}

resource "azapi_resource" "email_workflow" {
    type      = "Microsoft.Logic/workflows@2019-05-01"
    name      = "logic-${local.name_prefix}-email"
    parent_id = azurerm_resource_group.oliver.id
    location  = azurerm_resource_group.oliver.location
    tags      = local.common_tags

    body = {
        properties = {
            state      = "Enabled"
            definition = local.workflow_definition
            parameters = {
                "$connections" = {
                    value = local.office365_connection
                }
                internalApiKey = {
                    value = random_password.internal_api_key.result
                }
            }
        }
    }

    response_export_values = ["properties.accessEndpoint"]
}
