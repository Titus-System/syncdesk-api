.PHONY: install run dev lint format typecheck test seed migrate makemigration pre-commit

install:
	poetry install

run:
	poetry run uvicorn app.main:create_app --factory

dev:
	poetry run uvicorn app.main:create_app --factory --reload

lint:
	poetry run ruff check app/
	poetry run bandit -r app/

format:
	poetry run ruff format app/

typecheck:
	poetry run mypy app/


test:
	poetry run pytest

test-e2e:
	poetry run pytest tests/app/e2e/

seed:
	poetry run python app/seed/run_seed.py

migrate:
	poetry run alembic upgrade head

makemigration:
	poetry run alembic revision --autogenerate -m "$(m)"

pre-commit:
	poetry run ruff check --fix app/
	poetry run ruff format app/
	poetry run mypy app/
	poetry run bandit -c pyproject.toml -r app/
	poetry run pytest
