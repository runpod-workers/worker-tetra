"""Load Balancer handler for executing remote functions via HTTP.

This handler provides a FastAPI application for the Load Balancer runtime.
It supports:
- /ping: Health check endpoint (required by RunPod Load Balancer)
- /execute: Remote function execution via HTTP POST

The handler uses worker-tetra's RemoteExecutor for function execution.

For generated handlers from flash build:
- Those handlers extend this with user-defined routes
- They use the same execution engine
"""

from typing import Any, Dict

from fastapi import FastAPI

from logger import setup_logging
from remote_execution import FunctionRequest, FunctionResponse
from remote_executor import RemoteExecutor

# Initialize logging configuration
setup_logging()

# Create FastAPI app
app = FastAPI(title="Load Balancer Handler")


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

    return output.model_dump()


if __name__ == "__main__":
    import uvicorn

    # Local development server for testing
    uvicorn.run(app, host="0.0.0.0", port=8000)
