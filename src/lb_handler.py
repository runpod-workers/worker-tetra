"""Load Balancer handler for executing remote functions via HTTP.

This handler provides a FastAPI application for the Load Balancer runtime.
It supports:
- /ping: Health check endpoint (required by RunPod Load Balancer)
- /execute: Remote function execution via HTTP POST (queue-based mode)
- User's FastAPI app routes (mothership mode)

The handler uses worker-tetra's RemoteExecutor for function execution.

Mothership Mode (FLASH_IS_MOTHERSHIP=true):
- Imports user's FastAPI application from FLASH_MAIN_FILE
- Loads the app object from FLASH_APP_VARIABLE
- Preserves all user routes and middleware
- Adds /ping health check endpoint

Queue-Based Mode (FLASH_IS_MOTHERSHIP not set or false):
- Creates generic FastAPI app with /execute endpoint
- Uses RemoteExecutor for function execution
"""

import importlib.util
import logging
import os
from typing import Any, Dict

from fastapi import FastAPI

from logger import setup_logging
from unpack_volume import maybe_unpack
from tetra_rp.protos.remote_execution import FunctionRequest, FunctionResponse  # type: ignore[import-untyped]
from remote_executor import RemoteExecutor

# Initialize logging configuration
setup_logging()
logger = logging.getLogger(__name__)

# Unpack Flash deployment artifacts if running in Flash mode
# This is a no-op for Live Serverless and local development
maybe_unpack()

# Determine mode based on environment variables
is_mothership = os.getenv("FLASH_IS_MOTHERSHIP") == "true"

if is_mothership:
    # Mothership mode: Import user's FastAPI application
    try:
        main_file = os.getenv("FLASH_MAIN_FILE", "main.py")
        app_variable = os.getenv("FLASH_APP_VARIABLE", "app")

        logger.info(f"Mothership mode: Importing {app_variable} from {main_file}")

        # Dynamic import of user's module
        spec = importlib.util.spec_from_file_location("user_main", main_file)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot find or load {main_file}")

        user_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(user_module)

        # Get the FastAPI app from user's module
        if not hasattr(user_module, app_variable):
            raise AttributeError(f"Module {main_file} does not have '{app_variable}' attribute")

        app = getattr(user_module, app_variable)

        if not isinstance(app, FastAPI):
            raise TypeError(
                f"Expected FastAPI instance, got {type(app).__name__} for {app_variable}"
            )

        logger.info(f"Successfully imported FastAPI app '{app_variable}' from {main_file}")

        # Add /ping endpoint if not already present
        # Check if /ping route exists (compare by path)
        ping_exists = any(getattr(route, "path", None) == "/ping" for route in app.routes)

        if not ping_exists:

            @app.get("/ping")
            async def ping_mothership() -> Dict[str, Any]:
                """Health check endpoint for mothership (added by framework)."""
                return {
                    "status": "healthy",
                    "endpoint": "mothership",
                    "id": os.getenv("RUNPOD_ENDPOINT_ID", "unknown"),
                }

            logger.info("Added /ping endpoint to user's FastAPI app")

    except Exception as error:
        logger.error(f"Failed to initialize mothership mode: {error}", exc_info=True)
        raise

else:
    # Queue-based mode: Create generic Load Balancer handler app
    app = FastAPI(title="Load Balancer Handler")
    logger.info("Queue-based mode: Using generic Load Balancer handler")


# Queue-based mode endpoints
if not is_mothership:

    @app.get("/ping")
    async def ping() -> Dict[str, Any]:
        """Ping endpoint for health checks (RunPod Load Balancer requirement).

        Returns HTTP 200 when healthy. RunPod measures cold start by tracking
        the transition from 204 (initializing) to 200 (healthy).
        """
        return {"status": "healthy"}

    @app.post("/execute")
    async def execute(request: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a remote function via HTTP POST request.

        Expects FunctionRequest JSON payload.
        Supports both direct FunctionRequest format and RunPod wrapped format.
        """
        output: FunctionResponse

        try:
            executor = RemoteExecutor()
            # Handle both direct FunctionRequest and RunPod wrapped format
            request_data = request.get("input", request)
            input_data = FunctionRequest(**request_data)
            output = await executor.ExecuteFunction(input_data)

        except Exception as error:
            output = FunctionResponse(
                success=False,
                error=f"Error in handler: {str(error)}",
            )

        return output.model_dump()  # type: ignore[no-any-return]


if __name__ == "__main__":
    import uvicorn

    # Local development server for testing
    uvicorn.run(app, host="0.0.0.0", port=80)
