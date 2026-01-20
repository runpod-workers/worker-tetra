import runpod
from typing import Dict, Any

from remote_execution import FunctionRequest, FunctionResponse
from remote_executor import RemoteExecutor
from logger import setup_logging
from unpack_volume import maybe_unpack

# Initialize logging configuration
setup_logging()

# Unpack Flash deployment artifacts if running in Flash mode
# This is a no-op for Live Serverless and local development
maybe_unpack()


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
