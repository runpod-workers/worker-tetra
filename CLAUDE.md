# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is `worker-flash`, a RunPod Serverless worker template that provides dynamic GPU provisioning for ML workloads with transparent execution and persistent workspace management. The project consists of two main components:

1. **RunPod Worker Handler** (`src/handler.py`) - A serverless function that executes remote Python functions with dependency management and workspace support
2. **Flash SDK** (pip dependency) - Python library for distributed inference and serving of ML models

## Key Areas of Responsibility

### 1. Remote Function Execution Engine (`src/`)
- **Core Handler** (`src/handler.py:18`): Main RunPod serverless entry point that orchestrates remote execution
- **Remote Executor** (`src/remote_executor.py:11`): Central orchestrator that coordinates all execution components using composition pattern
- **Function Executor** (`src/function_executor.py:12`): Handles individual function execution with full output capture (stdout, stderr, logs)
- **Class Executor** (`src/class_executor.py:14`): Manages class instantiation and method execution with instance persistence and metadata tracking

### 2. Dependency Management System (`src/dependency_installer.py:14`)
- **Python Package Installation**: UV-based package management with environment-aware configuration (Docker vs local)
- **System Package Installation**: APT/Nala-based system dependency handling with acceleration support
- **Differential Installation**: Optimized package installation that skips already-installed packages
- **Environment Detection**: Automatic Docker vs local environment detection for appropriate installation methods
- **System Package Filtering**: Intelligent detection of system-available packages to avoid redundant installation
- **Universal Subprocess Integration**: All subprocess operations use centralized logging utility

### 3. Universal Subprocess Utility (`src/subprocess_utils.py`)
- **Centralized Subprocess Operations**: All subprocess calls use `run_logged_subprocess` for consistency
- **Automatic Logging Integration**: All subprocess output flows through log streamer at DEBUG level
- **Environment-Aware Execution**: Handles Docker vs local environment differences automatically
- **Standardized Error Handling**: Consistent FunctionResponse pattern for all subprocess operations
- **Timeout Management**: Configurable timeouts with proper cleanup on timeout/cancellation

### 4. Serialization & Protocol Management
- **Protocol Definitions** (`runpod_flash.protos.remote_execution`): Pydantic models for request/response with validation
- **Serialization Utils** (`src/serialization_utils.py`): CloudPickle-based data serialization for function arguments and results
- **Base Executor** (`src/base_executor.py`): Common execution interface and environment setup

### 5. Flash SDK Integration (pip dependency)
- **Installation**: Installed via pip from GitHub repository
- **Client Interface**: `@remote` decorator for marking functions for remote execution
- **Resource Management**: GPU/CPU configuration and provisioning through LiveServerless objects
- **Live Serverless**: Dynamic infrastructure provisioning with auto-scaling
- **Repository**: https://github.com/runpod/flash

### 6. Testing Infrastructure (`tests/`)
- **Unit Tests** (`tests/unit/`): Component-level testing for individual modules with mocking
- **Integration Tests** (`tests/integration/`): End-to-end workflow testing with real execution
- **Test Fixtures** (`tests/conftest.py:1`): Shared test data, mock objects, and utility functions
- **Handler Testing**: Local execution validation with JSON test files (`src/tests/`)
  - **Full Coverage**: All handler tests pass with environment-aware dependency installation
  - **Cross-Platform**: Works correctly in both Docker containers and local macOS/Linux environments

### 7. Build & Deployment Pipeline
- **Docker Containerization**: GPU (`Dockerfile`) and CPU (`Dockerfile-cpu`) image builds
- **CI/CD Pipeline**: Automated testing, linting, and releases (`.github/workflows/`)
- **Quality Gates** (`Makefile:104`): Format checking, type checking, test coverage requirements
- **Release Management**: Automated semantic versioning and Docker Hub deployment

### 8. Configuration & Constants
- **Constants** (`src/constants.py`): System-wide configuration values (NAMESPACE, LARGE_SYSTEM_PACKAGES)
- **Environment Configuration**: RunPod API integration

## Architecture

### Core Components

- **`src/handler.py`**: Main RunPod serverless handler implementing composition pattern
  - Executes arbitrary Python functions remotely with workspace support
  - Handles dynamic installation of Python and system dependencies with differential updates
  - Serializes/deserializes function arguments and results using cloudpickle
  - Captures stdout, stderr, and logs from remote execution

- **`runpod_flash.protos.remote_execution`**: Protocol definitions from runpod-flash
  - `FunctionRequest`: Defines function execution requests with dependencies
  - `FunctionResponse`: Standardized response format with success/error handling
  - Imported from installed runpod-flash package via `from runpod_flash.protos.remote_execution import ...`

### Key Patterns

1. **Remote Function Execution**: Functions decorated with `@remote` are automatically executed on RunPod GPU workers
2. **Composition Pattern**: RemoteExecutor uses specialized components (DependencyInstaller, Executors)
3. **Dynamic Dependency Management**: Dependencies specified in decorators are installed at runtime with differential updates
4. **Universal Subprocess Operations**: All subprocess calls use centralized `run_logged_subprocess` for consistent logging and error handling
5. **Environment-Aware Configuration**: Automatic Docker vs local environment detection for appropriate installation methods
6. **Serialization**: Uses cloudpickle + base64 encoding for function arguments and results
7. **Resource Configuration**: `LiveServerless` objects define GPU requirements, scaling, and worker configuration

## Code Intelligence with MCP

This project has a worker-flash-code-intel MCP server configured for efficient codebase exploration. The code intelligence index includes both project source code and the runpod_flash dependency.

### Indexed Codebase

The following are automatically indexed and searchable via MCP tools:
- **Project source** (`src/`) - All 83 worker-flash symbols
- **runpod_flash dependency** - All 552 protocol definitions, resources, and core components
  - Protocol definitions: `runpod_flash.protos.remote_execution` (`FunctionRequest`, `FunctionResponse`, etc.)
  - Resources: `runpod_flash.core.resources` (`LiveServerless`, `Serverless`, `NetworkVolume`, etc.)
  - Stubs: `runpod_flash.stubs` (stub implementations for local development)

To regenerate the index (when dependencies change), run: `make index`

To add more dependencies to the index, edit `DEPENDENCIES_TO_INDEX` in `scripts/ast_to_sqlite.py`.

### MCP Tools for Code Intelligence

**Always prefer these MCP tools over Grep/Glob for semantic code searches:**

- **`find_symbol(symbol)`** - Find classes, functions, methods by name (supports partial matches)
  - Example: Finding `RemoteExecutor` class, `FunctionRequest` protocol, or `handler` function
  - Use instead of: `grep -r "class RemoteExecutor"` or `glob "**/*.py"`

- **`list_classes()`** - Get all classes in codebase
  - Use instead of: `grep -r "^class "`

- **`get_class_interface(class_name)`** - Get class methods without implementations
  - Example: `get_class_interface("DependencyInstaller")` to see available methods
  - Example: `get_class_interface("FunctionRequest")` to see protocol fields
  - Use instead of: Reading full file and parsing manually

- **`list_file_symbols(file_path)`** - List all symbols (classes, functions) in a specific file
  - Use instead of: `grep` on individual files for symbol discovery

- **`find_by_decorator(decorator)`** - Find functions/classes with specific decorators
  - Example: `find_by_decorator("remote")` to find all @remote decorated functions
  - Use instead of: `grep -r "@remote"`

### Tool Selection Guidelines

**When to use MCP vs Grep/Glob:**
- **MCP tools**: Semantic searches (class names, function definitions, decorators, symbols) - including runpod_flash
- **Grep**: Content searches (error messages, comments, string literals, log statements)
- **Glob**: File path patterns when you know the exact file structure
- **Task tool with Explore agent**: Complex multi-step exploration requiring multiple searches

**Example workflow:**
- "Find all @remote functions" → use `find_by_decorator("remote")`
- "Where is RemoteExecutor defined" → use `find_symbol("RemoteExecutor")`
- "What fields does FunctionRequest protocol have" → use `get_class_interface("FunctionRequest")`
- "Where is LiveServerless used" → use `find_symbol("LiveServerless")`
- "Where is error 'API timeout' logged" → use Grep
- "Find all test_*.json files" → use Glob

## Development Commands

### Setup and Dependencies
```bash
make setup                    # Initialize project and sync dependencies
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

### Testing Commands
```bash
make test                     # Run all tests
make test-unit               # Run unit tests only
make test-integration        # Run integration tests only
make test-coverage           # Run tests with coverage report
make test-fast               # Run tests with fail-fast mode
make test-handler            # Test handler locally with all test_*.json files (same as CI)
```

### Docker Operations
```bash
make build                    # Build GPU Docker image (linux/amd64)
make build-cpu               # Build CPU-only Docker image
# Note: Docker push is automated via GitHub Actions on release
```

## Configuration

### Environment Variables
- `RUNPOD_API_KEY`: Required for RunPod Serverless integration
- `RUNPOD_ENDPOINT_ID`: Used for workspace isolation (automatically set by RunPod)
- `HF_HUB_ENABLE_HF_TRANSFER`: Set to "1" in Dockerfile to enable accelerated HuggingFace downloads
- `HF_TOKEN`: Optional authentication token for private/gated HuggingFace models
- `HF_HOME=/hf-cache`: HuggingFace cache location, set outside `/root/.cache` to exclude from volume sync
- `DEBIAN_FRONTEND=noninteractive`: Set during system package installation

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

### Testing Framework
- **pytest** with coverage reporting and async support
- **Unit tests** (`tests/unit/`): Test individual components in isolation
- **Integration tests** (`tests/integration/`): Test end-to-end workflows
- **Coverage target**: 35% minimum, with HTML and XML reports
- **Test fixtures**: Shared test data and mocks in `tests/conftest.py`
- **CI Integration**: Tests run on all PRs and before releases/deployments

## Development Notes

### Dependency Management
- Root project uses `uv` with `pyproject.toml`
- Runpod Flash SDK installed as pip dependency from GitHub repository
- System dependencies installed via `apt-get` in containerized environment
- Python dependencies installed via `uv pip install` at runtime
- **Differential Installation**: Only installs packages missing from environment
- **Environment Awareness**: Uses appropriate python preferences (Docker: `--python-preference=only-system`, Local: managed python)

### Error Handling
- All remote execution wrapped in try/catch with full traceback capture
- Structured error responses via `FunctionResponse.error`
- Combined stdout/stderr/log capture for debugging

### Security Considerations
- Functions execute arbitrary Python code in sandboxed containers
- System package installation requires root privileges in container
- No secrets should be committed to repository
- API keys passed via environment variables

## File Structure Highlights

```
├── src/                       # Core implementation
│   ├── handler.py            # Main serverless function handler
│   ├── remote_executor.py    # Central execution orchestrator
│   ├── function_executor.py  # Function execution with output capture
│   ├── class_executor.py     # Class execution with persistence
│   ├── dependency_installer.py # Python and system dependency management
│   ├── serialization_utils.py # CloudPickle serialization utilities
│   ├── base_executor.py      # Common execution interface
│   ├── constants.py          # System-wide configuration constants
│   └── tests/                # Handler test JSON files
├── tests/                    # Comprehensive test suite
│   ├── conftest.py          # Shared test fixtures
│   ├── unit/                # Unit tests for individual components
│   └── integration/         # End-to-end integration tests
├── Dockerfile               # GPU container definition
├── Dockerfile-cpu          # CPU container definition
└── Makefile                # Development commands and quality gates
```

## CI/CD and Release Process

### Automated Releases
- Uses `release-please` for automated semantic versioning and changelog generation
- Releases are triggered by conventional commit messages on `main` branch
- Docker images are automatically built and pushed to Docker Hub (`runpod/flash`) on release

### GitHub Actions Workflows
- **CI/CD** (`.github/workflows/ci.yml`): Single workflow handling tests, linting, releases, and Docker builds
  - Runs tests and linting on PRs and pushes to main
  - **Local execution testing**: Automatically tests all `test_*.json` files in src directory to validate handler functionality
  - Manages releases via `release-please` on main branch
  - Builds and pushes `:main` tagged images on main branch pushes
  - Builds and pushes production images with semantic versioning on releases
  - Supports manual triggering via `workflow_dispatch` for ad-hoc runs

### Required Secrets
Configure these in GitHub repository settings:
- `DOCKERHUB_USERNAME`: Docker Hub username
- `DOCKERHUB_TOKEN`: Docker Hub password or access token

## Branch Information
- Main branch: `main`
- Current branch: `tmp/deployed-execution`

## Development Best Practices

- Always run `make quality-check` before committing changes
- Always use `git mv` when moving existing files around
- Run `make test-handler` to validate handler functionality with test files
- Never create files unless absolutely necessary for achieving goals
- Always prefer editing existing files to creating new ones
- Never proactively create documentation files unless explicitly requested

## Project Memories

### Docker Guidelines
- Docker container should never refer to src/

### Testing Guidelines
- Use `make test-handler` to run checks on test files
- Do not run individual test files manually like `Bash(env RUNPOD_TEST_INPUT="$(cat test_input.json)" PYTHONPATH=. uv run python handler.py)`

### File Management
- Use `git mv` when moving existing files
- Prefer editing existing files over creating new ones
- Only create files when absolutely necessary
