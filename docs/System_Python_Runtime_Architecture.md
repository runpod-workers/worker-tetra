# System Python Runtime Architecture

## Overview

This design addresses full use of PyTorch installation built into the base Docker image that we use for the runtime.

## Architecture Design

### System Python Runtime

```mermaid
graph TD
    A[RunPod Request] --> B[src/handler.py]
    B --> C[RemoteExecutor]
    C --> D[Environment Detection]
    D --> E{Docker?}
    E -->|Yes| F[System UV Install]
    E -->|No| G[Local UV Install]
    F --> H[Function Execution]
    G --> H

    J[DependencyInstaller] --> C
    K[FunctionExecutor] --> C
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
command = ["uv", "pip", "install", "--system", "--no-cache"] + packages

# Local environment
command = ["uv", "pip", "install", "--python-preference=managed"] + packages
```

This architecture refactor addresses the core PyTorch installation issues while maintaining API compatibility and improving operational simplicity.
