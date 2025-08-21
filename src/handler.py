import runpod
from typing import Dict, Any

from remote_execution import FunctionRequest, FunctionResponse
from remote_executor import RemoteExecutor
from logger import setup_logging

# Initialize logging configuration
setup_logging()


async def handler(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    RunPod serverless function handler with dependency installation.
    """
    output: FunctionResponse

    try:
        executor = RemoteExecutor()
        input_data = FunctionRequest(**event.get("input", {}))
        output = await executor.ExecuteFunction(input_data)

    except Exception as error:
        output = FunctionResponse(
            success=False,
            error=f"Error in handler: {str(error)}",
        )

    return output.model_dump()


# Start the RunPod serverless handler
if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
