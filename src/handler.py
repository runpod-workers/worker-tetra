import runpod
import logging
import sys

from remote_execution import FunctionRequest, FunctionResponse
from remote_executor import RemoteExecutor


logging.basicConfig(
    level=logging.DEBUG,  # or INFO for less verbose output
    stream=sys.stdout,  # send logs to stdout (so docker captures it)
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)


async def handler(event: dict) -> dict:
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
