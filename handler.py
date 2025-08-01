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
import sys
from datetime import datetime
from contextlib import redirect_stdout, redirect_stderr
from typing import Dict, Any
from remote_execution import (
    FunctionRequest,
    FunctionResponse,
    RemoteExecutorStub,
)


logging.basicConfig(
    level=logging.DEBUG,  # or INFO for less verbose output
    stream=sys.stdout,  # send logs to stdout (so docker captures it)
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)


class RemoteExecutor(RemoteExecutorStub):
    """
    RemoteExecutor class for executing functions and classes in a serverless environment.
    Inherits from RemoteExecutorStub.
    """

    def __init__(self):
        super().__init__()
        # Instance registry for persistent class instances
        self.class_instances: Dict[str, Any] = {}
        self.instance_metadata: Dict[str, Dict] = {}

        # Initialize the RemoteExecutor with volume detection
        self.has_runpod_volume = os.path.exists("/runpod-volume")
        self.workspace_path = "/runpod-volume" if self.has_runpod_volume else "/app"
        self.venv_path = (
            os.path.join(self.workspace_path, ".venv")
            if self.has_runpod_volume
            else None
        )
        self.cache_path = (
            os.path.join(self.workspace_path, ".uv-cache")
            if self.has_runpod_volume
            else None
        )

        if self.has_runpod_volume:
            self.configure_uv_cache()
            self.configure_volume_environment()

    def initialize_workspace(self, timeout: int = 30) -> FunctionResponse:
        """
        Initialize the RunPod volume workspace with virtual environment.

        Args:
            timeout: Maximum time to wait for workspace initialization

        Returns:
            FunctionResponse: Success or failure of initialization
        """
        if not self.has_runpod_volume:
            return FunctionResponse(
                success=True, stdout="No volume available, using container workspace"
            )

        # Check if workspace is already initialized
        if self.venv_path and os.path.exists(self.venv_path):
            return FunctionResponse(
                success=True, stdout="Workspace already initialized"
            )

        # Use file-based locking for concurrent initialization
        lock_file = os.path.join(self.workspace_path, ".initialization.lock")

        try:
            # Ensure workspace directory exists
            os.makedirs(self.workspace_path, exist_ok=True)

            with open(lock_file, "w") as lock:
                try:
                    # Try to acquire exclusive lock with timeout
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except (BlockingIOError, OSError):
                    # Lock not available, wait for initialization by another worker
                    start_time = time.time()
                    while time.time() - start_time < timeout:
                        if self.venv_path and os.path.exists(self.venv_path):
                            return FunctionResponse(
                                success=True,
                                stdout="Workspace initialized by another worker",
                            )
                        time.sleep(0.5)

                    return FunctionResponse(
                        success=False, error="Workspace initialization timeout"
                    )

                # We have the lock, initialize the workspace
                return self._create_virtual_environment()

        except Exception as e:
            return FunctionResponse(
                success=False, error=f"Failed to initialize workspace: {str(e)}"
            )
        finally:
            # Clean up lock file
            try:
                if os.path.exists(lock_file):
                    os.remove(lock_file)
            except OSError:
                pass

    def _create_virtual_environment(self) -> FunctionResponse:
        """Create virtual environment in the volume."""
        if not self.venv_path:
            return FunctionResponse(
                success=False, error="Virtual environment path not configured"
            )

        try:
            process = subprocess.Popen(
                ["uv", "venv", self.venv_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            stdout, stderr = process.communicate()

            if process.returncode != 0:
                return FunctionResponse(
                    success=False,
                    error="Failed to create virtual environment",
                    stdout=stderr.decode(),
                )
            else:
                return FunctionResponse(success=True, stdout=stdout.decode())
        except Exception as e:
            return FunctionResponse(
                success=False, error=f"Exception creating virtual environment: {str(e)}"
            )

    def _get_installed_packages(self):
        """Get list of currently installed packages in the virtual environment."""
        if (
            not self.has_runpod_volume
            or not self.venv_path
            or not os.path.exists(self.venv_path)
        ):
            return {}

        try:
            env = os.environ.copy()
            env["VIRTUAL_ENV"] = self.venv_path

            process = subprocess.Popen(
                ["uv", "pip", "list", "--format=freeze"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )

            stdout, stderr = process.communicate()

            if process.returncode != 0:
                return {}

            packages = {}
            for line in stdout.decode().strip().split("\n"):
                if "==" in line:
                    name, version = line.split("==", 1)
                    packages[name] = version

            return packages
        except Exception:
            return {}

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

        # Route to appropriate execution method based on type
        execution_type = getattr(request, "execution_type", "function")
        if execution_type == "class":
            return self.execute_class_method(request)
        else:
            return self.execute(request)  # Your existing function execution

    # METHOD: Class method execution
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
            instance_id=instance_id,
            instance_info=self.instance_metadata.get(instance_id, {}),
        )

    def _get_or_create_instance(self, request: FunctionRequest) -> tuple[Any, str]:
        """
        Get existing instance or create new one.
        """
        instance_id = getattr(request, "instance_id", None)
        create_new = getattr(request, "create_new_instance", True)

        # Check if we should reuse existing instance
        if not create_new and instance_id and instance_id in self.class_instances:
            logging.debug(f"Reusing existing instance: {instance_id}")
            return self.class_instances[instance_id], instance_id

        # Create new instance
        logging.info(f"Creating new instance of class: {request.class_name}")

        # Execute class code
        namespace = {}
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

        logging.info(f"Created instance with ID: {instance_id}")
        return instance, instance_id

    def _update_instance_metadata(self, instance_id: str):
        """Update metadata for an instance."""
        if instance_id in self.instance_metadata:
            self.instance_metadata[instance_id]["method_calls"] += 1
            self.instance_metadata[instance_id]["last_used"] = (
                datetime.now().isoformat()
            )

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
                env={
                    **os.environ,
                    "DEBIAN_FRONTEND": "noninteractive",
                },  # Prevent prompts
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
        Install Python packages using uv with differential installation support.

        Args:
            packages: List of package names or package specifications
        Returns:
            FunctionResponse: Object indicating success or failure with details
        """
        if not packages:
            return FunctionResponse(success=True, stdout="No packages to install")

        print(f"Installing dependencies: {packages}")

        # If using volume, check which packages are already installed
        if self.has_runpod_volume and self.venv_path and os.path.exists(self.venv_path):
            installed_packages = self._get_installed_packages()
            packages_to_install = []

            for package in packages:
                # Parse package specification (e.g., "numpy==1.21.0" -> "numpy", "1.21.0")
                if "==" in package:
                    name, version = package.split("==", 1)
                    if (
                        name not in installed_packages
                        or installed_packages[name] != version
                    ):
                        packages_to_install.append(package)
                else:
                    # For packages without version specification, always install
                    packages_to_install.append(package)

            if not packages_to_install:
                return FunctionResponse(
                    success=True, stdout="All packages already installed"
                )

            packages = packages_to_install

        try:
            # Prepare environment for virtual environment usage
            env = os.environ.copy()
            if self.has_runpod_volume and self.venv_path:
                env["VIRTUAL_ENV"] = self.venv_path

            # Use uv pip to install the packages
            command = ["uv", "pip", "install", "--no-cache-dir"] + packages
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )

            stdout, stderr = process.communicate()
            importlib.invalidate_caches()

            # Simply rely on uv pip's return code
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
        serialized_result = base64.b64encode(cloudpickle.dumps(result)).decode("utf-8")

        # Combine stdout, stderr, and logs
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


# Start the RunPod serverless handler
if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
