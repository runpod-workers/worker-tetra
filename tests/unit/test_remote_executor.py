import pytest
import base64
import cloudpickle
from unittest.mock import Mock, patch
import subprocess

from handler import RemoteExecutor
from remote_execution import FunctionRequest


class TestRemoteExecutor:
    """Unit tests for the RemoteExecutor class."""

    def setup_method(self):
        """Setup for each test method."""
        self.executor = RemoteExecutor()

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

    def test_executor_init(self):
        """Test RemoteExecutor initialization."""
        assert hasattr(self.executor, "class_instances")
        assert hasattr(self.executor, "instance_metadata")
        assert len(self.executor.class_instances) == 0
        assert len(self.executor.instance_metadata) == 0

    @pytest.mark.asyncio
    async def test_execute_simple_function(self):
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

    @pytest.mark.asyncio
    async def test_execute_function_with_args(self):
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

    @pytest.mark.asyncio
    async def test_execute_class_method(self):
        """Test class method execution."""
        request = FunctionRequest(
            execution_type="class",
            class_name="TestClass",
            class_code="class TestClass:\n    def __init__(self, value):\n        self.value = value\n    def get_value(self):\n        return f'Value: {self.value}'",
            method_name="get_value",
            constructor_args=self.encode_args("test"),
            constructor_kwargs={},
            args=[],
            kwargs={},
        )

        response = self.executor.execute_class_method(request)

        assert response.success is True
        assert response.instance_id is not None
        result = cloudpickle.loads(base64.b64decode(response.result))
        assert result == "Value: test"

    @pytest.mark.asyncio
    async def test_function_error_handling(self):
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

    @patch("subprocess.Popen")
    def test_install_dependencies(self, mock_popen):
        """Test dependency installation."""
        mock_process = Mock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (b"Successfully installed", b"")
        mock_popen.return_value = mock_process

        response = self.executor.install_dependencies(["numpy"])

        assert response.success is True
        mock_popen.assert_called_once_with(
            ["uv", "pip", "install", "--no-cache-dir", "numpy"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
