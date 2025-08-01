"""Tests for function execution in RunPod volume workspace."""

import base64
import cloudpickle
from unittest.mock import Mock, patch, MagicMock

from handler import RemoteExecutor
from remote_execution import FunctionRequest


class TestExecutionEnvironment:
    """Test function execution in volume workspace."""

    @patch("os.path.exists")
    @patch("os.chdir")
    def test_execute_function_in_runpod_volume(self, mock_chdir, mock_exists):
        """Test that function execution happens in /runpod-volume directory."""
        mock_exists.side_effect = lambda path: path in [
            "/runpod-volume",
            "/runpod-volume/.venv",
        ]

        executor = RemoteExecutor()

        function_code = "def test_func():\n    import os\n    return os.getcwd()"
        request = FunctionRequest(
            function_name="test_func", function_code=function_code, args=[], kwargs={}
        )

        # This will fail until we implement directory change in execute()
        response = executor.execute(request)

        assert response.success is True
        # Check that chdir was called with the volume path (should be in call history)
        chdir_calls = [call[0][0] for call in mock_chdir.call_args_list]
        assert "/runpod-volume" in chdir_calls

    @patch("os.path.exists")
    @patch("sys.path")
    @patch("os.chdir")
    @patch("glob.glob")
    def test_function_access_to_persistent_packages(
        self, mock_glob, mock_chdir, mock_sys_path, mock_exists
    ):
        """Test that functions can access packages installed in volume venv."""
        mock_exists.side_effect = lambda path: path in [
            "/runpod-volume",
            "/runpod-volume/.venv",
        ]

        # Mock glob to return site-packages path
        mock_glob.return_value = ["/runpod-volume/.venv/lib/python3.12/site-packages"]

        executor = RemoteExecutor()

        # Mock the entire numpy module in sys.modules
        with patch.dict("sys.modules", {"numpy": Mock(__version__="1.21.0")}):
            function_code = """
def test_func():
    import numpy as np
    return np.__version__
"""
            request = FunctionRequest(
                function_name="test_func",
                function_code=function_code,
                args=[],
                kwargs={},
            )

            # This will fail until we implement venv activation in execute()
            response = executor.execute(request)

            assert response.success is True
            # sys.path should include the venv site-packages
            mock_sys_path.insert.assert_called_with(
                0, "/runpod-volume/.venv/lib/python3.12/site-packages"
            )

    @patch("os.path.exists")
    @patch("os.chdir")
    def test_fallback_execution_without_volume(self, mock_chdir, mock_exists):
        """Test that execution works normally when no volume is present."""
        mock_exists.return_value = False  # No volume available

        executor = RemoteExecutor()

        function_code = "def test_func():\n    return 'hello world'"
        request = FunctionRequest(
            function_name="test_func", function_code=function_code, args=[], kwargs={}
        )

        response = executor.execute(request)

        assert response.success is True
        # Should only restore original directory, not change to volume
        chdir_calls = [call[0][0] for call in mock_chdir.call_args_list]
        assert "/runpod-volume" not in chdir_calls

        # Should still be able to execute the function
        result = cloudpickle.loads(base64.b64decode(response.result))
        assert result == "hello world"


class TestStateManagement:
    """Test workspace state persistence and sharing."""

    @patch("os.path.exists")
    @patch("os.chdir")
    def test_workspace_state_persistence(self, mock_chdir, mock_exists):
        """Test that workspace state survives across multiple function calls."""
        mock_exists.side_effect = lambda path: path in [
            "/runpod-volume",
            "/runpod-volume/.venv",
        ]

        executor = RemoteExecutor()

        # First call - create a file in the workspace
        function_code1 = """
def create_file():
    with open('/runpod-volume/test_file.txt', 'w') as f:
        f.write('persistent data')
    return 'file created'
"""
        request1 = FunctionRequest(
            function_name="create_file",
            function_code=function_code1,
            args=[],
            kwargs={},
        )

        with patch("builtins.open", create=True) as mock_open:
            mock_file = MagicMock()
            mock_open.return_value.__enter__.return_value = mock_file

            response1 = executor.execute(request1)
            assert response1.success is True

        # Second call - read the file (simulating different worker/call)
        function_code2 = """
def read_file():
    with open('/runpod-volume/test_file.txt', 'r') as f:
        return f.read()
"""
        request2 = FunctionRequest(
            function_name="read_file", function_code=function_code2, args=[], kwargs={}
        )

        with patch("builtins.open", create=True) as mock_open:
            mock_file = MagicMock()
            mock_file.read.return_value = "persistent data"
            mock_open.return_value.__enter__.return_value = mock_file

            # This will fail until we implement persistent workspace
            response2 = executor.execute(request2)
            assert response2.success is True

            result = cloudpickle.loads(base64.b64decode(response2.result))
            assert result == "persistent data"

    @patch("os.path.exists")
    def test_multiple_workers_share_workspace(self, mock_exists):
        """Test that multiple RemoteExecutor instances share the same workspace."""
        mock_exists.side_effect = lambda path: path in [
            "/runpod-volume",
            "/runpod-volume/.venv",
        ]

        executor1 = RemoteExecutor()
        executor2 = RemoteExecutor()

        # This will fail until we implement shared workspace detection
        assert executor1.workspace_path == executor2.workspace_path
        assert executor1.workspace_path == "/runpod-volume"

    @patch("os.path.exists")
    @patch("os.environ")
    def test_environment_variables_persist(self, mock_environ, mock_exists):
        """Test that environment variables are properly set for volume usage."""
        mock_exists.side_effect = lambda path: path in [
            "/runpod-volume",
            "/runpod-volume/.venv",
        ]

        # Mock os.environ.get to return a predictable value
        mock_environ.get.return_value = "/usr/bin:/bin"

        executor = RemoteExecutor()

        # This will fail until we implement environment configuration
        executor.configure_volume_environment()

        # Should set required environment variables
        expected_vars = {
            "UV_CACHE_DIR": "/runpod-volume/.uv-cache",
            "VIRTUAL_ENV": "/runpod-volume/.venv",
            "PATH": "/runpod-volume/.venv/bin:/usr/bin:/bin",
        }

        for var, expected_value in expected_vars.items():
            mock_environ.__setitem__.assert_any_call(var, expected_value)


class TestWorkspaceIntegration:
    """Test integration between workspace management and execution."""

    @patch("os.path.exists")
    @patch("subprocess.Popen")
    def test_dependency_installation_uses_volume_venv(self, mock_popen, mock_exists):
        """Test that dependencies are installed into the volume virtual environment."""
        mock_exists.side_effect = lambda path: path in [
            "/runpod-volume",
            "/runpod-volume/.venv",
        ]

        mock_process = Mock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (b"Successfully installed", b"")
        mock_popen.return_value = mock_process

        executor = RemoteExecutor()
        packages = ["numpy==1.21.0"]

        # This will fail until we implement volume-aware installation
        result = executor.install_dependencies(packages)

        assert result.success is True

        # Should use uv pip install with the volume venv
        install_command = mock_popen.call_args[0][0]
        assert "uv" in install_command
        assert "pip" in install_command
        assert "install" in install_command

        # Should include environment variable for the virtual environment
        call_env = mock_popen.call_args[1].get("env", {})
        assert call_env.get("VIRTUAL_ENV") == "/runpod-volume/.venv"

    @patch("os.path.exists")
    def test_workspace_cleanup_on_error(self, mock_exists):
        """Test that workspace is left in a clean state even when execution fails."""
        mock_exists.side_effect = lambda path: path in [
            "/runpod-volume",
            "/runpod-volume/.venv",
        ]

        executor = RemoteExecutor()

        # Function that will raise an exception
        function_code = """
def failing_func():
    raise ValueError("This function always fails")
"""
        request = FunctionRequest(
            function_name="failing_func",
            function_code=function_code,
            args=[],
            kwargs={},
        )

        with patch("os.chdir") as mock_chdir:
            response = executor.execute(request)

            assert response.success is False
            assert "This function always fails" in response.error

            # Should still attempt to change to volume directory (check call history)
            chdir_calls = [call[0][0] for call in mock_chdir.call_args_list]
            assert "/runpod-volume" in chdir_calls
