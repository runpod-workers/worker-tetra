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
# Test handler locally with test_input.json
PYTHONPATH=src RUNPOD_TEST_INPUT="$(cat test_input.json)" uv run python src/handler.py

# Test with other test files
PYTHONPATH=src RUNPOD_TEST_INPUT="$(cat test_class_input.json)" uv run python src/handler.py
PYTHONPATH=src RUNPOD_TEST_INPUT="$(cat test_hf_input.json)" uv run python src/handler.py
```

### Submodule Management
```bash
git submodule update --remote --merge    # Update tetra-rp to latest
```

## RunPod Volume Workspace

The handler automatically detects and utilizes `/runpod-volume` for persistent workspace management when available:

### Volume Features
- **Automatic Detection**: Detects `/runpod-volume` presence on container startup
- **Endpoint Isolation**: Each endpoint gets its own workspace at `/runpod-volume/runtimes/{endpoint_id}`
- **Virtual Environment**: Creates and manages endpoint-specific `.venv` for persistent package installation
- **Shared Package Cache**: Uses `/runpod-volume/.uv-cache` for efficient package caching across all endpoints
- **Hugging Face Cache**: Configures HF model cache at `/runpod-volume/.hf-cache` to prevent storage issues
- **Differential Installation**: Only installs missing packages, leveraging persistent storage
- **Enhanced Concurrency Safety**: Advanced file-based locking with proper file descriptor management prevents race conditions during workspace initialization
- **Configurable Timeouts**: Workspace initialization timeout and polling intervals are configurable via constants
- **Atomic Operations**: Workspace functionality checks are atomic to prevent race conditions
- **Comprehensive Error Handling**: Robust error recovery and cleanup mechanisms for various failure scenarios
- **Graceful Fallback**: Works normally when no volume is present

### Volume Structure
```
/runpod-volume/
├── .uv-cache/               # Shared UV package cache (across all endpoints)
├── .hf-cache/               # Shared Hugging Face model cache (across all endpoints)
│   ├── transformers/        # Transformers model cache
│   ├── datasets/            # HF datasets cache
│   └── hub/                 # Hugging Face Hub cache
├── runtimes/                # Per-endpoint runtime environments
│   ├── endpoint-1/          # Workspace for endpoint-1
│   │   ├── .venv/           # Endpoint-specific virtual environment
│   │   ├── .initialization.lock  # Temporary workspace lock file
│   │   └── <execution workspace>
│   └── endpoint-2/          # Workspace for endpoint-2
│       ├── .venv/           # Endpoint-specific virtual environment
│       ├── .initialization.lock
│       └── <execution workspace>
```

### Performance Benefits
- **Faster Cold Starts**: Pre-installed packages and cached models reduce initialization time
- **Reduced Network Usage**: Cached packages and models avoid redundant downloads
- **Persistent State**: Function execution workspace survives across calls
- **Endpoint Isolation**: Each endpoint maintains independent dependencies and state
- **Optimized Resource Usage**: Shared caches across multiple endpoints while maintaining isolation
- **ML Model Efficiency**: Large HF models cached on volume prevent "No space left on device" errors

### Concurrency Safety Enhancements

The workspace initialization system has been enhanced with advanced concurrency safety features:

#### Lock Management
- **File Descriptor-Based Locking**: Uses `os.open()` and `fcntl.flock()` for reliable cross-process locking
- **Proper Resource Cleanup**: Ensures file descriptors are always closed, even on exceptions
- **Lock Timeout Handling**: Configurable timeout with graceful fallback when locks cannot be acquired
- **Atomic Lock Operations**: Lock acquisition and workspace validation are performed atomically

#### Workspace Validation
- **Directory Access Validation**: Verifies workspace directory is writable before attempting initialization
- **Virtual Environment Validation**: Checks that virtual environments are functional, not just present
- **Automatic Recovery**: Detects and recreates broken virtual environments
- **Race Condition Prevention**: Workspace functionality checks are atomic and thread-safe

#### Configuration Constants
- `WORKSPACE_INIT_TIMEOUT`: Default timeout (30 seconds) for workspace initialization
- `WORKSPACE_LOCK_POLL_INTERVAL`: Polling interval (0.5 seconds) during lock wait periods

#### Error Handling
- **Comprehensive Error Recovery**: Handles various failure scenarios with appropriate fallback behavior
- **Descriptive Error Messages**: Provides clear error context for debugging
- **Silent Cleanup**: Lock file cleanup failures are logged but don't fail the operation
- **Performance Monitoring**: Tracks lock acquisition success rates and timeout scenarios

## Configuration

### Environment Variables
- `RUNPOD_API_KEY`: Required for RunPod Serverless integration
- `RUNPOD_ENDPOINT_ID`: Used for workspace isolation (automatically set by RunPod)
- `DEBIAN_FRONTEND=noninteractive`: Set during system package installation
- `UV_CACHE_DIR`: Automatically set to `/runpod-volume/.uv-cache` when volume detected
- `VIRTUAL_ENV`: Automatically set to `/runpod-volume/runtimes/{endpoint_id}/.venv` when available

#### Hugging Face Cache Configuration (Auto-configured when volume available)
- `HF_HOME`: Set to `/runpod-volume/.hf-cache` for main HF cache directory
- `TRANSFORMERS_CACHE`: Set to `/runpod-volume/.hf-cache/transformers` for model cache
- `HF_DATASETS_CACHE`: Set to `/runpod-volume/.hf-cache/datasets` for dataset cache
- `HUGGINGFACE_HUB_CACHE`: Set to `/runpod-volume/.hf-cache/hub` for hub cache

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
make test-handler            # Test handler locally with all test_*.json files (same as CI)

# Test handler locally with specific test files
PYTHONPATH=src RUNPOD_TEST_INPUT="$(cat test_input.json)" uv run python src/handler.py
PYTHONPATH=src RUNPOD_TEST_INPUT="$(cat test_class_input.json)" uv run python src/handler.py
PYTHONPATH=src RUNPOD_TEST_INPUT="$(cat test_hf_input.json)" uv run python src/handler.py
```

### Testing Framework
- **pytest** with coverage reporting and async support
- **Unit tests** (`tests/unit/`): Test individual components in isolation
- **Integration tests** (`tests/integration/`): Test end-to-end workflows
- **Concurrency tests**: Comprehensive testing of workspace initialization under concurrent access
- **Coverage target**: 80% minimum, with HTML and XML reports (currently achieving 85%+)
- **Test fixtures**: Shared test data and mocks in `tests/conftest.py`
- **CI Integration**: Tests run on all PRs and before releases/deployments

#### Concurrency Test Coverage
- **Lock timeout scenarios**: Validates proper timeout handling and error messages
- **File descriptor cleanup**: Ensures resources are properly released on errors
- **Race condition handling**: Tests concurrent workspace initialization attempts
- **Directory validation**: Tests workspace access permission scenarios
- **Edge case handling**: Validates behavior under various failure conditions

## Development Notes

### Dependency Management
- Root project uses `uv` with `pyproject.toml`
- Tetra SDK has separate `pyproject.toml` in `tetra-rp/`
- System dependencies installed via `apt-get` in containerized environment
- Python dependencies installed via `uv pip install` at runtime with volume persistence
- **Differential Installation**: Only installs packages missing from persistent volume
- **Shared Cache**: UV cache in `/runpod-volume/.uv-cache` optimizes package downloads
- **Virtual Environment**: Persistent `.venv` in volume survives across function calls
- **ML Model Cache**: Hugging Face models cached in `/runpod-volume/.hf-cache` prevent storage issues

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
├── src/                    # Source code directory
│   ├── handler.py          # Main serverless function handler entry point
│   ├── remote_execution.py # Protocol definitions using Pydantic models
│   ├── remote_executor.py  # Main execution orchestrator
│   ├── workspace_manager.py # Enhanced workspace management with concurrency safety
│   ├── function_executor.py # Function execution with output capture
│   ├── class_executor.py   # Class instantiation and method execution
│   ├── dependency_installer.py # System and Python dependency management
│   ├── serialization_utils.py  # Argument and result serialization utilities
│   └── constants.py        # Configuration constants including concurrency settings
├── PLAN.md                # Implementation plan for stdout feedback enhancements
├── Dockerfile             # GPU container definition  
├── Dockerfile-cpu         # CPU container definition
├── test_input.json        # Basic function execution test
├── test_class_input.json   # Class execution test
├── test_hf_input.json      # HuggingFace model download test
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
  - **Local execution testing**: Automatically tests all `test_*.json` files in root directory to validate handler functionality
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

## Development Best Practices

- Always run `make quality-check` before committing changes