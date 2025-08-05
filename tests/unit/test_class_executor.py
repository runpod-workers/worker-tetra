"""Tests for ClassExecutor component."""

import base64
import cloudpickle
from datetime import datetime
from unittest.mock import MagicMock

from class_executor import ClassExecutor
from remote_execution import FunctionRequest


class TestClassExecution:
    """Test class method execution functionality."""

    def setup_method(self):
        """Setup for each test method."""
        mock_workspace_manager = MagicMock()
        self.executor = ClassExecutor(mock_workspace_manager)

    def encode_args(self, *args):
        """Helper to encode arguments."""
        return [
            base64.b64encode(cloudpickle.dumps(arg)).decode("utf-8") for arg in args
        ]

    def encode_kwargs(self, **kwargs):
        """Helper to encode keyword arguments."""
        return {
            k: base64.b64encode(cloudpickle.dumps(v)).decode("utf-8")
            for k, v in kwargs.items()
        }

    def test_execute_class_method_basic(self):
        """Test basic class method execution."""
        request = FunctionRequest(
            execution_type="class",
            class_name="TestClass",
            class_code="""
class TestClass:
    def __init__(self, value):
        self.value = value
    
    def get_value(self):
        return f'Value: {self.value}'
""",
            method_name="get_value",
            constructor_args=self.encode_args("test"),
            args=[],
            kwargs={},
        )

        response = self.executor.execute_class_method(request)

        assert response.success is True
        assert response.instance_id is not None
        result = cloudpickle.loads(base64.b64decode(response.result))
        assert result == "Value: test"

    def test_execute_class_method_with_args(self):
        """Test class method execution with method arguments."""
        request = FunctionRequest(
            execution_type="class",
            class_name="Calculator",
            class_code="""
class Calculator:
    def __init__(self):
        pass
    
    def add(self, a, b):
        return a + b
""",
            method_name="add",
            constructor_args=[],
            args=self.encode_args(5, 3),
            kwargs={},
        )

        response = self.executor.execute_class_method(request)

        assert response.success is True
        result = cloudpickle.loads(base64.b64decode(response.result))
        assert result == 8

    def test_execute_class_method_default_call(self):
        """Test class method execution with default __call__ method."""
        request = FunctionRequest(
            execution_type="class",
            class_name="Callable",
            class_code="""
class Callable:
    def __init__(self, message):
        self.message = message
    
    def __call__(self):
        return self.message
""",
            constructor_args=self.encode_args("hello"),
            args=[],
            kwargs={},
        )

        response = self.executor.execute_class_method(request)

        assert response.success is True
        result = cloudpickle.loads(base64.b64decode(response.result))
        assert result == "hello"

    def test_execute_class_method_not_found(self):
        """Test execution when method is not found in class."""
        request = FunctionRequest(
            execution_type="class",
            class_name="TestClass",
            class_code="""
class TestClass:
    def __init__(self):
        pass
    
    def existing_method(self):
        return "exists"
""",
            method_name="missing_method",
            args=[],
            kwargs={},
        )

        response = self.executor.execute_class_method(request)

        assert response.success is False
        assert "missing_method" in response.error
        assert "not found" in response.error

    def test_execute_class_method_with_exception(self):
        """Test error handling when class method raises exception."""
        request = FunctionRequest(
            execution_type="class",
            class_name="ErrorClass",
            class_code="""
class ErrorClass:
    def __init__(self):
        pass
    
    def error_method(self):
        raise ValueError('Method error')
""",
            method_name="error_method",
            args=[],
            kwargs={},
        )

        response = self.executor.execute_class_method(request)

        assert response.success is False
        assert "Method error" in response.error
        assert "ValueError" in response.error


class TestInstanceManagement:
    """Test class instance management functionality."""

    def setup_method(self):
        """Setup for each test method."""
        mock_workspace_manager = MagicMock()
        self.executor = ClassExecutor(mock_workspace_manager)

    def encode_args(self, *args):
        """Helper to encode arguments."""
        return [
            base64.b64encode(cloudpickle.dumps(arg)).decode("utf-8") for arg in args
        ]

    def test_create_new_instance(self):
        """Test creating a new class instance."""
        request = FunctionRequest(
            execution_type="class",
            class_name="Counter",
            class_code="""
class Counter:
    def __init__(self, start=0):
        self.count = start
    
    def increment(self):
        self.count += 1
        return self.count
""",
            method_name="increment",
            constructor_args=self.encode_args(5),
            create_new_instance=True,
            args=[],
            kwargs={},
        )

        response = self.executor.execute_class_method(request)

        assert response.success is True
        assert response.instance_id is not None
        assert response.instance_id in self.executor.class_instances

        # Check metadata
        metadata = response.instance_info
        assert metadata["class_name"] == "Counter"
        assert metadata["method_calls"] == 1
        assert "created_at" in metadata

    def test_reuse_existing_instance(self):
        """Test reusing an existing class instance."""
        # Create initial instance
        initial_request = FunctionRequest(
            execution_type="class",
            class_name="Counter",
            class_code="""
class Counter:
    def __init__(self, start=0):
        self.count = start
    
    def increment(self):
        self.count += 1
        return self.count
    
    def get_count(self):
        return self.count
""",
            method_name="increment",
            constructor_args=self.encode_args(0),
            create_new_instance=True,
            args=[],
            kwargs={},
        )

        first_response = self.executor.execute_class_method(initial_request)
        instance_id = first_response.instance_id

        # Reuse the same instance
        reuse_request = FunctionRequest(
            execution_type="class",
            class_name="Counter",
            class_code="# Code not needed for reuse",
            method_name="get_count",
            instance_id=instance_id,
            create_new_instance=False,
            args=[],
            kwargs={},
        )

        second_response = self.executor.execute_class_method(reuse_request)

        assert second_response.success is True
        assert second_response.instance_id == instance_id

        # Should return incremented count from first call
        result = cloudpickle.loads(base64.b64decode(second_response.result))
        assert result == 1

    def test_instance_metadata_tracking(self):
        """Test that instance metadata is properly tracked."""
        request = FunctionRequest(
            execution_type="class",
            class_name="TestClass",
            class_code="""
class TestClass:
    def __init__(self):
        pass
    
    def test_method(self):
        return "test"
""",
            method_name="test_method",
            args=[],
            kwargs={},
        )

        # Execute method multiple times
        response1 = self.executor.execute_class_method(request)
        instance_id = response1.instance_id

        request.instance_id = instance_id
        request.create_new_instance = False
        self.executor.execute_class_method(request)

        # Check metadata updates
        metadata = self.executor.instance_metadata[instance_id]
        assert metadata["method_calls"] == 2
        assert metadata["class_name"] == "TestClass"

        # Verify timestamps
        created_time = datetime.fromisoformat(metadata["created_at"])
        last_used_time = datetime.fromisoformat(metadata["last_used"])
        assert last_used_time >= created_time

    def test_generate_instance_id(self):
        """Test automatic instance ID generation."""
        request = FunctionRequest(
            execution_type="class",
            class_name="TestClass",
            class_code="""
class TestClass:
    def test_method(self):
        return "test"
""",
            method_name="test_method",
            args=[],
            kwargs={},
        )

        response = self.executor.execute_class_method(request)

        assert response.success is True
        assert response.instance_id is not None
        assert response.instance_id.startswith("TestClass_")
        assert len(response.instance_id.split("_")[1]) == 8  # UUID hex[:8]

    def test_class_not_found_error(self):
        """Test error when class is not found in provided code."""
        request = FunctionRequest(
            execution_type="class",
            class_name="MissingClass",
            class_code="""
class OtherClass:
    def __init__(self):
        pass
""",
            method_name="test_method",
            args=[],
            kwargs={},
        )

        response = self.executor.execute_class_method(request)

        assert response.success is False
        assert "MissingClass" in response.error
        assert "not found" in response.error
