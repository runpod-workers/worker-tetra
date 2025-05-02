import traceback
import runpod
import base64
import cloudpickle
import subprocess
import importlib
import io
import logging
from contextlib import redirect_stdout, redirect_stderr
from remote_execution import (
    FunctionRequest,
    FunctionResponse,
    RemoteExecutorStub,
)


class RemoteExecutor(RemoteExecutorStub):
    """
    RemoteExecutor class for executing functions in a serverless environment.
    Inherits from RemoteExecutorStub.
    """

    async def ExecuteFunction(self, request: FunctionRequest) -> FunctionResponse:
        """
        Execute a function on the remote resource.

        Args:
            request: FunctionRequest object containing function details

        Returns:
            FunctionResponse object with execution result
        """
        installed = self.install_dependencies(request.dependencies)
        if installed.success:
            print(installed.stdout)
        else:
            return installed

        return self.execute(request)

    def install_dependencies(self, packages) -> FunctionResponse:
        """
        Install Python packages using pip with proper process completion handling.

        Args:
            packages: List of package names or package specifications

        Returns:
            FunctionResponse: Object indicating success or failure with details
        """
        if not packages:
            return FunctionResponse(success=True, stdout="No packages to install")

        print(f"Installing dependencies: {packages}")

        try:
            # Use pip to install the packages
            # Note: communicate() already waits for process completion
            process = subprocess.Popen(
                ["uv", "pip", "install", "--no-cache-dir"] + packages,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            # This waits for the process to complete and captures output
            stdout, stderr = process.communicate()

            # Force reload of installed packages
            importlib.invalidate_caches()

            # Simply rely on pip's return code
            if process.returncode != 0:
                return FunctionResponse(
                    success=False,
                    error="Error installing packages",
                    stdout=stderr.decode(),
                )
            else:
                print(f"Successfully installed packages: {packages}")
                return FunctionResponse(
                    success=True,
                    stdout=stdout.decode(),
                )
        except Exception as e:
            return FunctionResponse(
                success=False,
                error=f"Exception during package installation: {e}",
            )

    def execute(self, request: FunctionRequest) -> FunctionResponse:
        """
        Execute a function as a remote resource.

        Args:
            request: FunctionRequest object containing function details

        Returns:
            FunctionResponse object with execution result
        """
        stdout_io = io.StringIO()
        stderr_io = io.StringIO()
        log_io = io.StringIO()

        # Capture all stdout, stderr, and logs into variables and supply them to the FunctionResponse
        with redirect_stdout(stdout_io), redirect_stderr(stderr_io):
            try:
                # Redirect logging to capture log messages
                log_handler = logging.StreamHandler(log_io)
                log_handler.setLevel(logging.DEBUG)
                logger = logging.getLogger()
                logger.addHandler(log_handler)

                namespace = {}
                exec(request.function_code, namespace)

                if request.function_name not in namespace:
                    return FunctionResponse(
                        success=False,
                        result=f"Function '{request.function_name}' not found in the provided code",
                    )

                func = namespace[request.function_name]

                # Deserialize arguments using cloudpickle
                args = [cloudpickle.loads(base64.b64decode(arg)) for arg in request.args]
                kwargs = {
                    k: cloudpickle.loads(base64.b64decode(v))
                    for k, v in request.kwargs.items()
                }

                # Execute the function
                result = func(*args, **kwargs)

            except Exception as e:
                # Combine stdout, stderr, and logs
                combined_output = (
                    stdout_io.getvalue() + stderr_io.getvalue() + log_io.getvalue()
                )

                # Capture full traceback for better debugging
                traceback_str = traceback.format_exc()
                error_message = f"{str(e)}\n{traceback_str}"

                return FunctionResponse(
                    success=False,
                    error=error_message,
                    stdout=combined_output,
                )

            finally:
                # Remove the log handler to avoid duplicate logs
                logger.removeHandler(log_handler)

        # Serialize result using cloudpickle
        serialized_result = base64.b64encode(cloudpickle.dumps(result)).decode(
            "utf-8"
        )

        # Combine stdout, stderr, and logs
        combined_output = stdout_io.getvalue() + stderr_io.getvalue() + log_io.getvalue()

        # Return success response
        return FunctionResponse(
            success=True,
            result=serialized_result,
            stdout=combined_output,
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
