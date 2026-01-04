from fastapi import FastAPI
from typing import Dict, Any

from remote_execution import FunctionRequest, FunctionResponse
from remote_executor import RemoteExecutor
from logger import setup_logging

# Initialize logging configuration
setup_logging()

# Create FastAPI app
app = FastAPI()


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.post("/execute")
async def execute(request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a remote function via HTTP POST request.
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
