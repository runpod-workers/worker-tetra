import logging
import asyncio
import importlib
import json
import os
from pathlib import Path
from typing import List, Any, Optional
import aiohttp
from tetra_rp.protos.remote_execution import FunctionRequest, FunctionResponse, RemoteExecutorStub  # type: ignore[import-untyped]
from dependency_installer import DependencyInstaller
from function_executor import FunctionExecutor
from class_executor import ClassExecutor
from log_streamer import start_log_streaming, stop_log_streaming, get_streamed_logs
from cache_sync_manager import CacheSyncManager
from serialization_utils import SerializationUtils
from manifest_reconciliation import refresh_manifest_if_stale
from constants import NAMESPACE, DEFAULT_ENDPOINT_TIMEOUT, FLASH_MANIFEST_PATH

# Service discovery for cross-endpoint routing
try:
    from tetra_rp.runtime.service_registry import (  # type: ignore[import-untyped]
        ServiceRegistry,
    )
except ImportError:
    ServiceRegistry = None


class RemoteExecutor(RemoteExecutorStub):
    """
    RemoteExecutor orchestrates remote function and class execution.
    Uses composition pattern with specialized components.
    """

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(f"{NAMESPACE}.{__name__.split('.')[-1]}")

        # Initialize components using composition
        self.dependency_installer = DependencyInstaller()
        self.function_executor = FunctionExecutor()
        self.class_executor = ClassExecutor()
        self.cache_sync = CacheSyncManager()

        # Service discovery for cross-endpoint routing (peer-to-peer model)
        self.service_registry: Optional[ServiceRegistry] = None
        if ServiceRegistry is not None:
            try:
                self.service_registry = ServiceRegistry(manifest_path=Path(FLASH_MANIFEST_PATH))
                self.logger.debug("Service registry initialized for cross-endpoint routing")
            except Exception as e:
                self.logger.debug(f"Failed to initialize service registry: {e}")
                self.service_registry = None
        else:
            self.logger.debug("ServiceRegistry not available (tetra-rp not installed)")

    async def ExecuteFunction(self, request: FunctionRequest) -> FunctionResponse:
        """
        Execute a function or class method on the remote resource.

        Args:
            request: FunctionRequest object containing function details

        Returns:
            FunctionResponse object with execution result
        """
        # Start log streaming to capture all system logs
        # Use the requested log level, not the root logger level
        from logger import get_log_level

        requested_level = get_log_level()
        start_log_streaming(level=requested_level)

        self.logger.debug(
            f"Started log streaming at level: {logging.getLevelName(requested_level)}"
        )
        self.logger.debug(
            f"Executing {request.execution_type} request: {request.function_name or request.class_name}"
        )

        try:
            # Hydrate cache from volume if needed (before any installations)
            has_installations = request.dependencies or request.system_dependencies
            if has_installations:
                await self.cache_sync.hydrate_from_volume()

            # Mark cache baseline before installation
            self.cache_sync.mark_baseline()

            # Install dependencies
            if request.accelerate_downloads:
                # Run installations in parallel when acceleration is enabled
                dep_result = await self._install_dependencies_parallel(request)
                if not dep_result.success:
                    # Add any buffered logs to the failed response
                    logs = get_streamed_logs(clear_buffer=True)
                    if logs:
                        if dep_result.stdout:
                            dep_result.stdout += "\n" + logs
                        else:
                            dep_result.stdout = logs
                    return dep_result
            else:
                # Sequential installation when acceleration is disabled
                dep_result = await self._install_dependencies_sequential(request)
                if not dep_result.success:
                    # Add any buffered logs to the failed response
                    logs = get_streamed_logs(clear_buffer=True)
                    if logs:
                        if dep_result.stdout:
                            dep_result.stdout += "\n" + logs
                        else:
                            dep_result.stdout = logs
                    return dep_result

            # cache sync after installation
            await self.cache_sync.sync_to_volume()

            # Detect execution mode: Flash deployed vs Live Serverless
            has_function_code = bool(getattr(request, "function_code", None))
            has_class_code = bool(getattr(request, "class_code", None))

            if not has_function_code and not has_class_code:
                # Flash Deployed App: code pre-deployed in /app
                # Optimize: check if local BEFORE refreshing manifest
                self.logger.debug("Flash deployment detected, checking execution path")

                # ServiceRegistry not available - execute locally
                if not self.service_registry:
                    self.logger.debug("Service registry not available, executing locally")
                    result = await self._execute_flash_function(request)
                else:
                    # Use ServiceRegistry for smart routing
                    try:
                        # Check if local using cached manifest (no State Manager query)
                        is_local = self.service_registry.is_local_function(request.function_name)

                        if is_local:
                            self.logger.debug(
                                f"Executing function '{request.function_name}' locally (no refresh)"
                            )
                            result = await self._execute_flash_function(request)
                        else:
                            # Remote routing - refresh manifest THEN route
                            self.logger.debug(
                                "Remote function detected, refreshing manifest before routing"
                            )
                            try:
                                await refresh_manifest_if_stale(Path(FLASH_MANIFEST_PATH))
                            except Exception as e:
                                self.logger.debug(f"Manifest refresh failed (non-fatal): {e}")

                            # Get fresh endpoint URL after refresh
                            endpoint_url = await self.service_registry.get_endpoint_for_function(
                                request.function_name
                            )

                            if endpoint_url:
                                self.logger.debug(
                                    f"Routing function '{request.function_name}' to {endpoint_url}"
                                )
                                result = await self._route_to_endpoint(request, endpoint_url)
                            else:
                                self.logger.warning(
                                    f"No endpoint URL for '{request.function_name}' after refresh, "
                                    f"executing locally"
                                )
                                result = await self._execute_flash_function(request)

                    except ValueError as e:
                        # Function not in manifest - try local execution
                        self.logger.warning(
                            f"Function lookup failed: {e}, attempting local execution"
                        )
                        result = await self._execute_flash_function(request)
                    except Exception as e:
                        # State Manager unavailable or other error - fallback to local
                        self.logger.warning(
                            f"Service registry error: {e}, attempting local execution"
                        )
                        result = await self._execute_flash_function(request)
            else:
                # Live Serverless: dynamic code execution
                self.logger.debug("Live Serverless mode, executing dynamic code")

                # Route to appropriate execution method based on type
                execution_type = getattr(request, "execution_type", "function")

                # Execute the function/class
                if execution_type == "class":
                    result = await self.class_executor.execute_class_method(request)
                else:
                    result = await self.function_executor.execute(request)

            # Add all captured system logs to the result
            system_logs = get_streamed_logs(clear_buffer=True)
            if system_logs:
                if result.stdout:
                    result.stdout = f"{system_logs}\n\n{result.stdout}"
                else:
                    result.stdout = system_logs

            return result

        finally:
            # Always stop log streaming to clean up
            stop_log_streaming()

    async def _install_dependencies_parallel(self, request: FunctionRequest) -> FunctionResponse:
        """
        Install dependencies and cache models in parallel when acceleration is enabled.

        Args:
            request: FunctionRequest with dependencies to install

        Returns:
            FunctionResponse indicating overall success/failure
        """
        tasks = []
        task_names = []

        # Add system dependencies task
        if request.system_dependencies:
            task = self.dependency_installer.install_system_dependencies_async(
                request.system_dependencies, request.accelerate_downloads
            )
            tasks.append(task)
            task_names.append("system_dependencies")

        # Add Python dependencies task
        if request.dependencies:
            task = self.dependency_installer.install_dependencies_async(
                request.dependencies, request.accelerate_downloads
            )
            tasks.append(task)
            task_names.append("python_dependencies")

        if not tasks:
            return FunctionResponse(success=True, stdout="No dependencies to install")

        self.logger.debug(f"Starting parallel installation of {len(tasks)} tasks: {task_names}")

        # Execute all tasks in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results and handle failures
        return self._process_parallel_results(results, task_names)

    async def _install_dependencies_sequential(self, request: FunctionRequest) -> FunctionResponse:
        """
        Install dependencies and cache models sequentially when acceleration is disabled.

        Args:
            request: FunctionRequest with dependencies to install

        Returns:
            FunctionResponse indicating overall success/failure
        """
        # Install system dependencies first
        if request.system_dependencies:
            sys_installed = self.dependency_installer.install_system_dependencies(
                request.system_dependencies, request.accelerate_downloads
            )
            if not sys_installed.success:
                return sys_installed
            self.logger.info(sys_installed.stdout)

        # Install Python dependencies next
        if request.dependencies:
            py_installed = self.dependency_installer.install_dependencies(
                request.dependencies, request.accelerate_downloads
            )
            if not py_installed.success:
                return py_installed
            self.logger.info(py_installed.stdout)

        return FunctionResponse(success=True, stdout="Dependencies installed successfully")

    def _process_parallel_results(
        self, results: List[Any], task_names: List[str]
    ) -> FunctionResponse:
        """
        Process results from parallel dependency installation tasks.

        Args:
            results: List of task results (may include exceptions)
            task_names: List of task names corresponding to results

        Returns:
            FunctionResponse with aggregated results
        """
        success_count = 0
        failures = []
        stdout_parts = []

        for i, result in enumerate(results):
            task_name = task_names[i]

            if isinstance(result, Exception):
                # Task raised an exception
                error_msg = f"{task_name}: Exception - {str(result)}"
                failures.append(error_msg)
                self.logger.error(error_msg)
            elif isinstance(result, FunctionResponse):
                if result.success:
                    success_count += 1
                    stdout_parts.append(f"✓ {task_name}: {result.stdout}")
                    self.logger.debug(f"✓ {task_name} completed successfully")
                else:
                    error_msg = f"{task_name}: {result.error}"
                    failures.append(error_msg)
                    self.logger.error(f"✗ {task_name} failed: {result.error}")
            else:
                # Unexpected result type
                error_msg = f"{task_name}: Unexpected result type - {type(result)}"
                failures.append(error_msg)
                self.logger.error(error_msg)

        # Determine overall success
        if failures:
            # Some tasks failed
            error_summary = f"Failed tasks: {'; '.join(failures)}"
            return FunctionResponse(
                success=False,
                error=error_summary,
                stdout=f"Parallel installation: {success_count}/{len(results)} tasks succeeded\n"
                + "\n".join(stdout_parts),
            )

        # All tasks succeeded
        return FunctionResponse(
            success=True,
            stdout=f"Parallel installation: {success_count}/{len(results)} tasks completed successfully\n"
            + "\n".join(stdout_parts),
        )

    async def _execute_flash_function(self, request: FunctionRequest) -> FunctionResponse:
        """Execute pre-deployed Flash function from /app directory.

        Args:
            request: Function request with function_name but no function_code

        Returns:
            FunctionResponse with result or error
        """
        function_name = request.function_name

        try:
            # Load manifest from /app (added to sys.path by maybe_unpack)
            manifest = self._load_flash_manifest()

            # Look up function in registry
            if function_name not in manifest["function_registry"]:
                return FunctionResponse(
                    success=False,
                    error=f"Function '{function_name}' not found in flash_manifest.json",
                )

            # Get resource config name from registry
            resource_name = manifest["function_registry"][function_name]
            resource = manifest["resources"][resource_name]

            # Find function details in resource
            func_details = next(
                (f for f in resource["functions"] if f["name"] == function_name),
                None,
            )

            if not func_details:
                return FunctionResponse(
                    success=False,
                    error=f"Function '{function_name}' found in registry but not in resource '{resource_name}'",
                )

            # Import the function from its module
            module_path = func_details["module"]
            self.logger.debug(f"Importing function '{function_name}' from module '{module_path}'")
            module = importlib.import_module(module_path)
            # function_name is guaranteed to be non-None by FunctionRequest validation
            func = getattr(module, function_name)

            # Deserialize args/kwargs (same as Live Serverless)
            args = SerializationUtils.deserialize_args(request.args)
            kwargs = SerializationUtils.deserialize_kwargs(request.kwargs)

            # Execute function
            # Check if async or sync
            if func_details["is_async"]:
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    # Run in executor for blocking calls
                    result = await asyncio.to_thread(func, *args, **kwargs)
            else:
                result = await asyncio.to_thread(func, *args, **kwargs)

            return FunctionResponse(
                success=True,
                result=SerializationUtils.serialize_result(result),
            )

        except Exception as e:
            self.logger.error(f"Flash function execution failed: {e}", exc_info=True)
            return FunctionResponse(
                success=False,
                error=f"Failed to execute Flash function '{function_name}': {str(e)}",
            )

    def _load_flash_manifest(self) -> dict[str, Any]:
        """Load flash_manifest.json from /app directory.

        Returns:
            Manifest dictionary with function routing info

        Raises:
            FileNotFoundError: If manifest not found
            json.JSONDecodeError: If manifest is invalid
        """
        manifest_path = Path(FLASH_MANIFEST_PATH)

        if not manifest_path.exists():
            raise FileNotFoundError(
                "flash_manifest.json not found in /app. "
                "Ensure Flash build artifacts were unpacked correctly."
            )

        with open(manifest_path) as f:
            manifest: dict[str, Any] = json.load(f)
            return manifest

    async def _route_to_endpoint(
        self, request: FunctionRequest, endpoint_url: str
    ) -> FunctionResponse:
        """Route FunctionRequest to target endpoint via RunPod API.

        Args:
            request: Function request to route
            endpoint_url: Full endpoint URL (e.g., https://api.runpod.ai/v2/abc123/run)

        Returns:
            FunctionResponse with result from target endpoint
        """
        try:
            # Prepare payload for RunPod API
            payload = {"input": request.model_dump(exclude_none=True)}

            # Make HTTP request to target endpoint
            api_key = os.getenv("RUNPOD_API_KEY")
            headers = {"Content-Type": "application/json"}

            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            timeout = aiohttp.ClientTimeout(total=DEFAULT_ENDPOINT_TIMEOUT)

            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(endpoint_url, json=payload, headers=headers) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        return FunctionResponse(
                            success=False,
                            error=f"Remote endpoint returned status {response.status}: {error_text}",
                        )

                    result_data = await response.json()

                    # Parse response
                    # RunPod API wraps result in "output" field for async requests
                    if "output" in result_data:
                        output_data = result_data["output"]
                    else:
                        output_data = result_data

                    try:
                        return FunctionResponse(**output_data)
                    except Exception as e:
                        self.logger.error(
                            f"Failed to parse endpoint response: {e}",
                            exc_info=True,
                        )
                        return FunctionResponse(
                            success=False,
                            error=f"Failed to parse response from endpoint: {str(e)}",
                        )

        except Exception as e:
            self.logger.error(
                f"Failed to route to {endpoint_url}: {e}",
                exc_info=True,
            )
            return FunctionResponse(
                success=False,
                error=f"Failed to route to endpoint: {str(e)}",
            )
