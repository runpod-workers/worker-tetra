import io
import logging
import traceback
import inspect
from contextlib import redirect_stdout, redirect_stderr
from typing import Dict, Any

from runpod_flash.protos.remote_execution import FunctionRequest, FunctionResponse
from serialization_utils import SerializationUtils


class FunctionExecutor:
    """Handles execution of individual functions with output capture."""

    async def execute(self, request: FunctionRequest) -> FunctionResponse:
        """
        Execute a function with full output capture.

        Args:
            request: FunctionRequest object containing function details
        Returns:
            FunctionResponse object with execution result
        """
        stdout_io = io.StringIO()
        stderr_io = io.StringIO()
        log_io = io.StringIO()

        # Capture all stdout, stderr, and logs
        with redirect_stdout(stdout_io), redirect_stderr(stderr_io):
            # Setup logging capture
            log_handler = logging.StreamHandler(log_io)
            log_handler.setLevel(logging.DEBUG)
            logger = logging.getLogger()
            logger.addHandler(log_handler)

            try:
                # Execute function code in namespace
                namespace: Dict[str, Any] = {}
                if request.function_code:
                    exec(request.function_code, namespace)

                if request.function_name not in namespace:
                    return FunctionResponse(
                        success=False,
                        result=f"Function '{request.function_name}' not found in the provided code",
                    )

                func = namespace[request.function_name]

                # Deserialize arguments
                args = SerializationUtils.deserialize_args(request.args)
                kwargs = SerializationUtils.deserialize_kwargs(request.kwargs)

                # Execute the function (handle both sync and async)
                if inspect.iscoroutinefunction(func):
                    # Async function - await directly
                    result = await func(*args, **kwargs)
                else:
                    # Sync function - call directly
                    result = func(*args, **kwargs)

            except Exception as e:
                # Combine output streams
                combined_output = stdout_io.getvalue() + stderr_io.getvalue() + log_io.getvalue()

                # Capture full traceback
                traceback_str = traceback.format_exc()
                error_message = f"{str(e)}\n{traceback_str}"

                return FunctionResponse(
                    success=False,
                    error=error_message,
                    stdout=combined_output,
                )

            finally:
                # Clean up logging handler
                if "logger" in locals() and "log_handler" in locals():
                    logger.removeHandler(log_handler)

        # Serialize result
        serialized_result = SerializationUtils.serialize_result(result)

        # Combine output streams
        combined_output = stdout_io.getvalue() + stderr_io.getvalue() + log_io.getvalue()

        return FunctionResponse(
            success=True,
            result=serialized_result,
            stdout=combined_output,
        )
