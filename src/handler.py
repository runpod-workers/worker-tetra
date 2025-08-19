import runpod
import logging
import sys
import os

from remote_execution import FunctionRequest, FunctionResponse
from remote_executor import RemoteExecutor


# Respect LOG_LEVEL environment variable, default to DEBUG
log_level = os.getenv("LOG_LEVEL", "DEBUG").upper()
log_level_mapping = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}

logging.basicConfig(
    level=log_level_mapping.get(log_level, logging.DEBUG),
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
