# CLAUDE.md

Administrative dashboard for Oliver. Its backend reads Oliver-owned Azure SQL tables through a read-only database identity, and its frontend displays conversations and semantic matches.

## Projects

- `backend`: FastAPI, Python 3.12, Pydantic Settings, uv, Ruff, gunicorn/uvicorn.
- `frontend`: React 18, TypeScript, Vite.

## Conventions

- Do not add automated tests, test files, snapshots, or test-only tooling unless explicitly requested.
- Do not add Oliver write or email workflow endpoints to the admin backend; those belong to root `oliver`.
- Keep the admin backend's `/health` endpoint unversioned and out of the public API schema.
- The frontend calls the admin backend `/api/v1/email-threads` read API.
- Never mount or copy the frontend build into the backend application.
- Run the scoped quality commands in both child projects before deployment.
