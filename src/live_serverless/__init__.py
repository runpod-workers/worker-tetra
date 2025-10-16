from typing import Dict, Any, Union

from handler_protocol import HandlerEvent
from .logger import setup_logging
from .remote_execution import FunctionRequest, FunctionResponse
from .remote_executor import RemoteExecutor


setup_logging()


async def handler(event: Union[HandlerEvent, Dict[str, Any]]) -> Dict[str, Any]:
    """
    RunPod serverless function handler with dependency installation.

    Args:
        event: Handler event containing input data. Can be HandlerEvent or dict
               for backward compatibility.

    Returns:
        Dictionary containing execution results
    """
    output: FunctionResponse

    try:
        # Coerce dict to HandlerEvent if needed (backward compatibility)
        if isinstance(event, dict):
            event = HandlerEvent(**event)

        executor = RemoteExecutor()
        input_data = FunctionRequest(**event.input)
        output = await executor.ExecuteFunction(input_data)

    except Exception as error:
        output = FunctionResponse(
            success=False,
            error=f"Error in handler: {str(error)}",
        )

    return output.model_dump()
