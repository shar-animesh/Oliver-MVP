# CLAUDE.md

Read-only FastAPI process for the Oliver administrative dashboard. Oliver workflow APIs belong to root `oliver`, not this project.

## Stack

- FastAPI and gunicorn/uvicorn
- Python 3.12
- Pydantic and Pydantic Settings
- uv
- Ruff with line length 150
- JSON structured logging with request correlation

## Conventions

- File headers use `# Path:` and `# Description:`.
- Access configuration only through `app.config.get_settings()`. Never use `os.getenv`, `os.environ`, or ad hoc dotenv loading in application code.
- `Settings` fields and validators come first. Its `model_config` is the final class attribute, loads `.env`, and forbids unknown dotenv entries.
- Only `.env` and `.env.template` are used. No spaces around `=`. Every `Settings` field must be mirrored in both files whenever configuration changes.
- `# noqa: B008` is required on every `Depends()` default argument.
- Use `typing` module forms such as `List`, `Dict`, `Optional`, and `Union` in Python annotations.
- Logger calls use stdlib logging and f-strings.
- Write errors inline at the `raise` or return site.
- Comments describe only current behavior.
- Expose read-only email-thread endpoints and `/health`. Do not add workflow writes or proxy Oliver email requests.
- The backend never serves frontend static files. Production routing belongs to the reverse proxy.
- Do not add automated tests or test tooling unless explicitly requested.

## Environment

- Local settings live in `.env`; the checked-in contract is `.env.template`.
- Configuration is validated at process startup. Enabled auth, Cosmos, or Graph integrations fail fast when required values are missing.

## Commands

- Install: `uv sync`
- Run: `make run`
- Format: `make format`
- Check: `make lint`
