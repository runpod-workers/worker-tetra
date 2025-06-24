# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is `worker-tetra`, a RunPod Serverless worker template that provides dynamic GPU provisioning for ML workloads with transparent execution. The project consists of two main components:

1. **RunPod Worker Handler** (`handler.py`) - A serverless function that executes remote Python functions with dependency management
2. **Tetra SDK** (`tetra-rp/` submodule) - Python library for distributed inference and serving of ML models

## Architecture

### Core Components

- **`handler.py`**: Main RunPod serverless handler implementing `RemoteExecutor` class
  - Executes arbitrary Python functions remotely
  - Handles dynamic installation of Python and system dependencies
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
2. **Dynamic Dependency Management**: Dependencies specified in decorators are installed at runtime
3. **Serialization**: Uses cloudpickle + base64 encoding for function arguments and results
4. **Resource Configuration**: `LiveServerless` objects define GPU requirements, scaling, and worker configuration

## Development Commands

### Setup and Dependencies
```bash
make setup                    # Initialize project, sync dependencies, update submodules
make dev                      # Install all development dependencies
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

## Configuration

### Environment Variables
- `RUNPOD_API_KEY`: Required for RunPod Serverless integration
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

- No formal test suite currently exists
- Testing is done via `test_input.json` with local handler execution
- Uses `uv` for fast dependency management
- Multi-stage Docker builds to minimize image size

## Development Notes

### Dependency Management
- Root project uses `uv` with `pyproject.toml`
- Tetra SDK has separate `pyproject.toml` in `tetra-rp/`
- System dependencies installed via `apt-get` in containerized environment
- Python dependencies installed via `uv pip install` at runtime

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
├── handler.py              # Main serverless function handler
├── remote_execution.py     # Protocol definitions
├── Dockerfile             # GPU container definition  
├── Dockerfile-cpu         # CPU container definition
├── test_input.json        # Sample input for local testing
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
- **Release** (`.github/workflows/release-please.yml`): Manages releases and versioning
- **Docker Images [Prod]** (`.github/workflows/docker-prod.yml`): Builds and pushes Docker images on release
- **Docker Images [Dev]** (`.github/workflows/docker-dev.yml`): Builds and pushes `:dev` tagged images on main branch pushes

### Required Secrets
Configure these in GitHub repository settings:
- `DOCKERHUB_USERNAME`: Docker Hub username
- `DOCKERHUB_TOKEN`: Docker Hub password or access token

## Branch Information
- Main branch: `main`
- Current working branch: `dean/ae-518-cpu-live-serverless`
- Submodule tracking: Updates pulled from remote automatically during setup