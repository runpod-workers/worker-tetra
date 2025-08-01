import pytest
from unittest.mock import patch, MagicMock
from handler import RemoteExecutor
from remote_execution import FunctionRequest


class TestDependencyManagement:
    """Integration tests for dependency management functionality."""

    @pytest.mark.integration
    def test_install_python_dependencies_integration(self):
        """Test Python dependency installation with mocked subprocess."""
        executor = RemoteExecutor()

        with patch("subprocess.Popen") as mock_popen:
            # Mock successful installation
            mock_process = MagicMock()
            mock_process.returncode = 0
            mock_process.communicate.return_value = (
                b"Successfully installed package-1.0.0",
                b"",
            )
            mock_popen.return_value = mock_process

            result = executor.install_dependencies(["requests", "numpy"])

            assert result.success is True
            assert "Successfully installed" in result.stdout

            # Verify correct command was called
            mock_popen.assert_called_once()
            call_args = mock_popen.call_args
            assert call_args[0][0] == [
                "uv",
                "pip",
                "install",
                "--no-cache-dir",
                "requests",
                "numpy",
            ]
            assert call_args[1]["stdout"] == -1
            assert call_args[1]["stderr"] == -1
            assert "env" in call_args[1]  # Environment should be passed

    @pytest.mark.integration
    def test_install_system_dependencies_integration(self):
        """Test system dependency installation with mocked subprocess."""
        executor = RemoteExecutor()

        with patch("subprocess.Popen") as mock_popen:
            # Mock apt-get update (first call)
            mock_update_process = MagicMock()
            mock_update_process.returncode = 0
            mock_update_process.communicate.return_value = (b"update success", b"")

            # Mock apt-get install (second call)
            mock_install_process = MagicMock()
            mock_install_process.returncode = 0
            mock_install_process.communicate.return_value = (
                b"Reading package lists...\nInstalling curl...\nDone.",
                b"",
            )

            mock_popen.side_effect = [mock_update_process, mock_install_process]

            result = executor.install_system_dependencies(["curl", "wget"])

            assert result.success is True
            assert "Installing curl" in result.stdout

            # Verify both commands were called
            assert mock_popen.call_count == 2

            # Check update command
            update_call = mock_popen.call_args_list[0]
            assert update_call[0][0] == ["apt-get", "update"]

            # Check install command
            install_call = mock_popen.call_args_list[1]
            expected_cmd = [
                "apt-get",
                "install",
                "-y",
                "--no-install-recommends",
                "curl",
                "wget",
            ]
            assert install_call[0][0] == expected_cmd

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_full_workflow_with_dependencies(self):
        """Test complete workflow including dependency installation."""
        executor = RemoteExecutor()

        request = FunctionRequest(
            function_name="test_with_deps",
            function_code="""
def test_with_deps():
    # This would normally import the installed package
    # but we'll mock the installation for testing
    return "function executed with dependencies"
""",
            args=[],
            kwargs={},
            dependencies=["requests"],
            system_dependencies=["curl"],
        )

        with (
            patch.object(executor, "install_dependencies") as mock_py_deps,
            patch.object(executor, "install_system_dependencies") as mock_sys_deps,
            patch.object(executor, "execute") as mock_execute,
        ):
            # Mock successful dependency installations
            mock_sys_deps.return_value = type(
                "obj", (object,), {"success": True, "stdout": "system deps installed"}
            )()
            mock_py_deps.return_value = type(
                "obj", (object,), {"success": True, "stdout": "python deps installed"}
            )()
            mock_execute.return_value = type(
                "obj", (object,), {"success": True, "result": "encoded_result"}
            )()

            result = await executor.ExecuteFunction(request)

            # Verify all steps were called
            mock_sys_deps.assert_called_once_with(["curl"])
            mock_py_deps.assert_called_once_with(["requests"])
            mock_execute.assert_called_once_with(request)

            assert result.success is True

    @pytest.mark.integration
    def test_dependency_installation_failure_handling(self):
        """Test proper error handling when dependency installation fails."""
        executor = RemoteExecutor()

        with patch("subprocess.Popen") as mock_popen:
            # Mock failed installation
            mock_process = MagicMock()
            mock_process.returncode = 1
            mock_process.communicate.return_value = (
                b"",
                b"E: Unable to locate package nonexistent-package",
            )
            mock_popen.return_value = mock_process

            result = executor.install_dependencies(["nonexistent-package"])

            assert result.success is False
            assert result.error == "Error installing packages"
            assert "Unable to locate package" in result.stdout

    @pytest.mark.integration
    def test_system_dependency_update_failure(self):
        """Test handling of apt-get update failures."""
        executor = RemoteExecutor()

        with patch("subprocess.Popen") as mock_popen:
            # Mock failed update
            mock_process = MagicMock()
            mock_process.returncode = 1
            mock_process.communicate.return_value = (
                b"",
                b"E: Could not get lock /var/lib/apt/lists/lock",
            )
            mock_popen.return_value = mock_process

            result = executor.install_system_dependencies(["curl"])

            assert result.success is False
            assert result.error == "Error updating package list"
            assert "Could not get lock" in result.stdout

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_dependency_failure_stops_execution(self):
        """Test that dependency installation failure prevents function execution."""
        executor = RemoteExecutor()

        request = FunctionRequest(
            function_name="test_func",
            function_code="def test_func(): return 'should not execute'",
            dependencies=["nonexistent-package"],
        )

        with (
            patch.object(executor, "install_dependencies") as mock_deps,
            patch.object(executor, "execute") as mock_execute,
        ):
            # Mock failed dependency installation
            mock_deps.return_value = type(
                "obj",
                (object,),
                {
                    "success": False,
                    "error": "Package not found",
                    "stdout": "error details",
                },
            )()

            result = await executor.ExecuteFunction(request)

            # Verify function execution was never called
            mock_execute.assert_not_called()

            # Verify failure response
            assert result.success is False
            assert result.error == "Package not found"

    @pytest.mark.integration
    def test_empty_dependency_lists(self):
        """Test handling of empty dependency lists."""
        executor = RemoteExecutor()

        # Test empty Python dependencies
        py_result = executor.install_dependencies([])
        assert py_result.success is True
        assert py_result.stdout == "No packages to install"

        # Test empty system dependencies
        sys_result = executor.install_system_dependencies([])
        assert sys_result.success is True
        assert sys_result.stdout == "No system packages to install"

    @pytest.mark.integration
    def test_dependency_command_construction(self):
        """Test that dependency installation commands are constructed correctly."""
        executor = RemoteExecutor()

        with patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.returncode = 0
            mock_process.communicate.return_value = (b"success", b"")
            mock_popen.return_value = mock_process

            # Test Python dependency command
            executor.install_dependencies(["package1", "package2>=1.0.0"])

            py_call = mock_popen.call_args
            expected_cmd = [
                "uv",
                "pip",
                "install",
                "--no-cache-dir",
                "package1",
                "package2>=1.0.0",
            ]
            assert py_call[0][0] == expected_cmd

        with patch("subprocess.Popen") as mock_popen:
            # Mock update process
            mock_update = MagicMock()
            mock_update.returncode = 0
            mock_update.communicate.return_value = (b"", b"")

            # Mock install process
            mock_install = MagicMock()
            mock_install.returncode = 0
            mock_install.communicate.return_value = (b"success", b"")

            mock_popen.side_effect = [mock_update, mock_install]

            # Test system dependency command
            executor.install_system_dependencies(["pkg1", "pkg2"])

            install_call = mock_popen.call_args_list[1]
            expected_cmd = [
                "apt-get",
                "install",
                "-y",
                "--no-install-recommends",
                "pkg1",
                "pkg2",
            ]
            assert install_call[0][0] == expected_cmd

            # Verify environment variables for non-interactive mode
            install_env = install_call[1]["env"]
            assert install_env["DEBIAN_FRONTEND"] == "noninteractive"

    @pytest.mark.integration
    def test_exception_handling_in_dependency_installation(self):
        """Test exception handling during dependency installation."""
        executor = RemoteExecutor()

        with patch("subprocess.Popen", side_effect=Exception("Subprocess error")):
            # Test Python dependency exception
            py_result = executor.install_dependencies(["some-package"])
            assert py_result.success is False
            assert "Exception during package installation" in py_result.error
            assert "Subprocess error" in py_result.error

            # Test system dependency exception
            sys_result = executor.install_system_dependencies(["some-package"])
            assert sys_result.success is False
            assert "Exception during system package installation" in sys_result.error
            assert "Subprocess error" in sys_result.error
