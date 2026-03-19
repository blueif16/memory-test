.PHONY: help dev install migrate seed test clean lint format typecheck debug

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  %-15s %s\n", $$1, $$2}'

dev: ## Start services with docker-compose
	docker-compose up --build

install: ## Install backend dependencies
	cd backend && poetry install

migrate: ## Push database migrations
	supabase db push

seed: ## Seed the database
	supabase db seed

test: ## Run backend tests
	cd backend && poetry run pytest

clean: ## Remove containers, volumes, and caches
	docker-compose down -v
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

lint: ## Run ruff linter
	cd backend && poetry run ruff check app/

format: ## Run ruff formatter
	cd backend && poetry run ruff format app/

typecheck: ## Run mypy type checking
	cd backend && poetry run mypy app/ --ignore-missing-imports

debug: ## Start backend with debug logging
	cd backend && DEBUG=true poetry run uvicorn app.main:app --reload --log-level debug
