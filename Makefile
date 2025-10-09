IMAGE = runpod/tetra-rp
TAG = $(or $(TETRA_IMAGE_TAG),local)
FULL_IMAGE = $(IMAGE):$(TAG)
FULL_IMAGE_CPU = $(IMAGE)-cpu:$(TAG)

.PHONY: setup help

# Check if 'uv' is installed
ifeq (, $(shell which uv))
$(error "uv is not installed. Please install it before running this Makefile.")
endif

# Default target - show available commands
help: # Show this help menu
	@echo "Available make commands:"
	@echo ""
	@awk 'BEGIN {FS = ":.*# "; printf "%-20s %s\n", "Target", "Description"} /^[a-zA-Z_-]+:.*# / {printf "%-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)
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

setup: dev # Initialize project, sync deps, update submodules
	git submodule update --init --recursive
	cp tetra-rp/src/tetra_rp/protos/remote_execution.py src/

build: # Build both GPU and CPU Docker images
	make build-gpu
	make build-cpu

build-gpu: setup # Build GPU Docker image (linux/amd64)
	docker buildx build \
	--platform linux/amd64 \
	-t $(FULL_IMAGE) \
	. --load

build-cpu: setup # Build CPU-only Docker image (linux/amd64)
	docker buildx build \
	--platform linux/amd64 \
	-f Dockerfile-cpu \
	-t $(FULL_IMAGE_CPU) \
	. --load

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

# Smoke Tests (local on Mac OS)

smoketest-macos-build: setup # Build Mac OS Docker image (macos/arm64)
	docker buildx build \
	--platform linux/arm64 \
	-f Dockerfile \
	-t $(FULL_IMAGE)-mac \
	. --load

smoketest-macos: smoketest-macos-build # Test Docker image locally
	docker run --rm $(FULL_IMAGE)-mac ./test-handler.sh

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
