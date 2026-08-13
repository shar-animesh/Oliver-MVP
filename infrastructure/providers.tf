provider "azurerm" {
    subscription_id = var.subscription_id

    features {
        key_vault {
            purge_soft_delete_on_destroy    = false
            recover_soft_deleted_key_vaults = true
        }
    }
}

provider "azapi" {}

provider "azuread" {
    tenant_id = data.azurerm_client_config.current.tenant_id
}
