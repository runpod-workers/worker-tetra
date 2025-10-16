# System Python Runtime Architecture

## Overview

This design addresses full use of PyTorch installation built into the base Docker image that we use for the runtime.

**Module Structure**: The core implementation resides in the `src/live_serverless/` module. The `src/handler.py` file serves as a lightweight RunPod wrapper that imports and starts the handler from `live_serverless`.

## Architecture Design

### System Python Runtime

```mermaid
graph TD
    A[RunPod Request] --> B[src/handler.py]
    B --> C[live_serverless module]
    C --> D[RemoteExecutor]
    D --> E[Environment Detection]
    E --> F{Docker?}
    F -->|Yes| G[System UV Install]
    F -->|No| H[Local UV Install]
    G --> I[Function Execution]
    H --> I

    J[DependencyInstaller] --> D
    K[FunctionExecutor] --> D
```

## Key Points


### Dependency Installation Strategy

```mermaid
flowchart LR
    A[Dependencies Required] --> B{Environment Check}
    B -->|Docker| C[uv pip install --system]
    B -->|Local| D[uv pip install]
    C --> E[Direct System Installation]
    D --> F[Managed Environment Installation]
```

### Component Architecture

```mermaid
graph TB
    A[handler.py] --> B[RemoteExecutor]
    B --> D[DependencyInstaller]
    B --> E[FunctionExecutor]
    B --> F[ClassExecutor]

    G[subprocess_utils] --> D
    G --> E
    G --> F

    I[serialization_utils] --> E
    I --> F
```

## Benefits

### Improved Reliability
- **Environment detection** handles Docker vs local contexts
- **Centralized subprocess handling** through `run_logged_subprocess`
- **Consistent error handling** via `FunctionResponse` pattern

### Performance Optimizations
- **Faster cold starts** without venv initialization
- **Reduced container size** from simplified builds
- **Direct package access** eliminates the re-downloading torch and other built-in libraries

## Implementation Details

### System Installation Strategy
```python
# Docker environment
command = ["uv", "pip", "install", "--system"] + packages

# Local environment
command = ["uv", "pip", "install", "--python-preference=managed"] + packages
```

This architecture refactor addresses the core PyTorch installation issues while maintaining API compatibility and improving operational simplicity.
