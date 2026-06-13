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

.PHONY: help build up down shell migrate migrate-new

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
	@printf "$(GREEN)Stopping and removing containers$(RESET)\n"
	@docker compose -p ${PROJECT_NAME} down
	@printf "$(GREEN)Containers stopped and removed$(RESET)\n"

# TODO: the following targets are not working, remove app from compose file and adjust accordingly

shell:
	@printf "$(GREEN)Opening shell in app container$(RESET)\n"
	@docker compose -p ${PROJECT_NAME} exec app bash
	@printf "$(GREEN)Exited shell$(RESET)\n"

migrate:
	@printf "$(YELLOW)Applying database migrations$(RESET)\n"
	@docker compose -p ${PROJECT_NAME} exec app \
		alembic -c alembic.ini upgrade head
	@printf "$(YELLOW)Database migrations applied successfully$(RESET)\n"

migrate-new:
	@printf "$(YELLOW)Generating new migration with message: ${m}$(RESET)\n"
	@docker compose -p ${PROJECT_NAME} exec app \
		alembic -c alembic.ini revision --autogenerate -m "${m}"
	@printf "$(YELLOW)New migration generated successfully$(RESET)\n"