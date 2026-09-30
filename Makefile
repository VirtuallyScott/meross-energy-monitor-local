# Energy Hub developer commands. Run `make help` for the list.
REGISTRY ?= energy-hub
TAG      ?= 0.1.0
PLATFORMS ?= linux/amd64,linux/arm64
VENV     := .venv/bin

.PHONY: help secrets up up-sim down logs test test-backend test-web lint images images-push stack-deploy stack-rm backup

help:  ## Show targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*## "}{printf "  %-14s %s\n",$$1,$$2}'

secrets:  ## Create local secret files in deploy/secrets (kept if present)
	./scripts/gen-secrets.sh

up: secrets  ## Build and start the dev stack (https://localhost:8443)
	docker compose up -d --build

up-sim: secrets  ## Dev stack plus the EM16P simulator (add device "sim:8080")
	docker compose --profile sim up -d --build

down:  ## Stop the dev stack (volumes kept)
	docker compose --profile sim down

logs:  ## Follow logs for api and collector
	docker compose logs -f api collector

test: test-backend test-web  ## Run all tests in the same containers CI uses

test-backend:  ## Backend lint, types, tests (container)
	docker build --target test -t $(REGISTRY)/backend:test backend

test-web:  ## Web lint, types, tests (container)
	docker build --target test -t $(REGISTRY)/web:test web

lint:  ## Fast local lint without Docker
	cd backend && ../$(VENV)/ruff check app tests && ../$(VENV)/ruff format --check app tests && ../$(VENV)/mypy app
	cd web && npx eslint src && npx prettier --check src && npx tsc --noEmit

images:  ## Build runtime images for this machine
	docker build --target runtime -t $(REGISTRY)/backend:$(TAG) --build-arg APP_VERSION=$(TAG) backend
	docker build --target runtime -t $(REGISTRY)/web:$(TAG) --build-arg APP_VERSION=$(TAG) web

images-push:  ## Build and push multi-arch images (SWM-011); needs REGISTRY
	docker buildx build --platform $(PLATFORMS) --target runtime -t $(REGISTRY)/backend:$(TAG) --push backend
	docker buildx build --platform $(PLATFORMS) --target runtime -t $(REGISTRY)/web:$(TAG) --push web

stack-deploy: secrets  ## Deploy to Docker Swarm (see deploy/stack.yml header first)
	./scripts/swarm-secrets.sh
	REGISTRY=$(REGISTRY) TAG=$(TAG) docker stack deploy -c deploy/stack.yml energy

stack-rm:  ## Remove the Swarm stack (volumes and secrets kept)
	docker stack rm energy

backup:  ## Take a database backup now (dev stack)
	docker compose exec backup /bin/sh /scripts/backup.sh --once
