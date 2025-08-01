import pytest
import base64
import cloudpickle
from unittest.mock import patch, MagicMock
from handler import handler
from remote_execution import FunctionRequest, FunctionResponse


class TestRemoteExecutor:
    """Test cases for RemoteExecutor class."""

    @pytest.mark.asyncio
    async def test_execute_function_success(
        self, remote_executor, function_request_basic
    ):
        """Test successful function execution."""
        with patch.object(remote_executor, "execute") as mock_execute:
            mock_execute.return_value = FunctionResponse(
                success=True,
                result=base64.b64encode(cloudpickle.dumps("hello world")).decode(
                    "utf-8"
                ),
                stdout="going to say hello\n",
            )

            result = await remote_executor.ExecuteFunction(function_request_basic)

            assert result.success is True
            assert cloudpickle.loads(base64.b64decode(result.result)) == "hello world"
            mock_execute.assert_called_once_with(function_request_basic)

    @pytest.mark.asyncio
    async def test_execute_function_with_dependencies(
        self, remote_executor, function_request_with_dependencies
    ):
        """Test function execution with Python dependencies."""
        with (
            patch.object(remote_executor, "install_dependencies") as mock_install,
            patch.object(remote_executor, "execute") as mock_execute,
        ):
            mock_install.return_value = FunctionResponse(
                success=True, stdout="installed"
            )
            mock_execute.return_value = FunctionResponse(
                success=True,
                result=base64.b64encode(cloudpickle.dumps("hello")).decode("utf-8"),
            )

            result = await remote_executor.ExecuteFunction(
                function_request_with_dependencies
            )

            assert result.success is True
            mock_install.assert_called_once_with(["requests"])
            mock_execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_function_with_system_dependencies(
        self, remote_executor, function_request_with_system_deps
    ):
        """Test function execution with system dependencies."""
        with (
            patch.object(
                remote_executor, "install_system_dependencies"
            ) as mock_sys_install,
            patch.object(remote_executor, "execute") as mock_execute,
        ):
            mock_sys_install.return_value = FunctionResponse(
                success=True, stdout="installed"
            )
            mock_execute.return_value = FunctionResponse(
                success=True,
                result=base64.b64encode(cloudpickle.dumps("hello")).decode("utf-8"),
            )

            result = await remote_executor.ExecuteFunction(
                function_request_with_system_deps
            )

            assert result.success is True
            mock_sys_install.assert_called_once_with(["curl", "wget"])
            mock_execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_function_dependency_failure(
        self, remote_executor, function_request_with_dependencies
    ):
        """Test function execution when dependency installation fails."""
        with patch.object(remote_executor, "install_dependencies") as mock_install:
            mock_install.return_value = FunctionResponse(
                success=False, error="Package not found", stdout="error output"
            )

            result = await remote_executor.ExecuteFunction(
                function_request_with_dependencies
            )

            assert result.success is False
            assert result.error == "Package not found"

    def test_install_dependencies_success(self, remote_executor):
        """Test successful Python package installation."""
        with patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.returncode = 0
            mock_process.communicate.return_value = (
                b"Successfully installed requests",
                b"",
            )
            mock_popen.return_value = mock_process

            result = remote_executor.install_dependencies(["requests"])

            assert result.success is True
            assert "Successfully installed requests" in result.stdout
            mock_popen.assert_called_once()
            call_args = mock_popen.call_args
            assert call_args[0][0] == [
                "uv",
                "pip",
                "install",
                "--no-cache-dir",
                "requests",
            ]
            assert call_args[1]["stdout"] == -1
            assert call_args[1]["stderr"] == -1
            assert "env" in call_args[1]  # Environment should be passed

    def test_install_dependencies_empty_list(self, remote_executor):
        """Test dependency installation with empty package list."""
        result = remote_executor.install_dependencies([])

        assert result.success is True
        assert result.stdout == "No packages to install"

    def test_install_dependencies_failure(self, remote_executor):
        """Test Python package installation failure."""
        with patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.returncode = 1
            mock_process.communicate.return_value = (b"", b"Package not found")
            mock_popen.return_value = mock_process

            result = remote_executor.install_dependencies(["nonexistent-package"])

            assert result.success is False
            assert result.error == "Error installing packages"
            assert "Package not found" in result.stdout

    def test_install_system_dependencies_success(self, remote_executor):
        """Test successful system package installation."""
        with patch("subprocess.Popen") as mock_popen:
            # Mock update process
            mock_update_process = MagicMock()
            mock_update_process.returncode = 0
            mock_update_process.communicate.return_value = (b"update success", b"")

            # Mock install process
            mock_install_process = MagicMock()
            mock_install_process.returncode = 0
            mock_install_process.communicate.return_value = (b"install success", b"")

            mock_popen.side_effect = [mock_update_process, mock_install_process]

            result = remote_executor.install_system_dependencies(["curl"])

            assert result.success is True
            assert "install success" in result.stdout
            assert mock_popen.call_count == 2

    def test_install_system_dependencies_update_failure(self, remote_executor):
        """Test system package installation when apt update fails."""
        with patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.returncode = 1
            mock_process.communicate.return_value = (b"", b"update failed")
            mock_popen.return_value = mock_process

            result = remote_executor.install_system_dependencies(["curl"])

            assert result.success is False
            assert result.error == "Error updating package list"

    def test_execute_simple_function(self, remote_executor, function_request_basic):
        """Test execution of a simple function."""
        result = remote_executor.execute(function_request_basic)

        assert result.success is True
        deserialized_result = cloudpickle.loads(base64.b64decode(result.result))
        assert deserialized_result == "hello world"
        assert "going to say hello" in result.stdout

    def test_execute_function_with_args(
        self, remote_executor, function_request_with_args
    ):
        """Test execution of function with arguments."""
        result = remote_executor.execute(function_request_with_args)

        assert result.success is True
        deserialized_result = cloudpickle.loads(base64.b64decode(result.result))
        assert deserialized_result == 8
        assert "Adding 5 + 3" in result.stdout

    def test_execute_function_not_found(self, remote_executor):
        """Test execution when function name is not found in code."""
        request = FunctionRequest(
            function_name="nonexistent_function",
            function_code="def hello(): return 'hello'",
            args=[],
            kwargs={},
        )

        result = remote_executor.execute(request)

        assert result.success is False
        assert "Function 'nonexistent_function' not found" in result.result

    def test_execute_function_with_exception(
        self, remote_executor, sample_function_with_error
    ):
        """Test execution when function raises an exception."""
        request = FunctionRequest(
            function_name="error_function",
            function_code=sample_function_with_error,
            args=[],
            kwargs={},
        )

        result = remote_executor.execute(request)

        assert result.success is False
        assert "Test error" in result.error
        assert "ValueError" in result.error


class TestHandler:
    """Test cases for the main handler function."""

    @pytest.mark.asyncio
    async def test_handler_success(self, mock_runpod_event):
        """Test successful handler execution."""
        result = await handler(mock_runpod_event)

        assert result["success"] is True
        assert result["result"] is not None

    @pytest.mark.asyncio
    async def test_handler_invalid_input(self):
        """Test handler with invalid input structure."""
        invalid_event = {"input": {"invalid": "data"}}

        result = await handler(invalid_event)

        assert result["success"] is False
        assert "Error in handler" in result["error"]

    @pytest.mark.asyncio
    async def test_handler_missing_input(self):
        """Test handler with missing input key."""
        empty_event = {}

        result = await handler(empty_event)

        assert result["success"] is False
        assert "Error in handler" in result["error"]
