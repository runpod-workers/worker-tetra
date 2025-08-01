# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is `worker-tetra`, a RunPod Serverless worker template that provides dynamic GPU provisioning for ML workloads with transparent execution and persistent workspace management. The project consists of two main components:

1. **RunPod Worker Handler** (`handler.py`) - A serverless function that executes remote Python functions with dependency management and persistent volume workspace support
2. **Tetra SDK** (`tetra-rp/` submodule) - Python library for distributed inference and serving of ML models

## Architecture

### Core Components

- **`handler.py`**: Main RunPod serverless handler implementing `RemoteExecutor` class
  - Executes arbitrary Python functions remotely with persistent workspace support
  - Handles dynamic installation of Python and system dependencies with differential updates
  - Manages `/runpod-volume` workspace with virtual environment and shared package cache
  - Implements concurrency-safe workspace initialization with file-based locking
  - Serializes/deserializes function arguments and results using cloudpickle
  - Captures stdout, stderr, and logs from remote execution

- **`remote_execution.py`**: Protocol definitions using Pydantic models
  - `FunctionRequest`: Defines function execution requests with dependencies
  - `FunctionResponse`: Standardized response format with success/error handling

- **`tetra-rp/`**: Git submodule containing the Tetra SDK
  - `client.py`: `@remote` decorator for marking functions for remote execution
  - `core/resources/`: Resource management for serverless endpoints
  - `core/pool/`: Worker pool and cluster management
  - Auto-provisions RunPod Serverless infrastructure

### Key Patterns

1. **Remote Function Execution**: Functions decorated with `@remote` are automatically executed on RunPod GPU workers
2. **Persistent Workspace Management**: `/runpod-volume` provides persistent storage for packages and execution state
3. **Dynamic Dependency Management**: Dependencies specified in decorators are installed at runtime with differential updates
4. **Concurrency Safety**: File-based locking ensures safe workspace initialization across multiple workers
5. **Serialization**: Uses cloudpickle + base64 encoding for function arguments and results
6. **Resource Configuration**: `LiveServerless` objects define GPU requirements, scaling, and worker configuration

## Development Commands

### Setup and Dependencies
```bash
make setup                    # Initialize project, sync dependencies, update submodules
make dev                      # Install all development dependencies (includes pytest, ruff)
uv sync                      # Sync production dependencies only
uv sync --all-groups         # Sync all dependency groups (same as make dev)
```

### Code Quality
```bash
make lint                     # Check code with ruff linter
make lint-fix                # Auto-fix linting issues
make format                   # Format code with ruff
make format-check            # Check if code is properly formatted
make quality-check           # Run all quality checks (format, lint, test coverage)
```

### Docker Operations
```bash
make build                    # Build GPU Docker image (linux/amd64)
make build-cpu               # Build CPU-only Docker image
# Note: Docker push is automated via GitHub Actions on release
```

### Local Testing  
```bash
python handler.py            # Test handler locally with test_input.json
```

### Submodule Management
```bash
git submodule update --remote --merge    # Update tetra-rp to latest
```

## RunPod Volume Workspace

The handler automatically detects and utilizes `/runpod-volume` for persistent workspace management when available:

### Volume Features
- **Automatic Detection**: Detects `/runpod-volume` presence on container startup
- **Virtual Environment**: Creates and manages `.venv` in the volume for persistent package installation
- **Shared Package Cache**: Uses `/runpod-volume/.uv-cache` for efficient package caching across workers
- **Differential Installation**: Only installs missing packages, leveraging persistent storage
- **Concurrency Safety**: File-based locking prevents race conditions during workspace initialization
- **Graceful Fallback**: Works normally when no volume is present

### Volume Structure
```
/runpod-volume/
├── .venv/                    # Persistent virtual environment
│   ├── bin/
│   ├── lib/python3.12/
│   └── site-packages/
├── .uv-cache/               # Shared UV package cache
├── .initialization.lock     # Temporary workspace lock file
└── <function execution workspace>
```

### Performance Benefits
- **Faster Cold Starts**: Pre-installed packages reduce initialization time
- **Reduced Network Usage**: Cached packages avoid redundant downloads
- **Persistent State**: Function execution workspace survives across calls
- **Optimized Resource Usage**: Shared cache across multiple workers

## Configuration

### Environment Variables
- `RUNPOD_API_KEY`: Required for RunPod Serverless integration
- `DEBIAN_FRONTEND=noninteractive`: Set during system package installation
- `UV_CACHE_DIR`: Automatically set to `/runpod-volume/.uv-cache` when volume detected
- `VIRTUAL_ENV`: Automatically set to `/runpod-volume/.venv` when available

### Resource Configuration
Configure GPU resources using `LiveServerless` objects:
```python
gpu_config = LiveServerless(
    name="my-endpoint",           # Endpoint name (required)
    gpus=[GpuGroup.ANY],         # GPU types
    workersMax=5,                # Max concurrent workers
    workersMin=0,                # Min workers (0 = scale to zero)
    idleTimeout=5,               # Minutes before scaling down
    executionTimeoutMs=600000,   # Max execution time
)
```

## Testing and Quality

### Testing Commands
```bash
make test                     # Run all tests
make test-unit               # Run unit tests only
make test-integration        # Run integration tests only
make test-coverage           # Run tests with coverage report
make test-fast               # Run tests with fail-fast mode
python handler.py            # Test handler locally with test_input.json
```

### Testing Framework
- **pytest** with coverage reporting and async support
- **Unit tests** (`tests/unit/`): Test individual components in isolation
- **Integration tests** (`tests/integration/`): Test end-to-end workflows
- **Coverage target**: 80% minimum, with HTML and XML reports
- **Test fixtures**: Shared test data and mocks in `tests/conftest.py`
- **CI Integration**: Tests run on all PRs and before releases/deployments

## Development Notes

### Dependency Management
- Root project uses `uv` with `pyproject.toml`
- Tetra SDK has separate `pyproject.toml` in `tetra-rp/`
- System dependencies installed via `apt-get` in containerized environment
- Python dependencies installed via `uv pip install` at runtime with volume persistence
- **Differential Installation**: Only installs packages missing from persistent volume
- **Shared Cache**: UV cache in `/runpod-volume/.uv-cache` optimizes package downloads
- **Virtual Environment**: Persistent `.venv` in volume survives across function calls

### Error Handling
- All remote execution wrapped in try/catch with full traceback capture
- Structured error responses via `FunctionResponse.error`
- Combined stdout/stderr/log capture for debugging

### Security Considerations
- Functions execute arbitrary Python code in sandboxed containers
- System package installation requires root privileges in container
- Volume workspace provides persistent storage but maintains container isolation
- File-based locking prevents race conditions during concurrent workspace access
- No secrets should be committed to repository
- API keys passed via environment variables

## File Structure Highlights

```
├── handler.py              # Main serverless function handler with volume support
├── remote_execution.py     # Protocol definitions
├── PLAN.md                # TDD implementation plan for volume workspace
├── Dockerfile             # GPU container definition  
├── Dockerfile-cpu         # CPU container definition
├── test_input.json        # Sample input for local testing
├── tests/                 # Comprehensive test suite
│   ├── conftest.py        # Shared test fixtures
│   ├── unit/              # Unit tests for individual components
│   │   ├── test_runpod_volume_workspace.py  # Volume detection and initialization
│   │   ├── test_volume_execution.py         # Volume-aware execution
│   │   └── test_*.py      # Other unit tests
│   └── integration/       # End-to-end integration tests
│       ├── test_runpod_volume_integration.py # Volume workflow tests
│       └── test_*.py      # Other integration tests
├── tetra-rp/              # Git submodule - Tetra SDK
│   ├── src/tetra_rp/
│   │   ├── client.py      # @remote decorator
│   │   ├── core/          # Resource and pool management
│   │   └── protos/        # Protocol buffer definitions
│   └── tetra-examples/    # Usage examples
```

## CI/CD and Release Process

### Automated Releases
- Uses `release-please` for automated semantic versioning and changelog generation
- Releases are triggered by conventional commit messages on `main` branch
- Docker images are automatically built and pushed to Docker Hub (`runpod/tetra-rp`) on release

### GitHub Actions Workflows
- **CI/CD** (`.github/workflows/ci.yml`): Single workflow handling tests, linting, releases, and Docker builds
  - Runs tests and linting on PRs and pushes to main
  - Manages releases via `release-please` on main branch
  - Builds and pushes `:dev` tagged images on main branch pushes
  - Builds and pushes production images with semantic versioning on releases
- **Deploy** (`.github/workflows/deploy.yml`): Manual deployment workflow for custom Docker tags and emergency deployments

### Required Secrets
Configure these in GitHub repository settings:
- `DOCKERHUB_USERNAME`: Docker Hub username
- `DOCKERHUB_TOKEN`: Docker Hub password or access token

## Branch Information
- Main branch: `main`
- Submodule tracking: Updates pulled from remote automatically during setup