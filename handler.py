import traceback
import runpod
import base64
import cloudpickle
import subprocess
import importlib
import io
import logging
import os
import uuid
from datetime import datetime
from contextlib import redirect_stdout, redirect_stderr
from typing import Dict, Any
from remote_execution import (
    FunctionRequest,
    FunctionResponse,
    RemoteExecutorStub,
)


class RemoteExecutor(RemoteExecutorStub):
    """
    Enhanced RemoteExecutor class with class-based execution support.
    Inherits from RemoteExecutorStub.
    """

    def __init__(self):
        super().__init__()
        # NEW: Instance registry for persistent class instances
        self.class_instances: Dict[str, Any] = {}
        self.instance_metadata: Dict[str, Dict] = {}

    async def ExecuteFunction(self, request: FunctionRequest) -> FunctionResponse:
        """
        Execute a function or class method on the remote resource.

        Args:
            request: FunctionRequest object containing function details

        Returns:
            FunctionResponse object with execution result
        """
        # Install system dependencies first
        if request.system_dependencies:
            sys_installed = self.install_system_dependencies(
                request.system_dependencies
            )
            if not sys_installed.success:
                return sys_installed
            print(sys_installed.stdout)

        # Install Python dependencies next
        if request.dependencies:
            py_installed = self.install_dependencies(request.dependencies)
            if not py_installed.success:
                return py_installed
            print(py_installed.stdout)

        # NEW: Route to appropriate execution method based on type
        execution_type = getattr(request, "execution_type", "function")
        if execution_type == "class":
            return self.execute_class_method(request)
        else:
            return self.execute(request)  # Your existing function execution

    # NEW METHOD: Class method execution
    def execute_class_method(self, request: FunctionRequest) -> FunctionResponse:
        """
        Execute a class method with instance management.
        """
        stdout_io = io.StringIO()
        stderr_io = io.StringIO()
        log_io = io.StringIO()

        with redirect_stdout(stdout_io), redirect_stderr(stderr_io):
            try:
                # Setup logging
                log_handler = logging.StreamHandler(log_io)
                log_handler.setLevel(logging.DEBUG)
                logger = logging.getLogger()
                logger.addHandler(log_handler)

                # Get or create class instance
                instance, instance_id = self._get_or_create_instance(request)

                # Get the method to call
                method_name = getattr(request, "method_name", "__call__")
                if not hasattr(instance, method_name):
                    return FunctionResponse(
                        success=False,
                        error=f"Method '{method_name}' not found in class '{request.class_name}'",
                    )

                method = getattr(instance, method_name)

                # Deserialize method arguments
                args = [
                    cloudpickle.loads(base64.b64decode(arg)) for arg in request.args
                ]
                kwargs = {
                    k: cloudpickle.loads(base64.b64decode(v))
                    for k, v in request.kwargs.items()
                }

                # Execute the method
                result = method(*args, **kwargs)

                # Update instance metadata
                self._update_instance_metadata(instance_id)

            except Exception as e:
                # Error handling
                combined_output = (
                    stdout_io.getvalue() + stderr_io.getvalue() + log_io.getvalue()
                )
                traceback_str = traceback.format_exc()
                error_message = f"{str(e)}\n{traceback_str}"

                return FunctionResponse(
                    success=False,
                    error=error_message,
                    stdout=combined_output,
                )

            finally:
                logger.removeHandler(log_handler)

        # Serialize result
        serialized_result = base64.b64encode(cloudpickle.dumps(result)).decode("utf-8")
        combined_output = (
            stdout_io.getvalue() + stderr_io.getvalue() + log_io.getvalue()
        )

        return FunctionResponse(
            success=True,
            result=serialized_result,
            stdout=combined_output,
        )

    # NEW METHOD: Get or create class instance
    def _get_or_create_instance(self, request: FunctionRequest) -> tuple[Any, str]:
        """
        Get existing instance or create new one.
        """
        instance_id = getattr(request, "instance_id", None)
        create_new = getattr(request, "create_new_instance", True)

        # Check if we should reuse existing instance
        if not create_new and instance_id and instance_id in self.class_instances:
            print(f"Reusing existing instance: {instance_id}")
            return self.class_instances[instance_id], instance_id

        # Create new instance
        print(f"Creating new instance of class: {request.class_name}")

        # Execute class code
        namespace = {}
        # e
        exec(request.class_code, namespace)

        if request.class_name not in namespace:
            raise ValueError(
                f"Class '{request.class_name}' not found in the provided code"
            )

        cls = namespace[request.class_name]

        # Deserialize constructor arguments
        constructor_args = []
        constructor_kwargs = {}

        if hasattr(request, "constructor_args") and request.constructor_args:
            constructor_args = [
                cloudpickle.loads(base64.b64decode(arg))
                for arg in request.constructor_args
            ]

        if hasattr(request, "constructor_kwargs") and request.constructor_kwargs:
            constructor_kwargs = {
                k: cloudpickle.loads(base64.b64decode(v))
                for k, v in request.constructor_kwargs.items()
            }

        # Create instance
        instance = cls(*constructor_args, **constructor_kwargs)

        # Generate instance ID if not provided
        if not instance_id:
            instance_id = f"{request.class_name}_{uuid.uuid4().hex[:8]}"

        # Store instance
        self.class_instances[instance_id] = instance
        self.instance_metadata[instance_id] = {
            "class_name": request.class_name,
            "created_at": datetime.now().isoformat(),
            "method_calls": 0,
            "last_used": datetime.now().isoformat(),
        }

        print(f"Created instance with ID: {instance_id}")
        return instance, instance_id

    # NEW METHOD: Update instance metadata
    def _update_instance_metadata(self, instance_id: str):
        """Update metadata for an instance."""
        if instance_id in self.instance_metadata:
            self.instance_metadata[instance_id]["method_calls"] += 1
            self.instance_metadata[instance_id]["last_used"] = (
                datetime.now().isoformat()
            )

    # NEW METHOD: Cleanup old instances
    def cleanup_instances(self, max_age_minutes: int = 60):
        """Clean up old instances"""
        from datetime import datetime, timedelta

        cutoff_time = datetime.now() - timedelta(minutes=max_age_minutes)
        instances_to_remove = []

        for instance_id, metadata in self.instance_metadata.items():
            last_used = datetime.fromisoformat(
                metadata.get("last_used", metadata["created_at"])
            )
            if last_used < cutoff_time:
                instances_to_remove.append(instance_id)

        for instance_id in instances_to_remove:
            if instance_id in self.class_instances:
                del self.class_instances[instance_id]
            if instance_id in self.instance_metadata:
                del self.instance_metadata[instance_id]
            print(f"Cleaned up instance: {instance_id}")

        return len(instances_to_remove)

    def install_system_dependencies(self, packages) -> FunctionResponse:
        """
        Install system packages using apt-get.
        """
        if not packages:
            return FunctionResponse(
                success=True, stdout="No system packages to install"
            )

        print(f"Installing system dependencies: {packages}")

        try:
            # Update package list first
            update_process = subprocess.Popen(
                ["apt-get", "update"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            update_stdout, update_stderr = update_process.communicate()

            if update_process.returncode != 0:
                return FunctionResponse(
                    success=False,
                    error="Error updating package list",
                    stdout=update_stderr.decode(),
                )

            # Install the packages
            process = subprocess.Popen(
                ["apt-get", "install", "-y", "--no-install-recommends"] + packages,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={**os.environ, "DEBIAN_FRONTEND": "noninteractive"},
            )

            stdout, stderr = process.communicate()

            if process.returncode != 0:
                return FunctionResponse(
                    success=False,
                    error="Error installing system packages",
                    stdout=stderr.decode(),
                )
            else:
                print(f"Successfully installed system packages: {packages}")
                return FunctionResponse(
                    success=True,
                    stdout=stdout.decode(),
                )
        except Exception as e:
            return FunctionResponse(
                success=False,
                error=f"Exception during system package installation: {e}",
            )

    def install_dependencies(self, packages) -> FunctionResponse:
        """
        Install Python packages using pip.
        """
        if not packages:
            return FunctionResponse(success=True, stdout="No packages to install")

        print(f"Installing dependencies: {packages}")

        try:
            process = subprocess.Popen(
                ["uv", "pip", "install", "--no-cache-dir"] + packages,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            stdout, stderr = process.communicate()
            importlib.invalidate_caches()

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
        """
        stdout_io = io.StringIO()
        stderr_io = io.StringIO()
        log_io = io.StringIO()

        with redirect_stdout(stdout_io), redirect_stderr(stderr_io):
            try:
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

                args = [
                    cloudpickle.loads(base64.b64decode(arg)) for arg in request.args
                ]
                kwargs = {
                    k: cloudpickle.loads(base64.b64decode(v))
                    for k, v in request.kwargs.items()
                }

                result = func(*args, **kwargs)

            except Exception as e:
                combined_output = (
                    stdout_io.getvalue() + stderr_io.getvalue() + log_io.getvalue()
                )
                traceback_str = traceback.format_exc()
                error_message = f"{str(e)}\n{traceback_str}"

                return FunctionResponse(
                    success=False,
                    error=error_message,
                    stdout=combined_output,
                )

            finally:
                logger.removeHandler(log_handler)

        serialized_result = base64.b64encode(cloudpickle.dumps(result)).decode("utf-8")
        combined_output = (
            stdout_io.getvalue() + stderr_io.getvalue() + log_io.getvalue()
        )

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


if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
