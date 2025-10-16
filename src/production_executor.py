"""Executor for production worker code loaded from tarballs."""

import importlib
import io
import json
import logging
import os
import traceback
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any, Dict, Optional

from base_executor import BaseExecutor
from remote_execution import FunctionRequest, FunctionResponse
from serialization_utils import SerializationUtils

log = logging.getLogger(__name__)


class ProductionExecutor(BaseExecutor):
    """
    Executes production worker code loaded from tarballs.

    This executor is used in production mode where worker code is extracted from
    tarballs at runtime, enabling fast deployments and proper code imports.
    """

    def __init__(self, workspace_manager, registry_path: Optional[Path] = None):
        """
        Initialize production executor.

        Args:
            workspace_manager: Workspace manager instance
            registry_path: Path to registry.json
        """
        super().__init__(workspace_manager)

        if registry_path is None:
            from constants import WORKERS_CODE_DIR

            registry_path = Path(WORKERS_CODE_DIR) / "registry.json"

        self.registry_path = registry_path
        self.registry = self._load_registry()
        self.loaded_modules: Dict[str, Any] = {}  # Cache for loaded modules
        self.class_instances: Dict[str, Any] = {}  # Instance cache for classes

        log.info(
            f"Initialized ProductionExecutor with {len(self.registry)} registered workers"
        )

    def _load_registry(self) -> Dict:
        """Load the production worker registry."""
        if not self.registry_path.exists():
            log.warning(
                f"Registry file not found at {self.registry_path}. "
                "Production execution will not be available."
            )
            return {}

        try:
            with open(self.registry_path, "r") as f:
                registry = json.load(f)
            log.info(
                f"Loaded registry with {len(registry)} production workers from {self.registry_path}"
            )
            return registry
        except Exception as e:
            log.error(f"Failed to load registry from {self.registry_path}: {e}")
            return {}

    def is_registered(self, callable_name: str) -> bool:
        """Check if a worker is registered in production registry."""
        return callable_name in self.registry

    def execute(self, request: FunctionRequest) -> FunctionResponse:
        """
        Execute a production worker function or class method.

        Args:
            request: FunctionRequest with callable name

        Returns:
            FunctionResponse with result
        """
        execution_type = getattr(request, "execution_type", "function")

        if execution_type == "class":
            return self.execute_class_method(request)
        else:
            return self.execute_function(request)

    def execute_function(self, request: FunctionRequest) -> FunctionResponse:
        """Execute a production worker function."""
        stdout_io = io.StringIO()
        stderr_io = io.StringIO()
        log_io = io.StringIO()

        with redirect_stdout(stdout_io), redirect_stderr(stderr_io):
            try:
                # Setup execution environment
                self._setup_execution_environment()

                # Setup logging
                log_handler = logging.StreamHandler(log_io)
                log_handler.setLevel(logging.DEBUG)
                logger = logging.getLogger()
                logger.addHandler(log_handler)

                # Get function from registry
                if not request.function_name:
                    return FunctionResponse(
                        success=False,
                        error="function_name is required for production execution",
                    )

                if not self.is_registered(request.function_name):
                    return FunctionResponse(
                        success=False,
                        error=f"Function '{request.function_name}' not found in production registry",
                    )

                # Load the function
                func = self._load_callable(request.function_name)

                # Deserialize arguments
                args = SerializationUtils.deserialize_args(request.args)
                kwargs = SerializationUtils.deserialize_kwargs(request.kwargs)

                # Execute
                log.info(
                    f"Executing production worker function: {request.function_name}"
                )
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
                if "logger" in locals() and "log_handler" in locals():
                    logger.removeHandler(log_handler)

        # Serialize result
        serialized_result = SerializationUtils.serialize_result(result)
        combined_output = (
            stdout_io.getvalue() + stderr_io.getvalue() + log_io.getvalue()
        )

        return FunctionResponse(
            success=True,
            result=serialized_result,
            stdout=combined_output,
        )

    def execute_class_method(self, request: FunctionRequest) -> FunctionResponse:
        """Execute a method on a production worker class."""
        stdout_io = io.StringIO()
        stderr_io = io.StringIO()
        log_io = io.StringIO()

        with redirect_stdout(stdout_io), redirect_stderr(stderr_io):
            try:
                # Setup execution environment
                self._setup_execution_environment()

                # Setup logging
                log_handler = logging.StreamHandler(log_io)
                log_handler.setLevel(logging.DEBUG)
                logger = logging.getLogger()
                logger.addHandler(log_handler)

                # Get class from registry
                if not request.class_name:
                    return FunctionResponse(
                        success=False,
                        error="class_name is required for production class execution",
                    )

                if not self.is_registered(request.class_name):
                    return FunctionResponse(
                        success=False,
                        error=f"Class '{request.class_name}' not found in production registry",
                    )

                # Get or create instance
                instance_id = getattr(request, "instance_id", request.class_name)
                create_new = getattr(request, "create_new_instance", True)

                if not create_new and instance_id in self.class_instances:
                    instance = self.class_instances[instance_id]
                    log.info(f"Reusing existing instance: {instance_id}")
                else:
                    # Load class and create new instance
                    cls = self._load_callable(request.class_name)

                    # Deserialize constructor arguments
                    constructor_args = []
                    constructor_kwargs = {}

                    if (
                        hasattr(request, "constructor_args")
                        and request.constructor_args
                    ):
                        constructor_args = SerializationUtils.deserialize_args(
                            request.constructor_args
                        )

                    if (
                        hasattr(request, "constructor_kwargs")
                        and request.constructor_kwargs
                    ):
                        constructor_kwargs = SerializationUtils.deserialize_kwargs(
                            request.constructor_kwargs
                        )

                    # Create instance
                    log.info(
                        f"Creating new instance of production worker: {request.class_name}"
                    )
                    instance = cls(*constructor_args, **constructor_kwargs)
                    self.class_instances[instance_id] = instance

                # Get method
                method_name = getattr(request, "method_name", "__call__")
                if not hasattr(instance, method_name):
                    return FunctionResponse(
                        success=False,
                        error=f"Method '{method_name}' not found in class '{request.class_name}'",
                    )

                method = getattr(instance, method_name)

                # Deserialize method arguments
                args = SerializationUtils.deserialize_args(request.args)
                kwargs = SerializationUtils.deserialize_kwargs(request.kwargs)

                # Execute
                log.info(
                    f"Executing production worker method: {request.class_name}.{method_name}"
                )
                result = method(*args, **kwargs)

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
                if "logger" in locals() and "log_handler" in locals():
                    logger.removeHandler(log_handler)

        # Serialize result
        serialized_result = SerializationUtils.serialize_result(result)
        combined_output = (
            stdout_io.getvalue() + stderr_io.getvalue() + log_io.getvalue()
        )

        return FunctionResponse(
            success=True,
            result=serialized_result,
            stdout=combined_output,
            instance_id=instance_id,
        )

    def _load_callable(self, callable_name: str) -> Any:
        """
        Load a callable from production worker modules.

        Args:
            callable_name: Name of the callable to load

        Returns:
            The loaded function or class
        """
        if callable_name not in self.registry:
            raise ValueError(f"Callable '{callable_name}' not found in registry")

        registry_entry = self.registry[callable_name]
        module_name = registry_entry["module"]
        callable_attr_name = registry_entry["name"]

        # Check cache
        cache_key = f"{module_name}.{callable_attr_name}"
        if cache_key in self.loaded_modules:
            log.debug(f"Using cached callable: {cache_key}")
            return self.loaded_modules[cache_key]

        # Import module
        try:
            log.info(f"Importing production worker module: {module_name}")
            module = importlib.import_module(module_name)

            # Get callable from module
            if not hasattr(module, callable_attr_name):
                raise AttributeError(
                    f"Callable '{callable_attr_name}' not found in module '{module_name}'"
                )

            callable_obj = getattr(module, callable_attr_name)

            # Cache it
            self.loaded_modules[cache_key] = callable_obj

            log.info(f"Loaded production worker: {callable_name} from {module_name}")
            return callable_obj

        except ImportError as e:
            raise ImportError(
                f"Failed to import production module '{module_name}': {e}"
            ) from e


def is_production_mode_enabled() -> bool:
    """Check if production execution mode is enabled via environment variable."""
    return os.getenv("TETRA_PRODUCTION_MODE", "false").lower() in ("true", "1", "yes")
