# Load environment variables
include .env

.PHONY: help build-app build-prefect build up down shell

# ── Default target ─────────────────────────────────────────────
help:
	@echo ""
	@echo "Usage: make [target]"
	@echo "  make build      Build the app Docker image"
	@echo "  make up         Start all services in detached mode"
	@echo "  make down       Stop and remove containers"
	@echo "  make shell      Open a shell in the app container"
	@echo ""

# ── Docker lifecycle ───────────────────────────────────────────
build-app:
	@echo "Building Docker image: ${APP_IMAGE}:latest"
	docker build --no-cache \
		-t ${APP_IMAGE}:latest \
		-f docker/app/Dockerfile .

build-prefect:
	@echo "Building Prefect image: ${PREFECT_IMAGE}:latest"
	docker build --no-cache \
		-t ${PREFECT_IMAGE}:latest \
		-f docker/prefect/Dockerfile .

build: build-app build-prefect

up:
	@echo "Starting services with Docker Compose"
	docker compose -p ${PROJECT_NAME} up -d
	@echo "Prefect UI  → http://localhost:4200"
	@echo "Grafana     → http://localhost:3000"

down:
	@echo "Stopping and removing containers"
	docker compose -p ${PROJECT_NAME} down

shell:
	@echo "Opening shell in app container"
	docker compose -p ${PROJECT_NAME} exec app bash