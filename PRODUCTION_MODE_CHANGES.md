# Production Mode Changes in worker-tetra

This document summarizes the changes made to worker-tetra to support production mode with baked code execution.

## Files Changed

### 1. NEW: `src/baked_executor.py`

**Purpose:** Executes pre-installed (baked) code via Python imports instead of dynamic `exec()`.

**Key Features:**
- Loads registry from `/app/baked_code/registry.json`
- Imports callables from `baked_code.*` modules
- Caches loaded modules for performance
- Supports both functions and classes
- Maintains class instance cache

**Usage:**
```python
from baked_executor import BakedExecutor, is_baked_mode_enabled

if is_baked_mode_enabled():
    executor = BakedExecutor(workspace_manager)
    response = executor.execute(request)
```

### 2. MODIFIED: `src/remote_executor.py`

**Changes:**
1. Added `baked_executor` initialization
2. Added `_initialize_baked_executor()` method
3. Added `_should_use_baked_execution()` routing logic
4. Modified `ExecuteFunction()` to check for baked execution first

**Code Added:**
```python
# In __init__():
self.baked_executor: Optional[Any] = None
self._initialize_baked_executor()

def _initialize_baked_executor(self):
    """Initialize baked executor if running in production mode."""
    try:
        from baked_executor import BakedExecutor, is_baked_mode_enabled

        if is_baked_mode_enabled():
            self.baked_executor = BakedExecutor(self.workspace_manager)
            self.logger.info(
                "✅ Baked execution mode ENABLED - using pre-installed code"
            )
        else:
            self.logger.info(
                "ℹ️  Baked execution mode DISABLED - using dynamic code execution"
            )
    except ImportError:
        self.logger.debug(
            "BakedExecutor not available - running in development mode"
        )

async def ExecuteFunction(self, request: FunctionRequest) -> FunctionResponse:
    # Check if we should use baked execution
    if self._should_use_baked_execution(request):
        self.logger.info(
            f"Using baked execution for {getattr(request, 'function_name', None) or getattr(request, 'class_name', 'unknown')}"
        )
        return self.baked_executor.execute(request)

    # Standard dynamic execution flow continues...
```

### 3. MODIFIED: `src/remote_execution.py`

**Changes:**
1. Added `baked: bool` field to `FunctionRequest`
2. Updated validation to allow missing code when `baked=True`

**Code Added:**
```python
# In FunctionRequest class:

# Production mode field
baked: bool = Field(
    default=False,
    description="Use baked execution (production mode) - code is pre-installed in container",
)

@model_validator(mode="after")
def validate_execution_requirements(self) -> "FunctionRequest":
    """Validate that required fields are provided based on execution_type"""
    if self.execution_type == "function":
        if self.function_name is None:
            raise ValueError(
                'function_name is required when execution_type is "function"'
            )
        # In baked mode, function_code is optional (code is pre-installed)
        if not self.baked and self.function_code is None:
            raise ValueError(
                'function_code is required when execution_type is "function" and baked=False'
            )

    elif self.execution_type == "class":
        if self.class_name is None:
            raise ValueError(
                'class_name is required when execution_type is "class"'
            )
        # In baked mode, class_code is optional (code is pre-installed)
        if not self.baked and self.class_code is None:
            raise ValueError(
                'class_code is required when execution_type is "class" and baked=False'
            )

    return self
```

## Execution Flow

### Development Mode (TETRA_BAKED_MODE=false)
```
Request → remote_executor.ExecuteFunction()
              ↓
       _should_use_baked_execution() → False
              ↓
       function_executor.execute() or class_executor.execute()
              ↓
       exec(code) - Dynamic execution
```

### Production Mode (TETRA_BAKED_MODE=true)
```
Request → remote_executor.ExecuteFunction()
              ↓
       _should_use_baked_execution() → True
              ↓
       baked_executor.execute()
              ↓
       importlib.import_module("baked_code.module")
              ↓
       Execute via import (no exec!)
```

## Environment Variables

**`TETRA_BAKED_MODE`**
- Values: `true`, `false`, `1`, `0`, `yes`, `no`
- Default: `false`
- Purpose: Enable/disable baked execution mode
- Set in Dockerfile: `ENV TETRA_BAKED_MODE=true`

## Expected Directory Structure

When `TETRA_BAKED_MODE=true`, the container expects:

```
/app/
├── handler.py
├── remote_executor.py
├── baked_executor.py      ← NEW
├── function_executor.py
├── class_executor.py
├── ... (other worker files)
└── baked_code/            ← NEW (added in application layer)
    ├── __init__.py
    ├── registry.json
    ├── module1.py
    └── module2.py
```

**`/app/baked_code/registry.json` Example:**
```json
{
  "my_function": {
    "type": "function",
    "module": "baked_code.module1",
    "name": "my_function"
  },
  "MyClass": {
    "type": "class",
    "module": "baked_code.module2",
    "name": "MyClass"
  }
}
```

## Building Worker Base Image

```bash
cd /Users/marut/tetra/worker-tetra

# Build worker base image
docker build -t myregistry.io/tetra-worker:v1.0.0 -f Dockerfile .

# Push to registry
docker push myregistry.io/tetra-worker:v1.0.0
```

This image contains:
- ✅ All worker infrastructure
- ✅ `baked_executor.py` (NEW)
- ✅ Support for production mode
- ❌ No baked user code (added in application layer)

## Building Application Image

Application images extend the worker base:

```dockerfile
# Your application Dockerfile
FROM myregistry.io/tetra-worker:v1.0.0

# Copy baked code
COPY baked_code /app/baked_code

# Install application dependencies
RUN uv pip install --system transformers torch

# Enable production mode
ENV TETRA_BAKED_MODE=true

# CMD inherited from base image
```

## Testing

### Test Baked Mode Detection

```bash
# Start container with baked mode enabled
docker run -e TETRA_BAKED_MODE=true myregistry.io/tetra-worker:v1.0.0 \
  python -c "from baked_executor import is_baked_mode_enabled; print(is_baked_mode_enabled())"

# Output: True
```

### Test Baked Module Import

```bash
# Create test baked code
mkdir -p baked_code
cat > baked_code/registry.json << 'EOF'
{
  "test_func": {
    "type": "function",
    "module": "baked_code.test",
    "name": "test_func"
  }
}
EOF

cat > baked_code/test.py << 'EOF'
def test_func():
    return "Hello from baked code!"
EOF

# Build test image
cat > Dockerfile.test << 'EOF'
FROM myregistry.io/tetra-worker:v1.0.0
COPY baked_code /app/baked_code
ENV TETRA_BAKED_MODE=true
EOF

docker build -f Dockerfile.test -t test-baked .

# Test import
docker run test-baked python -c "from baked_code.test import test_func; print(test_func())"

# Output: Hello from baked code!
```

## Logging

When baked mode is enabled, you'll see:

```
INFO: ✅ Baked execution mode ENABLED - using pre-installed code
INFO: Initialized BakedExecutor with 5 registered callables
INFO: Using baked execution for my_function
INFO: Importing baked module: baked_code.my_module
INFO: Loaded baked callable: my_function from baked_code.my_module
INFO: Executing baked function: my_function
```

When disabled:

```
INFO: ℹ️  Baked execution mode DISABLED - using dynamic code execution
```

## Backward Compatibility

All changes are **100% backward compatible**:

- ✅ Development mode (dynamic execution) still works
- ✅ Existing code requires no changes
- ✅ Production mode is opt-in via environment variable
- ✅ Falls back gracefully if baked code not found

## Security

Production mode eliminates security risks:

| Aspect | Development Mode | Production Mode |
|--------|------------------|-----------------|
| Code transmission | Over HTTP | None (pre-installed) |
| Code execution | `exec()` | `import` |
| Arbitrary code | Possible | Impossible |
| Audit trail | None | Docker image + registry |

## Performance

Benefits of baked execution:

- ✅ **No code serialization** - Saves network bandwidth
- ✅ **No exec() overhead** - Native Python imports
- ✅ **Module caching** - Imported modules cached by Python
- ✅ **Instance persistence** - Class instances cached in memory

## Summary

**3 files changed:**
1. ✅ `src/baked_executor.py` (NEW) - 350 lines
2. ✅ `src/remote_executor.py` (MODIFIED) - Added ~100 lines
3. ✅ `src/remote_execution.py` (MODIFIED) - Added ~20 lines

**Key capabilities:**
- ✅ Import-based execution (secure)
- ✅ Automatic mode detection
- ✅ Backward compatible
- ✅ Instance caching for classes
- ✅ Module caching for performance

Ready for production deployment! 🚀
