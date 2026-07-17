# RAG E-Commerce Agent — Makefile
.PHONY: help install dev test lint docker-up docker-down seed clean

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install backend dependencies
	cd apps/backend && pip install -r requirements.txt

dev: ## Start backend dev server
	cd apps/backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8080

docker-up: ## Start infrastructure (PostgreSQL + Backend)
	docker compose -f infrastructure/docker-compose.yml up -d

docker-down: ## Stop infrastructure
	docker compose -f infrastructure/docker-compose.yml down

test: ## Run backend tests
	cd apps/backend && python -m pytest tests/ -v

seed: ## Seed product data
	cd apps/backend && python scripts/seed_data.py

clean: ## Clean Python cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete 2>/dev/null || true

deploy: ## One-click deploy (Linux/WSL/macOS)
	bash deploy.sh

deploy-build: ## Deploy + force rebuild backend image
	bash deploy.sh --build

deploy-win: ## One-click deploy (Windows PowerShell)
	powershell -ExecutionPolicy Bypass -File deploy.ps1

deploy-win-build: ## Deploy-win + force rebuild backend image
	powershell -ExecutionPolicy Bypass -File deploy.ps1 -Build

deploy-stop: ## Stop all deployed services
	bash deploy.sh --stop
