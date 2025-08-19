import logging
from remote_execution import FunctionRequest, FunctionResponse, RemoteExecutorStub
from workspace_manager import WorkspaceManager
from dependency_installer import DependencyInstaller
from function_executor import FunctionExecutor
from class_executor import ClassExecutor
from log_capture import LogCapture


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
        # Start capturing all logs for this request
        log_capture = LogCapture()
        log_capture.start_capture()

        # Debug: Log the current log level being used for capture
        self.logger.debug(f"LogCapture initialized with level: {log_capture.level}")
        self.logger.debug("Starting remote function execution")

        try:
            # Initialize workspace if using volume
            if self.workspace_manager.has_runpod_volume:
                workspace_init = self.workspace_manager.initialize_workspace()
                if not workspace_init.success:
                    # Capture logs and include in error response
                    captured_logs = log_capture.stop_capture()
                    workspace_init.stdout = str(workspace_init.stdout or "") + (
                        captured_logs or ""
                    )
                    return workspace_init
                if workspace_init.stdout:
                    self.logger.info(workspace_init.stdout)

            # Install system dependencies first
            if request.system_dependencies:
                sys_installed = self.dependency_installer.install_system_dependencies(
                    request.system_dependencies
                )
                if not sys_installed.success:
                    # Capture logs and include in error response
                    captured_logs = log_capture.stop_capture()
                    sys_installed.stdout = str(sys_installed.stdout or "") + (
                        captured_logs or ""
                    )
                    return sys_installed
                self.logger.info(sys_installed.stdout)

            # Pre-cache HuggingFace models if requested and acceleration is enabled
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

            # Install Python dependencies next (with acceleration if enabled)
            if request.dependencies:
                self.logger.debug(
                    f"Installing Python dependencies: {request.dependencies}"
                )
                # The DependencyInstaller will automatically use acceleration for large packages
                # when aria2c is available and request.accelerate_downloads is True
                py_installed = self.dependency_installer.install_dependencies(
                    request.dependencies, request.accelerate_downloads
                )
                if not py_installed.success:
                    # Capture logs and include in error response
                    captured_logs = log_capture.stop_capture()
                    py_installed.stdout = str(py_installed.stdout or "") + (
                        captured_logs or ""
                    )
                    return py_installed
                self.logger.info(py_installed.stdout)

            # Route to appropriate execution method based on type
            execution_type = getattr(request, "execution_type", "function")

            # Execute the function/class
            if execution_type == "class":
                result = self.class_executor.execute_class_method(request)
            else:
                result = self.function_executor.execute(request)

            # Add acceleration summary to the result
            self._log_acceleration_summary(request, result)

            # Capture all orchestration logs and add to result
            captured_logs = log_capture.stop_capture()
            if captured_logs:
                if result.stdout:
                    result.stdout = captured_logs + "\n" + str(result.stdout)
                else:
                    result.stdout = captured_logs

            return result

        except Exception as e:
            # Ensure we capture logs even on unexpected errors
            captured_logs = log_capture.stop_capture()
            return FunctionResponse(
                success=False,
                error=f"Unexpected error in RemoteExecutor: {str(e)}",
                stdout=captured_logs,
            )

    def _log_acceleration_summary(
        self, request: FunctionRequest, result: FunctionResponse
    ):
        """Log acceleration impact summary for performance visibility."""
        # Skip expensive summary generation if DEBUG logging is disabled
        if not self.logger.isEnabledFor(logging.DEBUG):
            return

        if not hasattr(self.dependency_installer, "download_accelerator"):
            return

        acceleration_enabled = request.accelerate_downloads
        has_volume = self.workspace_manager.has_runpod_volume
        aria2c_available = self.dependency_installer.download_accelerator.aria2_downloader.aria2c_available

        # Build summary message
        summary_parts = []

        if acceleration_enabled and aria2c_available:
            summary_parts.append("✓ Download acceleration ENABLED")

            if has_volume:
                summary_parts.append(
                    f"✓ Volume workspace: {self.workspace_manager.workspace_path}"
                )
                summary_parts.append("✓ Persistent caching enabled")
            else:
                summary_parts.append("ℹ No persistent volume - using temporary cache")

            if request.hf_models_to_cache:
                summary_parts.append(
                    f"✓ HF models pre-cached: {len(request.hf_models_to_cache)}"
                )

            if request.dependencies:
                large_packages = self.dependency_installer._identify_large_packages(
                    request.dependencies
                )
                if large_packages:
                    summary_parts.append(
                        f"✓ Large packages accelerated: {len(large_packages)}"
                    )

        elif acceleration_enabled and not aria2c_available:
            summary_parts.append(
                "⚠ Download acceleration REQUESTED but aria2c unavailable"
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
            self.logger.debug("=======================================")
