"""Tests for FunctionExecutor component."""

import base64
import cloudpickle

from function_executor import FunctionExecutor
from tetra_rp.protos.remote_execution import FunctionRequest


class TestFunctionExecution:
    """Test function execution functionality."""

    def setup_method(self):
        """Setup for each test method."""
        self.executor = FunctionExecutor()

    def encode_args(self, *args):
        """Helper to encode arguments."""
        return [base64.b64encode(cloudpickle.dumps(arg)).decode("utf-8") for arg in args]

    def encode_kwargs(self, **kwargs):
        """Helper to encode keyword arguments."""
        return {
            k: base64.b64encode(cloudpickle.dumps(v)).decode("utf-8") for k, v in kwargs.items()
        }

    async def test_execute_simple_function(self):
        """Test basic function execution."""
        request = FunctionRequest(
            function_name="hello",
            function_code="def hello():\n    return 'hello world'",
            args=[],
            kwargs={},
        )

        response = await self.executor.execute(request)

        assert response.success is True
        result = cloudpickle.loads(base64.b64decode(response.result))
        assert result == "hello world"

    async def test_execute_function_with_args(self):
        """Test function execution with arguments."""
        request = FunctionRequest(
            function_name="add",
            function_code="def add(a, b):\n    return a + b",
            args=self.encode_args(5, 3),
            kwargs={},
        )

        response = await self.executor.execute(request)

        assert response.success is True
        result = cloudpickle.loads(base64.b64decode(response.result))
        assert result == 8

    async def test_execute_function_with_kwargs(self):
        """Test function execution with keyword arguments."""
        request = FunctionRequest(
            function_name="greet",
            function_code="def greet(name, greeting='Hello'):\n    return f'{greeting}, {name}!'",
            args=self.encode_args("Alice"),
            kwargs=self.encode_kwargs(greeting="Hi"),
        )

        response = await self.executor.execute(request)

        assert response.success is True
        result = cloudpickle.loads(base64.b64decode(response.result))
        assert result == "Hi, Alice!"

    async def test_execute_function_not_found(self):
        """Test execution when function is not found in code."""
        request = FunctionRequest(
            function_name="missing_func",
            function_code="def other_func():\n    return 'test'",
            args=[],
            kwargs={},
        )

        response = await self.executor.execute(request)

        assert response.success is False
        assert "missing_func" in response.result
        assert "not found" in response.result

    async def test_execute_function_with_exception(self):
        """Test error handling when function raises exception."""
        request = FunctionRequest(
            function_name="error_func",
            function_code="def error_func():\n    raise ValueError('Test error')",
            args=[],
            kwargs={},
        )

        response = await self.executor.execute(request)

        assert response.success is False
        assert "Test error" in response.error
        assert "ValueError" in response.error

    async def test_execute_function_with_output_capture(self):
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

        response = await self.executor.execute(request)

        assert response.success is True
        result = cloudpickle.loads(base64.b64decode(response.result))
        assert result == "result"
        assert "stdout message" in response.stdout
        assert "stderr message" in response.stdout
        assert "log message" in response.stdout


class TestAsyncFunctionSupport:
    """Test async function execution support."""

    def setup_method(self):
        """Setup for each test method."""
        self.executor = FunctionExecutor()

    def encode_args(self, *args):
        """Helper to encode arguments."""
        return [base64.b64encode(cloudpickle.dumps(arg)).decode("utf-8") for arg in args]

    async def test_execute_async_function(self):
        """Test execution of async function."""
        request = FunctionRequest(
            function_name="async_hello",
            function_code="async def async_hello():\n    return 'async hello world'",
            args=[],
            kwargs={},
        )

        response = await self.executor.execute(request)

        assert response.success is True
        result = cloudpickle.loads(base64.b64decode(response.result))
        assert result == "async hello world"

    async def test_execute_async_function_with_args(self):
        """Test async function with arguments."""
        request = FunctionRequest(
            function_name="async_multiply",
            function_code="async def async_multiply(x, y):\n    return x * y",
            args=self.encode_args(6, 7),
            kwargs={},
        )

        response = await self.executor.execute(request)

        assert response.success is True
        result = cloudpickle.loads(base64.b64decode(response.result))
        assert result == 42

    async def test_execute_async_function_with_await(self):
        """Test async function that uses await."""
        request = FunctionRequest(
            function_name="async_with_await",
            function_code="""
import asyncio

async def async_with_await(delay):
    await asyncio.sleep(delay)
    return f'slept for {delay}s'
""",
            args=self.encode_args(0.01),
            kwargs={},
        )

        response = await self.executor.execute(request)

        assert response.success is True
        result = cloudpickle.loads(base64.b64decode(response.result))
        assert result == "slept for 0.01s"

    async def test_execute_async_function_with_dict_return(self):
        """Test async function returning dict (like GPU worker)."""
        request = FunctionRequest(
            function_name="gpu_matrix_multiply",
            function_code="""
async def gpu_matrix_multiply(input_data: dict) -> dict:
    size = input_data.get("matrix_size", 100)
    return {
        "status": "success",
        "matrix_size": size,
        "result_shape": [size, size],
    }
""",
            args=self.encode_args({"matrix_size": 500}),
            kwargs={},
        )

        response = await self.executor.execute(request)

        assert response.success is True
        result = cloudpickle.loads(base64.b64decode(response.result))
        assert result["status"] == "success"
        assert result["matrix_size"] == 500
        assert result["result_shape"] == [500, 500]


class TestErrorHandling:
    """Test error handling in function execution."""

    def setup_method(self):
        """Setup for each test method."""
        self.executor = FunctionExecutor()

    async def test_execute_function_handles_errors(self):
        """Test that function execution properly handles errors."""
        request = FunctionRequest(
            function_name="error_func",
            function_code="def error_func():\n    raise Exception('test error')",
            args=[],
            kwargs={},
        )

        response = await self.executor.execute(request)

        # Verify error was captured
        assert response.success is False
        assert "test error" in response.error
