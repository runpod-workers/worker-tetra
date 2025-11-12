import io
import logging
import traceback
import uuid
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime
from typing import Dict, Any, Tuple

from .remote_execution import FunctionRequest, FunctionResponse
from .serialization_utils import SerializationUtils


class ClassExecutor:
    """Handles execution of class methods with instance management."""

    def __init__(self):
        # Instance registry for persistent class instances
        self.class_instances: Dict[str, Any] = {}
        self.instance_metadata: Dict[str, Dict[str, Any]] = {}

    def execute(self, request: FunctionRequest) -> FunctionResponse:
        """Execute class method."""
        return self.execute_class_method(request)

    def execute_class_method(self, request: FunctionRequest) -> FunctionResponse:
        """
        Execute a class method with instance management.
        """
        stdout_io = io.StringIO()
        stderr_io = io.StringIO()
        log_io = io.StringIO()

        with redirect_stdout(stdout_io), redirect_stderr(stderr_io):
            # Setup logging
            log_handler = logging.StreamHandler(log_io)
            log_handler.setLevel(logging.DEBUG)
            logger = logging.getLogger()
            logger.addHandler(log_handler)

            try:
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
                args = SerializationUtils.deserialize_args(request.args)
                kwargs = SerializationUtils.deserialize_kwargs(request.kwargs)

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
        serialized_result = SerializationUtils.serialize_result(result)
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

    def _get_or_create_instance(self, request: FunctionRequest) -> Tuple[Any, str]:
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
        logging.debug(f"Creating new instance of class: {request.class_name}")

        # Execute class code
        namespace: Dict[str, Any] = {}
        if request.class_code:
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
            constructor_args = SerializationUtils.deserialize_args(
                request.constructor_args
            )

        if hasattr(request, "constructor_kwargs") and request.constructor_kwargs:
            constructor_kwargs = SerializationUtils.deserialize_kwargs(
                request.constructor_kwargs
            )

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

        logging.debug(f"Created instance with ID: {instance_id}")
        return instance, instance_id

    def _update_instance_metadata(self, instance_id: str):
        """Update metadata for an instance."""
        if instance_id in self.instance_metadata:
            self.instance_metadata[instance_id]["method_calls"] += 1
            self.instance_metadata[instance_id]["last_used"] = (
                datetime.now().isoformat()
            )
