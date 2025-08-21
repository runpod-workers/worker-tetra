import logging
import asyncio
from typing import List, Any
from remote_execution import FunctionRequest, FunctionResponse, RemoteExecutorStub
from workspace_manager import WorkspaceManager
from dependency_installer import DependencyInstaller
from function_executor import FunctionExecutor
from class_executor import ClassExecutor


class RemoteExecutor(RemoteExecutorStub):
    """
    RemoteExecutor orchestrates remote function and class execution.
    Uses composition pattern with specialized components.
    """

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)

        # Initialize components using composition
        self.workspace_manager = WorkspaceManager()
        self.dependency_installer = DependencyInstaller(self.workspace_manager)
        self.function_executor = FunctionExecutor(self.workspace_manager)
        self.class_executor = ClassExecutor(self.workspace_manager)

    async def ExecuteFunction(self, request: FunctionRequest) -> FunctionResponse:
        """
        Execute a function or class method on the remote resource.

        Args:
            request: FunctionRequest object containing function details

        Returns:
            FunctionResponse object with execution result
        """
        # Initialize workspace if using volume
        if self.workspace_manager.has_runpod_volume:
            workspace_init = self.workspace_manager.initialize_workspace()
            if not workspace_init.success:
                return workspace_init
            if workspace_init.stdout:
                self.logger.info(workspace_init.stdout)

        # Install dependencies and cache models
        if request.accelerate_downloads:
            # Run installations in parallel when acceleration is enabled
            dep_result = await self._install_dependencies_parallel(request)
            if not dep_result.success:
                return dep_result
        else:
            # Sequential installation when acceleration is disabled
            dep_result = await self._install_dependencies_sequential(request)
            if not dep_result.success:
                return dep_result

        # Route to appropriate execution method based on type
        execution_type = getattr(request, "execution_type", "function")

        # Execute the function/class
        if execution_type == "class":
            result = self.class_executor.execute_class_method(request)
        else:
            result = self.function_executor.execute(request)

        # Add acceleration summary to the result
        self._log_acceleration_summary(request, result)

        return result

    def _log_acceleration_summary(
        self, request: FunctionRequest, result: FunctionResponse
    ):
        """Log acceleration impact summary for performance visibility."""
        if not hasattr(self.dependency_installer, "download_accelerator"):
            return

        acceleration_enabled = request.accelerate_downloads
        has_volume = self.workspace_manager.has_runpod_volume
        hf_transfer_available = self.dependency_installer.download_accelerator.hf_transfer_downloader.hf_transfer_available
        nala_available = self.dependency_installer._check_nala_available()

        # Build summary message
        summary_parts = []

        if acceleration_enabled:
            summary_parts.append("✓ Download acceleration ENABLED")

            if has_volume:
                summary_parts.append(
                    f"✓ Volume workspace: {self.workspace_manager.workspace_path}"
                )
                summary_parts.append("✓ Persistent caching enabled")
            else:
                summary_parts.append("ℹ No persistent volume - using temporary cache")

            # System package acceleration status
            if request.system_dependencies:
                large_system_packages = (
                    self.dependency_installer._identify_large_system_packages(
                        request.system_dependencies
                    )
                )
                if large_system_packages and nala_available:
                    summary_parts.append(
                        f"✓ System packages with nala: {len(large_system_packages)}"
                    )
                elif request.system_dependencies:
                    summary_parts.append("→ System packages using standard apt-get")

            if request.hf_models_to_cache:
                summary_parts.append(
                    f"✓ HF models pre-cached: {len(request.hf_models_to_cache)}"
                )

        elif acceleration_enabled and not (hf_transfer_available or nala_available):
            summary_parts.append(
                "⚠ Download acceleration REQUESTED but no accelerators available"
            )
            summary_parts.append("→ Using standard downloads")

        elif not acceleration_enabled:
            summary_parts.append("- Download acceleration DISABLED")
            summary_parts.append("→ Using standard downloads")

        # Log the summary
        if summary_parts:
            self.logger.debug("=== DOWNLOAD ACCELERATION SUMMARY ===")
            for part in summary_parts:
                self.logger.debug(part)
            self.logger.debug("=====================================")

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

        # Add HF model caching tasks
        if request.hf_models_to_cache:
            for model_id in request.hf_models_to_cache:
                task = self.workspace_manager.accelerate_model_download_async(model_id)
                tasks.append(task)
                task_names.append(f"hf_model_{model_id}")

        if not tasks:
            return FunctionResponse(success=True, stdout="No dependencies to install")

        self.logger.info(
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

        # Pre-cache HuggingFace models if requested (should not happen when acceleration disabled)
        if request.accelerate_downloads and request.hf_models_to_cache:
            for model_id in request.hf_models_to_cache:
                self.logger.info(f"Pre-caching HuggingFace model: {model_id}")
                cache_result = self.workspace_manager.accelerate_model_download(
                    model_id
                )
                if cache_result.success:
                    self.logger.info(
                        f"Successfully cached model {model_id}: {cache_result.stdout}"
                    )
                else:
                    self.logger.warning(
                        f"Failed to cache model {model_id}: {cache_result.error}"
                    )

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
                    self.logger.info(f"✓ {task_name} completed successfully")
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
        else:
            # All tasks succeeded
            return FunctionResponse(
                success=True,
                stdout=f"Parallel installation: {success_count}/{len(results)} tasks completed successfully\n"
                + "\n".join(stdout_parts),
            )
