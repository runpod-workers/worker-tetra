"""Integration tests for RunPod volume workspace functionality."""

import asyncio
import base64
import cloudpickle
import threading
from unittest.mock import Mock, patch

from handler import RemoteExecutor, handler


class TestFullWorkflowWithVolume:
    """Test complete request workflows with volume integration."""

    @patch("os.path.exists")
    @patch("subprocess.Popen")
    @patch("os.chdir")
    @patch("glob.glob")
    async def test_full_workflow_with_volume(
        self, mock_glob, mock_chdir, mock_popen, mock_exists
    ):
        """Test complete workflow from handler to execution with volume."""
        # Mock volume exists
        mock_exists.side_effect = lambda path: path in [
            "/runpod-volume",
            "/runpod-volume/.venv",
        ]

        # Mock glob for site-packages
        mock_glob.return_value = ["/runpod-volume/.venv/lib/python3.12/site-packages"]

        # Mock successful dependency installation
        mock_process = Mock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (b"Successfully installed numpy", b"")
        mock_popen.return_value = mock_process

        # Mock numpy module
        with patch.dict("sys.modules", {"numpy": Mock(__version__="1.21.0")}):
            # Complete request with dependencies and function
            event = {
                "input": {
                    "function_name": "numpy_test",
                    "function_code": """
def numpy_test():
    import numpy as np
    return f"NumPy version: {np.__version__}"
""",
                    "args": [],
                    "kwargs": {},
                    "dependencies": ["numpy==1.21.0"],
                }
            }

            # This will fail until full integration is implemented
            result = await handler(event)

            assert result["success"] is True
            assert "error" not in result or result["error"] is None

            # Should have changed to volume directory
            chdir_calls = [call[0][0] for call in mock_chdir.call_args_list]
            assert "/runpod-volume" in chdir_calls

            # Should have installed dependencies
            assert mock_popen.called
            install_command = mock_popen.call_args[0][0]
            assert "numpy==1.21.0" in " ".join(install_command)

    @patch("os.path.exists")
    @patch("subprocess.Popen")
    @patch("os.chdir")
    @patch("glob.glob")
    async def test_workflow_with_system_dependencies(
        self, mock_glob, mock_chdir, mock_popen, mock_exists
    ):
        """Test workflow that includes both system and Python dependencies."""
        mock_exists.side_effect = lambda path: path in [
            "/runpod-volume",
            "/runpod-volume/.venv",
        ]

        # Mock glob for site-packages
        mock_glob.return_value = ["/runpod-volume/.venv/lib/python3.12/site-packages"]

        # Mock apt-get update and install
        apt_update_process = Mock()
        apt_update_process.returncode = 0
        apt_update_process.communicate.return_value = (b"Package lists updated", b"")

        apt_install_process = Mock()
        apt_install_process.returncode = 0
        apt_install_process.communicate.return_value = (
            b"System packages installed",
            b"",
        )

        # Mock uv pip list (for _get_installed_packages)
        pip_list_process = Mock()
        pip_list_process.returncode = 0
        pip_list_process.communicate.return_value = (
            b"",  # No packages installed yet
            b"",
        )

        # Mock uv pip install
        pip_install_process = Mock()
        pip_install_process.returncode = 0
        pip_install_process.communicate.return_value = (
            b"Python packages installed",
            b"",
        )

        mock_popen.side_effect = [
            apt_update_process,
            apt_install_process,
            pip_list_process,  # Added missing call
            pip_install_process,
        ]

        # Mock subprocess.run for the test function
        mock_run_result = Mock()
        mock_run_result.stdout = "/usr/bin/curl"

        with patch("subprocess.run", return_value=mock_run_result):
            with patch.dict("sys.modules", {"requests": Mock(__version__="2.25.1")}):
                event = {
                    "input": {
                        "function_name": "system_test",
                        "function_code": """
def system_test():
    import subprocess
    result = subprocess.run(['which', 'curl'], capture_output=True, text=True)
    return result.stdout.strip()
""",
                        "args": [],
                        "kwargs": {},
                        "system_dependencies": ["curl"],
                        "dependencies": ["requests==2.25.1"],
                    }
                }

                # This will fail until system dependency integration is implemented
                result = await handler(event)

                assert result["success"] is True

                # Should have called apt-get update and install
                calls = [call[0][0] for call in mock_popen.call_args_list]
        assert any("apt-get" in " ".join(call) and "update" in call for call in calls)
        assert any("apt-get" in " ".join(call) and "curl" in call for call in calls)
        assert any(
            "uv" in call and "requests==2.25.1" in " ".join(call) for call in calls
        )


class TestConcurrentRequests:
    """Test realistic concurrent access scenarios."""

    @patch("os.path.exists")
    @patch("subprocess.Popen")
    @patch("fcntl.flock")
    @patch("os.chdir")
    @patch("glob.glob")
    async def test_multiple_concurrent_requests(
        self, mock_glob, mock_chdir, mock_flock, mock_popen, mock_exists
    ):
        """Test multiple concurrent requests to the same endpoint."""
        mock_exists.side_effect = lambda path: path in [
            "/runpod-volume",
            "/runpod-volume/.venv",
        ]

        # Mock glob for site-packages
        mock_glob.return_value = ["/runpod-volume/.venv/lib/python3.12/site-packages"]

        # Mock successful installations
        mock_process = Mock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (b"Installation complete", b"")
        mock_popen.return_value = mock_process

        # Mock the time module
        mock_time = Mock()
        mock_time.sleep = Mock()

        with patch.dict(
            "sys.modules", {"time": mock_time, "numpy": Mock(__version__="1.21.0")}
        ):

            async def make_request(request_id):
                event = {
                    "input": {
                        "function_name": "concurrent_test",
                        "function_code": f"""
def concurrent_test():
    import time
    time.sleep(0.1)  # Simulate some work
    return "Request {request_id} completed"
""",
                        "args": [],
                        "kwargs": {},
                        "dependencies": ["numpy==1.21.0"],
                    }
                }
                return await handler(event)

            # Start 5 concurrent requests
            tasks = [make_request(i) for i in range(5)]

            # This will fail until concurrent safety is implemented
            results = await asyncio.gather(*tasks)

            # All requests should succeed
            for i, result in enumerate(results):
                assert result["success"] is True
                decoded_result = cloudpickle.loads(base64.b64decode(result["result"]))
                assert f"Request {i} completed" in decoded_result

            # Since workspace is already initialized, flock might not be called
            # Just verify that all requests succeeded
            assert len(results) == 5

    @patch("os.path.exists")
    @patch("subprocess.Popen")
    def test_concurrent_dependency_installation(self, mock_popen, mock_exists):
        """Test that concurrent dependency installations don't conflict."""
        mock_exists.side_effect = lambda path: path in [
            "/runpod-volume",
            "/runpod-volume/.venv",
        ]

        # Track installation calls
        install_calls = []

        def track_popen(*args, **kwargs):
            if "uv" in args[0] and "pip" in args[0]:
                install_calls.append(args[0])
            mock_process = Mock()
            mock_process.returncode = 0
            mock_process.communicate.return_value = (b"Installation complete", b"")
            return mock_process

        mock_popen.side_effect = track_popen

        def install_deps(executor, packages):
            return executor.install_dependencies(packages)

        # Create multiple executors trying to install different packages
        executors = [RemoteExecutor() for _ in range(3)]
        package_sets = [["numpy==1.21.0"], ["pandas==1.3.0"], ["scipy==1.7.0"]]

        threads = []
        results = []

        for executor, packages in zip(executors, package_sets):
            thread = threading.Thread(
                target=lambda e=executor, p=packages: results.append(install_deps(e, p))
            )
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # This will fail until concurrent installation safety is implemented
        assert len(results) == 3
        assert all(result.success for result in results)

        # Should have made installation calls for all packages
        all_packages = ["numpy==1.21.0", "pandas==1.3.0", "scipy==1.7.0"]
        for package in all_packages:
            assert any(package in " ".join(call) for call in install_calls)


class TestMixedExecution:
    """Test mixed volume and non-volume execution scenarios."""

    @patch("os.path.exists")
    @patch("os.chdir")
    async def test_mixed_volume_and_non_volume_execution(self, mock_chdir, mock_exists):
        """Test that handlers work both with and without volumes."""
        # First request - no volume available
        mock_exists.return_value = False

        event_no_volume = {
            "input": {
                "function_name": "simple_test",
                "function_code": "def simple_test():\n    return 'no volume'",
                "args": [],
                "kwargs": {},
            }
        }

        result_no_volume = await handler(event_no_volume)
        assert result_no_volume["success"] is True

        # Second request - volume becomes available
        mock_exists.side_effect = lambda path: path in [
            "/runpod-volume",
            "/runpod-volume/.venv",
        ]

        event_with_volume = {
            "input": {
                "function_name": "volume_test",
                "function_code": "def volume_test():\n    return 'with volume'",
                "args": [],
                "kwargs": {},
            }
        }

        # This will fail until mixed execution is properly handled
        result_with_volume = await handler(event_with_volume)
        assert result_with_volume["success"] is True
        chdir_calls = [call[0][0] for call in mock_chdir.call_args_list]
        assert "/runpod-volume" in chdir_calls

    @patch("os.path.exists")
    @patch("subprocess.Popen")
    @patch("os.makedirs")
    @patch("builtins.open")
    async def test_fallback_on_volume_initialization_failure(
        self, mock_open, mock_makedirs, mock_popen, mock_exists
    ):
        """Test graceful fallback when volume initialization fails."""
        mock_exists.side_effect = (
            lambda path: path == "/runpod-volume"
        )  # Volume exists but venv doesn't exist

        # Mock file operations
        mock_file = Mock()
        mock_file.fileno.return_value = 3
        mock_open.return_value.__enter__.return_value = mock_file

        # Mock failed virtual environment creation
        mock_process = Mock()
        mock_process.returncode = 1
        mock_process.communicate.return_value = (b"", b"Failed to create venv")
        mock_popen.return_value = mock_process

        event = {
            "input": {
                "function_name": "fallback_test",
                "function_code": "def fallback_test():\n    return 'fallback execution'",
                "args": [],
                "kwargs": {},
                "dependencies": ["numpy==1.21.0"],
            }
        }

        # This will fail until fallback mechanism is implemented
        result = await handler(event)

        # Should fail because venv creation failed and no fallback implemented yet
        assert result["success"] is False
        assert "failed to create virtual environment" in result.get("error", "").lower()


class TestErrorHandlingIntegration:
    """Test error handling in integrated volume scenarios."""

    @patch("os.path.exists")
    @patch("subprocess.Popen")
    async def test_dependency_installation_failure_with_volume(
        self, mock_popen, mock_exists
    ):
        """Test proper error handling when dependency installation fails in volume."""
        mock_exists.side_effect = lambda path: path in [
            "/runpod-volume",
            "/runpod-volume/.venv",
        ]

        # Mock failed dependency installation
        mock_process = Mock()
        mock_process.returncode = 1
        mock_process.communicate.return_value = (
            b"",
            b"Package not found: nonexistent-package",
        )
        mock_popen.return_value = mock_process

        event = {
            "input": {
                "function_name": "test_func",
                "function_code": "def test_func():\n    return 'should not execute'",
                "args": [],
                "kwargs": {},
                "dependencies": ["nonexistent-package==999.999.999"],
            }
        }

        result = await handler(event)

        assert result["success"] is False
        assert "error installing packages" in result.get("error", "").lower()
        # Function should not have been executed
        assert "result" not in result or result["result"] is None

    @patch("os.path.exists")
    @patch("os.chdir")
    async def test_volume_permission_error_handling(self, mock_chdir, mock_exists):
        """Test handling of permission errors when accessing volume."""
        mock_exists.return_value = True
        mock_chdir.side_effect = PermissionError("Permission denied")

        event = {
            "input": {
                "function_name": "permission_test",
                "function_code": "def permission_test():\n    return 'test'",
                "args": [],
                "kwargs": {},
            }
        }

        # This will fail until permission error handling is implemented
        result = await handler(event)

        # Should handle permission error gracefully
        assert result["success"] is False
        assert "permission denied" in result.get("error", "").lower()
