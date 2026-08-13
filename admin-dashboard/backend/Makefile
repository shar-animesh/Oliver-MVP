SERVICE_NAME = oliver-admin-dashboard-backend
IMAGE_NAME = oliver/admin-dashboard-backend:latest

.PHONY: format lint run

# ----------Local checks----------
format:
	uv run ruff check --fix .
	uv run ruff format .

lint:
	uv run ruff check .
	uv run ruff format --check .

run:
	uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
