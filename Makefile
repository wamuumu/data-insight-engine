# Load environment variables
include .env

.PHONY: help build up down shell migrate migrate-new

# ── Default target ─────────────────────────────────────────────
help:
	@echo ""
	@echo "Usage: make [target]"
	@echo ""
	@echo "  make build      				Build the app Docker image"
	@echo "  make up         				Start all services in detached mode"
	@echo "  make down       				Stop and remove containers"
	@echo "  make shell      				Open a shell in the app container"
	@echo ""
	@echo "  make migrate    				Apply all pending database migrations"
	@echo "  make migrate-new m=<msg>  		Generate a new migration (autogenerate with message)"
	@echo ""
	@echo "  make test       				Run the full test suite"
	@echo "  make lint       				Run code linters and formatters"
	@echo ""

# ── Docker lifecycle ───────────────────────────────────────────
build:
	@echo "Building Docker image: ${APP_IMAGE}:latest"
	docker build --no-cache \
		-t ${APP_IMAGE}:latest \
		-f docker/app/Dockerfile .

up:
	@echo "Starting services with Docker Compose"
	docker compose -p ${PROJECT_NAME} up -d
	@echo "Grafana       	→ http://localhost:3000"
	@echo "Prometheus    	→ http://localhost:9090"
	@echo "Metrics       	→ http://localhost:${METRICS_PORT}/metrics"

down:
	@echo "Stopping and removing containers"
	docker compose -p ${PROJECT_NAME} down

shell:
	@echo "Opening shell in app container"
	docker compose -p ${PROJECT_NAME} exec app bash

migrate:
	@echo "Applying database migrations"
	docker compose -p ${PROJECT_NAME} exec app \
		alembic -c alembic.ini upgrade head

migrate-new:
	@echo "Generating new migration with message: ${m}"+
	docker compose -p ${PROJECT_NAME} exec app \
		alembic -c alembic.ini revision --autogenerate -m "${m}"