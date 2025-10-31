import logging
import asyncio
from typing import List, Any, Optional
from remote_execution import FunctionRequest, FunctionResponse, RemoteExecutorStub
from dependency_installer import DependencyInstaller
from function_executor import FunctionExecutor
from class_executor import ClassExecutor
from log_streamer import start_log_streaming, stop_log_streaming, get_streamed_logs
from cache_sync_manager import CacheSyncManager
from constants import NAMESPACE


class RemoteExecutor(RemoteExecutorStub):
    """
    RemoteExecutor orchestrates remote function and class execution.
    Uses composition pattern with specialized components.
    Supports both dynamic (dev) and production (tarball-based) execution modes.
    """

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(f"{NAMESPACE}.{__name__.split('.')[-1]}")

        # Load tarball if specified (must happen before production executor init)
        self._load_tarball_if_needed()

        # Initialize components using composition
        self.dependency_installer = DependencyInstaller()
        self.function_executor = FunctionExecutor()
        self.class_executor = ClassExecutor()
        self.cache_sync = CacheSyncManager()

        # Initialize production executor if in production mode
        self.production_executor: Optional[Any] = None
        self._initialize_production_executor()

    def _load_tarball_if_needed(self):
        """Load production worker code tarball from network volume and add to Python path."""
        try:
            from tarball_loader import should_load_tarball, load_and_extract_tarball
            from constants import WORKERS_CODE_DIR
            import sys
            from pathlib import Path

            if should_load_tarball():
                success = load_and_extract_tarball()

                if success:
                    # Add extracted workers code directory to Python path
                    workers_code_path = Path(WORKERS_CODE_DIR)
                    if workers_code_path.exists():
                        workers_code_str = str(workers_code_path)
                        if workers_code_str not in sys.path:
                            sys.path.insert(0, workers_code_str)
                            self.logger.info(f"Added {workers_code_path} to sys.path")
                else:
                    self.logger.error(
                        "Tarball loading failed, continuing with dynamic execution"
                    )

        except ImportError:
            self.logger.debug("Tarball loader not available, skipping")

    def _initialize_production_executor(self):
        """Initialize production executor if running in production mode."""
        try:
            from production_executor import (
                ProductionExecutor,
                is_production_mode_enabled,
            )

            if is_production_mode_enabled():
                self.production_executor = ProductionExecutor()
                self.logger.info(
                    "Production execution mode ENABLED - using tarball-loaded code"
                )
            else:
                self.logger.info(
                    "Production execution mode DISABLED - using dynamic code execution"
                )
        except ImportError:
            self.logger.debug(
                "ProductionExecutor not available - running in development mode"
            )

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
            # Check if we should use production execution
            if self._should_use_production_execution(request):
                self.logger.info(
                    f"Using production execution for {getattr(request, 'function_name', None) or getattr(request, 'class_name', 'unknown')}"
                )
                return self.production_executor.execute(request)

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

            # Route to appropriate execution method based on type
            execution_type = getattr(request, "execution_type", "function")

            # Execute the function/class
            if execution_type == "class":
                result = self.class_executor.execute_class_method(request)
            else:
                result = self.function_executor.execute(request)

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

    def _should_use_production_execution(self, request: FunctionRequest) -> bool:
        """
        Determine if request should use production execution.

        Returns True if:
        1. Production executor is initialized (production mode enabled)
        2. Request has a callable name
        3. Callable is available in production registry
        4. Request doesn't have custom code (function_code or class_code)
        """
        if not self.production_executor:
            return False

        # Get callable name
        callable_name = getattr(request, "function_name", None) or getattr(
            request, "class_name", None
        )
        if not callable_name:
            return False

        # Check if callable is registered
        if not self.production_executor.is_registered(callable_name):
            self.logger.debug(
                f"Callable '{callable_name}' not found in production registry, using dynamic execution"
            )
            return False

        # If request has custom code, use dynamic execution
        execution_type = getattr(request, "execution_type", "function")
        if execution_type == "function" and getattr(request, "function_code", None):
            self.logger.debug(
                "Request has custom function_code, using dynamic execution"
            )
            return False
        elif execution_type == "class" and getattr(request, "class_code", None):
            self.logger.debug("Request has custom class_code, using dynamic execution")
            return False

        return True

    async def _install_dependencies_parallel(
        self, request: FunctionRequest
    ) -> FunctionResponse:
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

        self.logger.debug(
            f"Starting parallel installation of {len(tasks)} tasks: {task_names}"
        )

        # Execute all tasks in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results and handle failures
        return self._process_parallel_results(results, task_names)

    async def _install_dependencies_sequential(
        self, request: FunctionRequest
    ) -> FunctionResponse:
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

        return FunctionResponse(
            success=True, stdout="Dependencies installed successfully"
        )

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
