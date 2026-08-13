# CLAUDE.md

Oliver is a single-agent email assistant for assessing and coordinating internal AI initiatives.

## Repository layout

- `oliver`: Independently deployed FastAPI email API, system prompt, persistence, and migrations.
- `admin-dashboard/backend`: Read-only FastAPI API for Oliver communications.
- `admin-dashboard/frontend`: React, Vite, and TypeScript dashboard UI.
- `infrastructure`: Terraform for all Azure resources and the Logic App workflow.
- `docs`: Architecture decisions, delivery notes, and source planning documents.

## Conventions

- Always track multi-step tasks and keep their statuses current.
- Read the nearest scoped `CLAUDE.md` before changing a project.
- Write error messages inline at the `raise`, `throw`, or return site; do not extract single-use error constants.
- Comments describe current behavior only.
- Never delete user data, environment files, or deployment state as part of code cleanup.
- Keep backend and frontend independently deployable. Production traffic is joined by a reverse proxy; the backend never serves frontend build artifacts.

## Source control

- Do not rewrite history, remove remotes, or perform destructive Git operations unless the user explicitly requests it.
- Preserve unrelated and uncommitted work.
