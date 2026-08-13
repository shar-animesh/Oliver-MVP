# Oliver MVP

Oliver is a single-agent email assistant for Siemens Energy AI initiatives. It receives shared-mailbox messages through an Azure Logic App, stores full conversations in Azure SQL, retrieves related initiatives across internal teams, and returns either a branded HTML reply or a no-reply instruction.

## Repository

- `oliver/`: independently deployable FastAPI API, system prompt, email shell, SQLAlchemy schema, and Alembic migrations.
- `admin-dashboard/backend/`: read-only FastAPI API for stored Oliver conversations and semantic matches.
- `admin-dashboard/frontend/`: React and Vite interface for browsing conversations.
- `infrastructure/`: Terraform for Azure SQL, Container Apps, ACR, Key Vault, Logic Apps, Entra authentication, monitoring, migrations, and image builds.
- `docs/`: historical planning and delivery records.

## Runtime flow

```text
Microsoft 365 shared mailbox
    -> Azure Logic App
    -> POST /api/v1/email/respond with X-Internal-Api-Key
    -> Azure SQL conversation storage and vector retrieval
    -> OpenAI embedding and response models
    -> Logic App replies in the same email conversation
```

Oliver stores every inbound and outbound message. Each thread also stores a readable transcript and a 1,536-dimensional embedding. Before responding, Azure SQL ranks other internal threads using cosine distance. Relevant complete transcripts and contact details are supplied to Oliver, which may suggest a useful internal introduction without treating similarity as proof that two initiatives are duplicates.

## Local checks

```bash
cd oliver
uv sync
uv run ruff check .

cd ../admin-dashboard/backend
uv sync
uv run ruff check app

cd ../frontend
npm install
npm run typecheck
npm run build

cd ../../../infrastructure
terraform init
terraform validate
```

See `infrastructure/README.md` for Azure prerequisites and deployment steps.
