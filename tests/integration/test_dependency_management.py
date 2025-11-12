import pytest
from unittest.mock import patch, AsyncMock
from live_serverless.remote_executor import RemoteExecutor
from live_serverless.remote_execution import FunctionRequest, FunctionResponse


class TestDependencyManagement:
    """Integration tests for dependency management functionality."""

    @pytest.mark.integration
    def test_install_python_dependencies_integration(self):
        """Test Python dependency installation with mocked subprocess."""
        executor = RemoteExecutor()

        with patch(
            "live_serverless.dependency_installer.run_logged_subprocess"
        ) as mock_subprocess:
            # Mock successful installation
            mock_subprocess.return_value = FunctionResponse(
                success=True, stdout="Successfully installed package-1.0.0"
            )

            result = executor.dependency_installer.install_dependencies(
                ["requests", "numpy"]
            )

            assert result.success is True
            assert "Successfully installed" in result.stdout

            # Verify subprocess utility was called
            mock_subprocess.assert_called_once()

    @pytest.mark.integration
    @patch("platform.system")
    def test_install_system_dependencies_integration(self, mock_platform):
        """Test system dependency installation with mocked subprocess."""
        mock_platform.return_value = "Linux"
        executor = RemoteExecutor()

        with patch(
            "live_serverless.dependency_installer.run_logged_subprocess"
        ) as mock_subprocess:
            # Mock successful apt-get update and install
            mock_subprocess.side_effect = [
                FunctionResponse(success=True, stdout="update success"),
                FunctionResponse(
                    success=True,
                    stdout="Reading package lists...\nInstalling nano...\nDone.",
                ),
            ]

            result = executor.dependency_installer.install_system_dependencies(
                ["nano", "vim"]
            )

            assert result.success is True
            assert "nano" in result.stdout or "vim" in result.stdout

            # Verify both commands were called
            assert mock_subprocess.call_count == 2

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
            patch.object(
                executor.dependency_installer,
                "install_dependencies_async",
                new_callable=AsyncMock,
            ) as mock_py_deps,
            patch.object(
                executor.dependency_installer,
                "install_system_dependencies_async",
                new_callable=AsyncMock,
            ) as mock_sys_deps,
            patch.object(executor.function_executor, "execute") as mock_execute,
        ):
            # Mock successful dependency installations
            from live_serverless.remote_execution import FunctionResponse

            mock_sys_deps.return_value = FunctionResponse(
                success=True, stdout="system deps installed"
            )
            mock_py_deps.return_value = FunctionResponse(
                success=True, stdout="python deps installed"
            )
            mock_execute.return_value = type(
                "obj",
                (object,),
                {
                    "success": True,
                    "result": "encoded_result",
                    "stdout": "function executed",
                },
            )()

            result = await executor.ExecuteFunction(request)

            # Verify all steps were called
            mock_sys_deps.assert_called_once_with(["curl"], True)
            mock_py_deps.assert_called_once_with(["requests"], True)
            mock_execute.assert_called_once_with(request)

            assert result.success is True

    @pytest.mark.integration
    def test_dependency_installation_failure_handling(self):
        """Test proper error handling when dependency installation fails."""
        executor = RemoteExecutor()

        with patch(
            "live_serverless.dependency_installer.run_logged_subprocess"
        ) as mock_subprocess:
            # Mock failed installation
            mock_subprocess.return_value = FunctionResponse(
                success=False, error="E: Unable to locate package nonexistent-package"
            )

            result = executor.dependency_installer.install_dependencies(
                ["nonexistent-package"]
            )

            assert result.success is False
            assert "Unable to locate package" in result.error

    @pytest.mark.integration
    @patch("platform.system")
    def test_system_dependency_update_failure(self, mock_platform):
        """Test handling of apt-get update failures."""
        mock_platform.return_value = "Linux"
        executor = RemoteExecutor()

        with patch(
            "live_serverless.dependency_installer.run_logged_subprocess"
        ) as mock_subprocess:
            # Mock failed update
            mock_subprocess.return_value = FunctionResponse(
                success=False,
                error="E: Could not get lock /var/lib/apt/lists/lock",
                stdout="E: Could not get lock /var/lib/apt/lists/lock",
            )

            result = executor.dependency_installer.install_system_dependencies(["nano"])

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
            patch.object(
                executor.dependency_installer,
                "install_dependencies_async",
                new_callable=AsyncMock,
            ) as mock_deps,
            patch.object(executor.function_executor, "execute") as mock_execute,
        ):
            # Mock failed dependency installation
            from live_serverless.remote_execution import FunctionResponse

            mock_deps.return_value = FunctionResponse(
                success=False,
                error="Error installing packages",
                stdout="error details",
            )

            result = await executor.ExecuteFunction(request)

            # Verify function execution was never called
            mock_execute.assert_not_called()

            # Verify failure response
            assert result.success is False
            assert "Error installing packages" in result.error

    @pytest.mark.integration
    @patch("platform.system")
    def test_empty_dependency_lists(self, mock_platform):
        """Test handling of empty dependency lists."""
        mock_platform.return_value = "Linux"
        executor = RemoteExecutor()

        # Test empty Python dependencies
        py_result = executor.dependency_installer.install_dependencies([])
        assert py_result.success is True
        assert py_result.stdout == "No packages to install"

        # Test empty system dependencies
        sys_result = executor.dependency_installer.install_system_dependencies([])
        assert sys_result.success is True
        assert sys_result.stdout == "No system packages to install"

    @pytest.mark.integration
    @patch("platform.system")
    def test_dependency_command_construction(self, mock_platform):
        """Test that dependency installation commands are constructed correctly."""
        mock_platform.return_value = "Linux"
        executor = RemoteExecutor()

        with patch(
            "live_serverless.dependency_installer.run_logged_subprocess"
        ) as mock_subprocess:
            mock_subprocess.return_value = FunctionResponse(
                success=True, stdout="success"
            )

            # Test Python dependency command
            executor.dependency_installer.install_dependencies(
                ["package1", "package2>=1.0.0"]
            )

            # Verify subprocess utility was called
            mock_subprocess.assert_called()

        with patch(
            "live_serverless.dependency_installer.run_logged_subprocess"
        ) as mock_subprocess:
            # Mock successful update and install processes
            mock_subprocess.side_effect = [
                FunctionResponse(success=True, stdout=""),
                FunctionResponse(success=True, stdout="success"),
            ]

            # Test system dependency command
            executor.dependency_installer.install_system_dependencies(
                ["pkg1", "pkg2"], accelerate_downloads=False
            )

            # Verify subprocess utility was called for both operations
            assert mock_subprocess.call_count == 2

    @pytest.mark.integration
    @patch("platform.system")
    def test_system_dependency_installation_with_nala_acceleration(self, mock_platform):
        """Test system dependency installation with nala acceleration enabled."""
        mock_platform.return_value = "Linux"
        executor = RemoteExecutor()

        with patch(
            "live_serverless.dependency_installer.run_logged_subprocess"
        ) as mock_subprocess:
            # Mock nala availability check, update, and install
            mock_subprocess.side_effect = [
                FunctionResponse(success=True, stdout="/usr/bin/nala"),
                FunctionResponse(success=True, stdout="Reading package lists..."),
                FunctionResponse(
                    success=True, stdout="Successfully installed build-essential"
                ),
            ]

            result = executor.dependency_installer.install_system_dependencies(
                ["build-essential"], accelerate_downloads=True
            )

            assert result.success is True
            assert "Installed with nala" in result.stdout

            # Verify all nala operations were called
            assert mock_subprocess.call_count == 3

    @pytest.mark.integration
    @patch("platform.system")
    def test_system_dependency_installation_no_nala_available(self, mock_platform):
        """Test system dependency installation when nala is not available."""
        mock_platform.return_value = "Linux"
        executor = RemoteExecutor()

        with patch(
            "live_serverless.dependency_installer.run_logged_subprocess"
        ) as mock_subprocess:
            # Mock nala not available, then successful apt-get operations
            mock_subprocess.side_effect = [
                FunctionResponse(success=False, error="which: nala: not found"),
                FunctionResponse(success=True, stdout="Reading package lists..."),
                FunctionResponse(success=True, stdout="Successfully installed gcc"),
            ]

            result = executor.dependency_installer.install_system_dependencies(
                ["gcc"], accelerate_downloads=True
            )

            assert result.success is True
            assert "Installed with nala" not in result.stdout

            # Verify all operations were called
            assert mock_subprocess.call_count == 3

    @pytest.mark.integration
    @patch("platform.system")
    def test_exception_handling_in_dependency_installation(self, mock_platform):
        """Test exception handling during dependency installation."""
        mock_platform.return_value = "Linux"
        executor = RemoteExecutor()

        with patch(
            "live_serverless.dependency_installer.run_logged_subprocess",
            side_effect=Exception("Subprocess error"),
        ):
            # Test Python dependency exception
            py_result = executor.dependency_installer.install_dependencies(
                ["some-package"]
            )
            assert py_result.success is False
            assert "Subprocess error" in py_result.error

            # Test system dependency exception
            sys_result = executor.dependency_installer.install_system_dependencies(
                ["some-package"]
            )
            assert sys_result.success is False
            assert "Subprocess error" in sys_result.error
