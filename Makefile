IMAGE = runpod/tetra-rp
TAG = local
FULL_IMAGE = $(IMAGE):$(TAG)
FULL_IMAGE_CPU = $(IMAGE)-cpu:$(TAG)

.PHONY: setup

# Check if 'uv' is installed
ifeq (, $(shell which uv))
$(error "uv is not installed. Please install it before running this Makefile.")
endif

dev:
	uv sync --all-groups

clean:
	rm -rf dist build *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pkl" -delete

upgrade:
	uv sync --upgrade

setup: dev
	git submodule init
	git submodule update --remote --merge
	cp tetra-rp/src/tetra_rp/protos/remote_execution.py .

build: setup
	docker buildx build \
	--no-cache \
	--platform linux/amd64 \
	-t $(FULL_IMAGE) \
	. --load

build-cpu: setup
	docker buildx build \
	--no-cache \
	--platform linux/amd64 \
	-f Dockerfile-cpu \
	-t $(FULL_IMAGE_CPU) \
	. --load

# Test commands
test:
	uv run pytest tests/ -v

test-unit:
	uv run pytest tests/unit/ -v -m "not integration"

test-integration:
	uv run pytest tests/integration/ -v -m integration

test-coverage:
	uv run pytest tests/ -v --cov=handler --cov=remote_execution --cov-report=term-missing

test-fast:
	uv run pytest tests/ -v -x --tb=short

# Linting commands
lint:
	uv run ruff check .

lint-fix:
	uv run ruff check . --fix

format:
	uv run ruff format .

format-check:
	uv run ruff format --check .

# Quality gates (used in CI)
quality-check: format-check lint test-coverage
