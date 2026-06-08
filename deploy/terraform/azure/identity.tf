# User-assigned managed identity for the external-secrets operator. Grant it
# read on the vault, then federate it to the in-cluster external-secrets KSA
# (the federated credential references the AKS OIDC issuer, created with the
# cluster — hence kept out of this data module):
#
#   az identity federated-credential create \
#     --identity-name <name> --resource-group <rg> \
#     --issuer <aks-oidc-issuer-url> \
#     --subject system:serviceaccount:external-secrets:external-secrets \
#     --audience api://AzureADTokenExchange

resource "azurerm_user_assigned_identity" "external_secrets" {
  name                = "${var.name_prefix}-ext-secrets"
  location            = var.location
  resource_group_name = local.rg_name
  tags                = local.tags
}

resource "azurerm_role_assignment" "es_secrets_user" {
  scope                = azurerm_key_vault.this.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.external_secrets.principal_id
}
