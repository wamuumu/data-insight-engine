# Load environment variables
include .env

# Make settings
MAKEFLAGS += --no-print-directory
SHELL := /bin/bash
.SHELLFLAGS := -O extglob -c

# Terminal colors
RESET := \033[0m
GREEN := \033[32m
BLUE := \033[34m
YELLOW := \033[33m
CYAN := \033[36m

# Define variables
DOCKER_DATA_VOLUMES := $(shell \
    yq -r '.volumes[] | "-v " + .path + ":" + .target + (if .readonly then ":ro" else "" end)' \
    $(MOUNTS_FILE) \
)

DOCKER_RUN = docker run --rm -it \
	--env-file .env \
	--network $(NETWORK_NAME) \
	-p ${METRICS_PORT:-8000}:8000 \
	$(DOCKER_DATA_VOLUMES) \
	$(APP_IMAGE):latest

.PHONY: help build up down shell migrate migrate-new db

# ── Default target ─────────────────────────────────────────────
help:
	@echo ""
	@printf "$(CYAN)Usage: make [target]$(RESET)\n"
	@echo ""
	@printf "  $(GREEN)make build$(RESET)\t\t\tBuild the app Docker image\n"
	@printf "  $(GREEN)make up$(RESET)\t\t\tStart all services in detached mode\n"
	@printf "  $(GREEN)make down$(RESET)\t\t\tStop and remove containers\n"
	@printf "  $(GREEN)make shell$(RESET)\t\t\tOpen a shell in the app container\n"
	@echo ""
	@printf "  $(YELLOW)make migrate$(RESET)\t\t\tApply all pending database migrations\n"
	@printf "  $(YELLOW)make migrate-new m=<msg>$(RESET)\tGenerate a new migration (autogenerate with message)\n"
	@echo ""
	@printf "  $(BLUE)make db$(RESET)\t\t\tConnect to the database container\n"
	@echo ""

# ── Docker lifecycle ───────────────────────────────────────────
build:
	@printf "$(GREEN)Building Docker image: ${APP_IMAGE}:latest$(RESET)\n"
	@docker build --no-cache \
		-t ${APP_IMAGE}:latest \
		-f docker/app/Dockerfile .
	@printf "$(GREEN)Docker image built successfully$(RESET)\n"

up:
	@mkdir -p logs && chmod 777 logs
	@printf "$(GREEN)Created logs directory at:$(RESET) $(PWD)/logs\n"
	@printf "$(GREEN)Starting services with Docker Compose$(RESET)\n"
	@docker compose -p ${PROJECT_NAME} up -d
	@printf "$(CYAN)Grafana$(RESET)        → http://localhost:3000\n"
	@printf "$(CYAN)Prometheus$(RESET)     → http://localhost:9090\n"
	@printf "$(CYAN)Metrics$(RESET)        → http://localhost:${METRICS_PORT}/metrics\n"

down:
	@printf "$(GREEN)Stopping and removing containers (with volumes)$(RESET)\n"
	@docker compose -p ${PROJECT_NAME} down -v
	@printf "$(GREEN)Containers stopped and removed$(RESET)\n"

shell:
	@mkdir -p logs && chmod 777 logs
	@printf "$(GREEN)Created logs directory at:$(RESET) $(PWD)/logs\n"
	@printf "$(GREEN)Opening shell in app container$(RESET)\n"
	@$(DOCKER_RUN) bash
	@printf "$(GREEN)Exited shell in app container$(RESET)\n"

migrate:
	@printf "$(YELLOW)Applying database migrations$(RESET)\n"
	@$(DOCKER_RUN) alembic -c alembic.ini upgrade head
	@printf "$(GREEN)Database migrations applied successfully$(RESET)\n"

migrate-new:
	@printf "$(YELLOW)Generating new migration with message: $(m)$(RESET)\n"
	@$(DOCKER_RUN) alembic -c alembic.ini revision --autogenerate -m "$(m)"
	@printf "$(GREEN)New migration generated successfully$(RESET)\n"

db:
	@printf "$(GREEN)Connecting to the database container$(RESET)\n"
	@docker compose -p ${PROJECT_NAME} exec postgres psql -U ${DB_USER} -d ${DB_NAME}
	@printf "$(GREEN)Exited database container$(RESET)\n"