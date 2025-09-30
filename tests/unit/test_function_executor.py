"""Tests for FunctionExecutor component."""

import base64
import cloudpickle
from unittest.mock import Mock

from function_executor import FunctionExecutor
from workspace_manager import WorkspaceManager
from remote_execution import FunctionRequest


class TestFunctionExecution:
    """Test function execution functionality."""

    def setup_method(self):
        """Setup for each test method."""
        self.workspace_manager = Mock(spec=WorkspaceManager)
        self.executor = FunctionExecutor(self.workspace_manager)

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

    def test_execute_simple_function(self):
        """Test basic function execution."""
        request = FunctionRequest(
            function_name="hello",
            function_code="def hello():\n    return 'hello world'",
            args=[],
            kwargs={},
        )

        response = self.executor.execute(request)

        assert response.success is True
        result = cloudpickle.loads(base64.b64decode(response.result))
        assert result == "hello world"

    def test_execute_function_with_args(self):
        """Test function execution with arguments."""
        request = FunctionRequest(
            function_name="add",
            function_code="def add(a, b):\n    return a + b",
            args=self.encode_args(5, 3),
            kwargs={},
        )

        response = self.executor.execute(request)

        assert response.success is True
        result = cloudpickle.loads(base64.b64decode(response.result))
        assert result == 8

    def test_execute_function_with_kwargs(self):
        """Test function execution with keyword arguments."""
        request = FunctionRequest(
            function_name="greet",
            function_code="def greet(name, greeting='Hello'):\n    return f'{greeting}, {name}!'",
            args=self.encode_args("Alice"),
            kwargs=self.encode_kwargs(greeting="Hi"),
        )

        response = self.executor.execute(request)

        assert response.success is True
        result = cloudpickle.loads(base64.b64decode(response.result))
        assert result == "Hi, Alice!"

    def test_execute_function_not_found(self):
        """Test execution when function is not found in code."""
        request = FunctionRequest(
            function_name="missing_func",
            function_code="def other_func():\n    return 'test'",
            args=[],
            kwargs={},
        )

        response = self.executor.execute(request)

        assert response.success is False
        assert "missing_func" in response.result
        assert "not found" in response.result

    def test_execute_function_with_exception(self):
        """Test error handling when function raises exception."""
        request = FunctionRequest(
            function_name="error_func",
            function_code="def error_func():\n    raise ValueError('Test error')",
            args=[],
            kwargs={},
        )

        response = self.executor.execute(request)

        assert response.success is False
        assert "Test error" in response.error
        assert "ValueError" in response.error

    def test_execute_function_with_output_capture(self):
        """Test that stdout, stderr, and logs are captured."""
        request = FunctionRequest(
            function_name="output_func",
            function_code="""
import logging
import sys

def output_func():
    print("stdout message")
    print("stderr message", file=sys.stderr)
    logging.info("log message")
    return "result"
""",
            args=[],
            kwargs={},
        )

        response = self.executor.execute(request)

        assert response.success is True
        result = cloudpickle.loads(base64.b64decode(response.result))
        assert result == "result"
        assert "stdout message" in response.stdout
        assert "stderr message" in response.stdout
        assert "log message" in response.stdout


class TestWorkspaceIntegration:
    """Test integration with workspace manager."""

    def setup_method(self):
        """Setup for each test method."""
        self.workspace_manager = Mock(spec=WorkspaceManager)
        self.executor = FunctionExecutor(self.workspace_manager)

    def test_execute_function_handles_errors(self):
        """Test that function execution properly handles errors."""
        request = FunctionRequest(
            function_name="error_func",
            function_code="def error_func():\n    raise Exception('test error')",
            args=[],
            kwargs={},
        )

        response = self.executor.execute(request)

        # Verify error was captured
        assert response.success is False
        assert "test error" in response.error
