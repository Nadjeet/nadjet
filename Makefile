# Nadjet developer commands. Run `make` or `make help` for the list.
# Works with GNU make 3.81+ (macOS default). Python via uv, TypeScript via pnpm, infra via Docker Compose.

SHELL := /bin/bash
.DEFAULT_GOAL := help

COMPOSE := docker compose -f deploy/local/compose.yml $(if $(wildcard .env),--env-file .env,)
PYTEST := uv run pytest
UNIT := -m "not integration and not brev"

.PHONY: help setup doctor env dev stop down infra infra-video infra-sms infra-logs ps camsim migrate \
	seed-cameras camsim-list camsim-restart camsim-freeze camsim-unfreeze camsim-outage \
	camsim-restore camsim-swap gen check-contracts \
	test test-unit test-integration test-brev coverage lint format typecheck build ci clean reset-db \
	brev-status brev-up brev-forward brev-unforward brev-check \
	brev-tunnel brev-untunnel brev-deploy-workers brev-logs \
	map-data routing-data routing-up routing-down seed-geo

help: ## Show this help
	@awk 'BEGIN {FS = ":.*## "; printf "Nadjet — make <target>\n\n"} /^[a-zA-Z_-]+:.*## / {printf "  \033[36m%-17s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# ---------------------------------------------------------------- setup
setup: env ## Install dependencies and tooling (idempotent)
	@bash scripts/doctor.sh || (echo "Fix the FAIL items above, then re-run make setup." && exit 1)
	uv sync --frozen
	pnpm install --frozen-lockfile
	git config core.hooksPath .githooks
	@echo "Setup complete. Next: make dev"

env: ## Create .env from .env.example if missing
	@test -f .env || (cp .env.example .env && echo "Created .env from .env.example")

doctor: ## Check tools, Docker, Brev login and project files
	@bash scripts/doctor.sh

# ---------------------------------------------------------------- run
dev: env camsim ## Start the full dev environment (infra + API + web; Ctrl-C to stop apps)
	$(COMPOSE) --profile video up -d --wait
	$(MAKE) migrate
	$(MAKE) seed-cameras
	@echo "API http://localhost:8080/docs · Web http://localhost:5173 · MediaMTX http://localhost:8889"
	uv run honcho -f Procfile.dev start

stop: ## Stop all services (keeps data)
	-@pkill -f "nadjet-api serve" 2>/dev/null; pkill -f "vite" 2>/dev/null; true
	$(COMPOSE) --profile video stop

down: ## Stop and remove containers (keeps data volumes)
	$(COMPOSE) --profile video down

infra: env ## Start PostGIS and Redis only, wait until healthy
	$(COMPOSE) up -d --wait db redis

infra-video: env camsim ## Start MediaMTX (simulated cameras) on top of the infrastructure
	$(COMPOSE) --profile video up -d --wait mediamtx

infra-sms: env ## Start the self-hosted SMS gateway server (private mode, TD-13)
	$(COMPOSE) --profile sms up -d --wait sms-db sms-server sms-worker

infra-logs: ## Follow infrastructure logs
	$(COMPOSE) --profile video logs -f

ps: ## Show infrastructure status
	$(COMPOSE) --profile video ps

camsim: ## Render the MediaMTX config from data/cameras.yaml
	@mkdir -p data/videos
	uv run nadjet-camsim render

migrate: ## Apply database migrations
	cd services/api && uv run alembic upgrade head

seed-cameras: ## Sync the camera registry from data/cameras.yaml (needs make migrate)
	uv run nadjet-api seed-cameras

# Simulator controls (FR-CAM-004), e.g. `make camsim-freeze CAM=cam-a1-pk42`. Needs make dev.
camsim-list: ## Show every simulated camera and whether it is live
	uv run nadjet-camsim list

camsim-restart: ## Restart a camera's clip from the start: CAM=<id>
	@test -n "$(CAM)" || { echo "usage: make $@ CAM=<camera-id>"; exit 1; }
	uv run nadjet-camsim restart $(CAM)

camsim-freeze: ## Freeze a camera (no new frames, session stays open): CAM=<id>
	@test -n "$(CAM)" || { echo "usage: make $@ CAM=<camera-id>"; exit 1; }
	uv run nadjet-camsim freeze $(CAM)

camsim-unfreeze: ## Resume a frozen camera: CAM=<id>
	@test -n "$(CAM)" || { echo "usage: make $@ CAM=<camera-id>"; exit 1; }
	uv run nadjet-camsim unfreeze $(CAM)

camsim-outage: ## Drop a camera's stream path (camera offline): CAM=<id>
	@test -n "$(CAM)" || { echo "usage: make $@ CAM=<camera-id>"; exit 1; }
	uv run nadjet-camsim outage $(CAM)

camsim-restore: ## Bring a camera back after an outage: CAM=<id>
	@test -n "$(CAM)" || { echo "usage: make $@ CAM=<camera-id>"; exit 1; }
	uv run nadjet-camsim restore $(CAM)

camsim-swap: ## Play another clip from data/videos on a camera: CAM=<id> VIDEO=<file>
	@test -n "$(CAM)" -a -n "$(VIDEO)" || { echo "usage: make $@ CAM=<camera-id> VIDEO=<file>"; exit 1; }
	uv run nadjet-camsim swap $(CAM) $(VIDEO)

# ---------------------------------------------------------------- map and routing
map-data: ## Download the offline Algeria basemap to data/map/algeria.pmtiles (~560 MB, once)
	@bash scripts/map-data.sh
	@bash scripts/map-assets.sh

routing-data: ## Download the Algeria OSM extract and prepare OSRM data (~290 MB, ~1.3 GB RAM, once)
	@bash scripts/routing-data.sh

routing-up: env ## Start OSRM (after make routing-data) and wait until healthy
	$(COMPOSE) --profile routing up -d --wait osrm

routing-down: ## Stop OSRM
	$(COMPOSE) --profile routing stop osrm

seed-geo: ## Import facilities and units from data/seed/*.csv (idempotent)
	uv run nadjet-api seed-geo

# ---------------------------------------------------------------- contracts
gen: ## Regenerate contracts (event schemas, OpenAPI) and the TS client
	uv run nadjet-export-schemas
	uv run nadjet-api export-openapi
	pnpm gen:client

check-contracts: ## Fail if generated contracts or the TS client are out of date
	uv run nadjet-export-schemas --check
	uv run nadjet-api export-openapi --check
	pnpm gen:client >/dev/null
	@git diff --exit-code -- packages/api-client/src/schema.d.ts || (echo "TS client out of date: run make gen" && exit 1)

# ---------------------------------------------------------------- quality
test: infra infra-video migrate ## Run all non-frontend tests (unit + integration) with coverage
	$(PYTEST) -m "not brev" --cov --cov-report=term --cov-report=xml

test-unit: ## Run unit tests only (no infrastructure needed)
	$(PYTEST) $(UNIT)

test-integration: infra infra-video migrate ## Run integration tests against local PostGIS and Redis
	$(PYTEST) -m integration

test-brev: ## Live check of the Brev AI endpoint (needs make brev-forward; uses GPU credits)
	$(PYTEST) -m brev

lint: ## Lint Python and TypeScript, check formatting and repository rules
	uv run ruff check .
	uv run ruff format --check .
	pnpm lint
	pnpm format:check
	@bash scripts/check-integrity.sh
	@bash scripts/check-migrations.sh
	uv run nadjet-camsim check

typecheck: ## Type-check Python (mypy strict) and TypeScript
	uv run mypy
	pnpm typecheck

format: ## Format and auto-fix Python and TypeScript
	uv run ruff check --fix .
	uv run ruff format .
	pnpm format

build: ## Build Python wheels and the web app
	uv build --all-packages --out-dir dist
	pnpm build

ci: lint typecheck check-contracts test build ## Everything CI runs

# ---------------------------------------------------------------- cleanup
clean: ## Remove caches and build outputs (keeps .env, dependencies and data)
	rm -rf dist apps/web/dist .pytest_cache .mypy_cache .ruff_cache .coverage coverage.xml htmlcov
	find . -name __pycache__ -type d -prune -not -path "./node_modules/*" -not -path "./.venv/*" -exec rm -rf {} +
	rm -f deploy/local/mediamtx.generated.yml

reset-db: ## DANGER: delete local database and Redis volumes (asks for confirmation)
	@read -r -p "Delete local PostGIS and Redis data? [y/N] " ans && [ "$$ans" = "y" ]
	$(COMPOSE) --profile video down -v

# ---------------------------------------------------------------- NVIDIA Brev (all AI inference)
brev-status: ## List Brev instances
	@bash scripts/brev.sh status

brev-up: ## Start vLLM on the running Brev instance and wait until it serves
	@bash scripts/brev.sh up

brev-forward: ## Forward localhost:18000 to vLLM on the Brev instance
	@bash scripts/brev.sh forward

brev-unforward: ## Stop the Brev port forward
	@bash scripts/brev.sh unforward

brev-check: ## Verify the Brev AI endpoint serves the configured model
	@bash scripts/brev.sh check

brev-tunnel: ## Open vLLM (-L) and local MediaMTX + API (-R) tunnels to the Brev instance
	@bash scripts/brev.sh tunnel

brev-untunnel: ## Close the three Brev tunnels
	@bash scripts/brev.sh untunnel

brev-deploy-workers: ## Pull (or build on the instance) the vision image and start the workers on Brev
	@bash scripts/brev.sh deploy-workers

brev-logs: ## Vision worker logs on Brev (make brev-logs F=-f to follow)
	@bash scripts/brev.sh logs $(F)
