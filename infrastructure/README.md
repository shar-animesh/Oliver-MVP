# Oliver Azure infrastructure

Terraform deploys Oliver as three Container Apps: the Oliver API, a private read-only admin API, and the authenticated admin frontend. It also creates Azure SQL, ACR, Key Vault, Log Analytics, Application Insights, the database migration job, and the Logic App email workflow.

## Prerequisites

- An Azure subscription and Microsoft Entra tenant.
- Azure CLI authenticated to the target subscription.
- Terraform and the Azure CLI Container Apps extension.
- Permission to create Azure resources, Entra applications, and an Office 365 API connection.
- A Microsoft 365 shared mailbox. The account used to authorize the Office 365 connection needs access to that mailbox and permission to send replies from it.
- An approved OpenAI response model and API key. Semantic retrieval uses `text-embedding-3-large` at 1,536 dimensions by default.
- A remote, access-controlled Azure Storage backend for production Terraform state. Secret inputs and generated database credentials are present in Terraform state.

## Configure

```bash
cp terraform.tfvars.example terraform.tfvars
export TF_VAR_model_api_key='replace-with-the-approved-key'
```

Set `mailbox_address`, the Azure OpenAI v1 `model_base_url`, and the Azure OpenAI deployment `model_name`. Oliver attaches Azure OpenAI's `web_search` Responses API tool, which is backed by Grounding with Bing. Cross-team search is restricted in the Oliver codebase to Siemens Energy email addresses.

## Deploy

```bash
terraform init -backend-config=backend.tf
terraform validate
terraform plan -out=oliver.tfplan
terraform apply oliver.tfplan
```

Terraform builds the three images in ACR. The migration job then applies Alembic, creates the admin dashboard's read-only SQL user, and backfills embeddings for existing conversations before the Oliver and admin APIs start.

## Authorize the mailbox connection

Terraform can create the Office 365 API connection resource, but Microsoft requires an interactive OAuth consent step for the mailbox identity. After deployment, open the generated Office 365 connection in the Azure portal, authorize it with the mailbox-enabled account, and confirm the Logic App trigger is connected.

The Logic App watches the shared mailbox inbox, calls Oliver with the generated `X-Internal-Api-Key`, and replies in the same Outlook conversation only when Oliver returns `SEND_EMAIL`.

## Semantic storage

Azure SQL remains the system of record. Raw inbound and outbound HTML is stored in `email_messages`. Each `email_threads` row stores a complete readable transcript and native `VECTOR(1536)` embedding. `oliver_run_related_threads` records every semantic match supplied to a response, including rank and cosine distance, so the admin dashboard can show why another initiative was considered related.
