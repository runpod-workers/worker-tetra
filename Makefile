IMAGE = runpod/flash
TAG = $(or $(FLASH_IMAGE_TAG),local)
FULL_IMAGE = $(IMAGE):$(TAG)
FULL_IMAGE_CPU = $(IMAGE)-cpu:$(TAG)

# Detect host platform for local builds
ARCH := $(shell uname -m)
ifeq ($(ARCH),x86_64)
	PLATFORM := linux/amd64
else ifeq ($(ARCH),aarch64)
	PLATFORM := linux/arm64
else ifeq ($(ARCH),arm64)
	PLATFORM := linux/arm64
else
	PLATFORM := linux/amd64
endif

# WIP testing configuration (multi-platform builds)
WIP_TAG ?= wip
MULTI_PLATFORM := linux/amd64,linux/arm64

.PHONY: setup help

# Check if 'uv' is installed
ifeq (, $(shell which uv))
$(error "uv is not installed. Please install it before running this Makefile.")
endif

# Default target - show available commands
help: # Show this help menu
	@echo "Available make commands:"
	@echo ""
	@awk 'BEGIN {FS = ":.*# "; printf "%-20s %s\n", "Target", "Description"} /^[a-zA-Z_][a-zA-Z0-9_-]*:.*# / {printf "%-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo ""

dev: # Install development dependencies
	uv sync --all-groups

update: # Upgrade all dependencies
	uv sync --upgrade --all-groups
	uv lock --upgrade

clean: # Remove build artifacts and cache files
	rm -rf dist build *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pkl" -delete

setup: dev # Initialize project and sync dependencies
	@echo "Setup complete. Development environment ready."

build: # Build both GPU and CPU Docker images
	make build-gpu
	make build-cpu
	make build-lb
	make build-lb-cpu

build-gpu: setup # Build GPU Docker image for host platform
	docker buildx build \
	--platform $(PLATFORM) \
	-t $(FULL_IMAGE) \
	. --load

build-cpu: setup # Build CPU-only Docker image for host platform
	docker buildx build \
	--platform $(PLATFORM) \
	-f Dockerfile-cpu \
	-t $(FULL_IMAGE_CPU) \
	. --load

build-lb: setup # Build Load Balancer Docker image for host platform
	docker buildx build \
	--platform $(PLATFORM) \
	-f Dockerfile-lb \
	-t $(IMAGE)-lb:$(TAG) \
	. --load

build-lb-cpu: setup # Build CPU-only Load Balancer Docker image for host platform
	docker buildx build \
	--platform $(PLATFORM) \
	-f Dockerfile-lb-cpu \
	-t $(IMAGE)-lb-cpu:$(TAG) \
	. --load

# WIP Build Targets (multi-platform, requires Docker Hub push)
# Usage: make build-wip
# Custom tag: make build-wip WIP_TAG=myname-feature
# Then deploy with: export FLASH_IMAGE_TAG=wip (or your custom tag)

build-wip: # Build and push all WIP images (multi-platform)
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "Building multi-platform WIP images with tag :$(WIP_TAG)"
	@echo "This will push to Docker Hub registry (requires docker login)"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	make build-wip-gpu
	make build-wip-cpu
	make build-wip-lb
	make build-wip-lb-cpu
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "✅ WIP images pushed to Docker Hub with tag :$(WIP_TAG)"
	@echo "Next steps:"
	@echo "  1. export FLASH_IMAGE_TAG=$(WIP_TAG)"
	@echo "  2. Deploy to RunPod and test"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

build-wip-gpu: setup # Build and push GPU image (multi-platform)
	docker buildx build \
	--platform $(MULTI_PLATFORM) \
	-t $(IMAGE):$(WIP_TAG) \
	. --push

build-wip-cpu: setup # Build and push CPU image (multi-platform)
	docker buildx build \
	--platform $(MULTI_PLATFORM) \
	-f Dockerfile-cpu \
	-t $(IMAGE)-cpu:$(WIP_TAG) \
	. --push

build-wip-lb: setup # Build and push LB image (multi-platform)
	docker buildx build \
	--platform $(MULTI_PLATFORM) \
	-f Dockerfile-lb \
	-t $(IMAGE)-lb:$(WIP_TAG) \
	. --push

build-wip-lb-cpu: setup # Build and push LB CPU image (multi-platform)
	docker buildx build \
	--platform $(MULTI_PLATFORM) \
	-f Dockerfile-lb-cpu \
	-t $(IMAGE)-lb-cpu:$(WIP_TAG) \
	. --push

# Test commands
test: # Run all tests
	uv run pytest tests/ -v

test-unit: # Run unit tests only
	uv run pytest tests/unit/ -v -m "not integration"

test-integration: # Run integration tests only
	uv run pytest tests/integration/ -v -m integration

test-coverage: # Run tests with coverage report
	uv run pytest tests/ -v --cov=handler --cov=remote_execution --cov-report=term-missing

test-fast: # Run tests with fast-fail mode
	uv run pytest tests/ -v -x --tb=short

test-handler: # Test handler locally with all test_*.json files
	cd src && ./test-handler.sh

test-lb-handler: # Test Load Balancer handler with /execute endpoint
	cd src && ./test-lb-handler.sh

# Smoke Tests (local Docker validation)

smoketest: build-gpu # Test Docker image locally
	docker run --rm $(FULL_IMAGE) ./test-handler.sh

smoketest-lb: build-lb # Test Load Balancer Docker image locally
	docker run --rm $(IMAGE)-lb:$(TAG) ./test-lb-handler.sh

smoketest-lb-cpu: build-lb-cpu # Test CPU-only Load Balancer Docker image locally
	docker run --rm $(IMAGE)-lb-cpu:$(TAG) ./test-lb-handler.sh

# Linting commands
lint: # Check code with ruff
	uv run ruff check .

lint-fix: # Fix code issues with ruff
	uv run ruff check . --fix

format: # Format code with ruff
	uv run ruff format .

format-check: # Check code formatting
	uv run ruff format --check .

# Type checking
typecheck: # Check types with mypy
	uv run mypy src/

# Quality gates (used in CI)
quality-check: format-check lint typecheck test-coverage test-handler

# Code intelligence commands
index: # Generate code intelligence index
	@echo "🔍 Indexing codebase..."
	@uv run python scripts/ast_to_sqlite.py

query: # Query symbols (usage: make query SYMBOL=name)
	@test -n "$(SYMBOL)" || (echo "Usage: make query SYMBOL=<name>" && exit 1)
	@uv run python scripts/code_intel.py find "$(SYMBOL)"

query-interface: # Show class interface (usage: make query-interface CLASS=ClassName)
	@test -n "$(CLASS)" || (echo "Usage: make query-interface CLASS=<ClassName>" && exit 1)
	@uv run python scripts/code_intel.py interface "$(CLASS)"

query-file: # Show file symbols (usage: make query-file FILE=path)
	@test -n "$(FILE)" || (echo "Usage: make query-file FILE=<path>" && exit 1)
	@uv run python scripts/code_intel.py file "$(FILE)"
