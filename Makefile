# ─────────────────────────────────────────────
# Environment
# ─────────────────────────────────────────────

-include .env
export

MAKEFLAGS += --no-print-directory
SHELL := /bin/bash

# ─────────────────────────────────────────────
# Colors
# ─────────────────────────────────────────────

RESET := \033[0m
GREEN := \033[32m
BLUE := \033[34m
YELLOW := \033[33m
CYAN := \033[36m

# ─────────────────────────────────────────────
# Safety checks
# ─────────────────────────────────────────────

ifndef PROJECT_NAME
$(error PROJECT_NAME is not set in .env)
endif

ifndef APP_IMAGE
$(error APP_IMAGE is not set in .env)
endif

ifndef NETWORK_NAME
$(error NETWORK_NAME is not set in .env)
endif

# ─────────────────────────────────────────────
# Docker configuration
# ─────────────────────────────────────────────

DOCKER_DATA_VOLUMES := $(shell \
    yq -r '.volumes[] | "-v " + .path + ":" + .target + (if .readonly then ":ro" else "" end)' \
    $(MOUNTS_FILE) \
)

DOCKER_RUN = docker run --rm -it \
	--name cli-app \
	--env-file .env \
	--network $(NETWORK_NAME) \
	-p ${METRICS_PORT:-8000}:8000 \
	$(DOCKER_DATA_VOLUMES) \
	$(APP_IMAGE):latest

.PHONY: help build up down shell db migrate test-unit test-integration test lint lint-fix format typecheck

# ── Default target ─────────────────────────────────────────────
help:
	@echo ""
	@printf "Usage: make [target]\n"
	@echo ""
	@printf "  $(GREEN)make build$(RESET)\t\t\tBuild the app Docker image\n"
	@printf "  $(GREEN)make up$(RESET)\t\t\tStart all services in detached mode\n"
	@printf "  $(GREEN)make down$(RESET)\t\t\tStop and remove containers\n"
	@printf "  $(GREEN)make shell$(RESET)\t\t\tOpen a shell in the app container\n"
	@printf "  $(GREEN)make db$(RESET)\t\t\tConnect to the database container\n"
	@printf "  $(GREEN)make migrate$(RESET)\t\t\tApply all pending database migrations\n"
	@echo ""
	@printf "  $(YELLOW)make test-unit$(RESET)\t\tRun unit tests\n"
	@printf "  $(YELLOW)make test-integration$(RESET)\t\tRun integration tests\n"
	@printf "  $(YELLOW)make test$(RESET)\t\t\tRun all tests\n"
	@echo ""
	@printf "  $(CYAN)make lint$(RESET)\t\t\tRun linter checks\n"
	@printf "  $(CYAN)make lint-fix$(RESET)\t\t\tRun linter checks and fix issues\n"
	@printf "  $(CYAN)make format$(RESET)\t\t\tFormat code\n"
	@printf "  $(CYAN)make typecheck$(RESET)\t\tRun type checks\n"
	@echo ""

# ── Docker lifecycle ───────────────────────────────────────────
build:
	@printf "$(GREEN)Building Docker image: ${APP_IMAGE}:latest$(RESET)\n"
	@docker build --no-cache \
		-t ${APP_IMAGE}:latest \
		-f docker/app/Dockerfile .

up:
	@mkdir -p logs && chmod 777 logs
	@printf "$(GREEN)Created logs directory at:$(RESET) $(PWD)/logs\n"
	@printf "$(GREEN)Starting services with Docker Compose$(RESET)\n"
	@docker compose -p ${PROJECT_NAME} up -d
	@printf "$(CYAN)Grafana$(RESET)        → http://localhost:3000\n"
	@printf "$(CYAN)Prometheus$(RESET)     → http://localhost:9090\n"

down:
	@docker compose -p ${PROJECT_NAME} down -v

shell:
	@$(DOCKER_RUN) bash

db:
	@docker compose -p ${PROJECT_NAME} exec postgres psql -U ${DB_USER} -d ${DB_NAME}

migrate:
	@printf "$(YELLOW)Applying database migrations$(RESET)\n"
	@$(DOCKER_RUN) alembic -c alembic.ini upgrade head

test-unit:
	@printf "$(BLUE)Running unit tests$(RESET)\n"
	@pytest tests/unit

test-integration:
	@printf "$(BLUE)Running integration tests$(RESET)\n"
	@pytest tests/integration

test: test-unit test-integration

lint:
	@printf "$(CYAN)Running linter checks$(RESET)\n"
	@ruff check .

lint-fix:
	@printf "$(CYAN)Running linter checks and fixing issues$(RESET)\n"
	@ruff check . --fix

format:
	@printf "$(CYAN)Formatting code$(RESET)\n"
	@ruff format .

typecheck:
	@printf "$(CYAN)Running type checks$(RESET)\n"
	@mypy .