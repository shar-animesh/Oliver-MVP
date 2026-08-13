.PHONY: format lint pre-commit-install

# ----------Local checks----------
format:
	uv run ruff check --fix .
	uv run ruff format .

# Lint and format check.
lint:
	uv run ruff check .
	uv run ruff format --check .

pre-commit-install:
	uv run pre-commit install
