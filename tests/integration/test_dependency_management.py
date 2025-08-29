import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from remote_executor import RemoteExecutor
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

            result = executor.dependency_installer.install_dependencies(
                ["requests", "numpy"]
            )

            assert result.success is True
            assert "Successfully installed" in result.stdout

            # Verify correct command was called
            mock_popen.assert_called_once()
            call_args = mock_popen.call_args
            assert call_args[0][0] == [
                "uv",
                "pip",
                "install",
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

            result = executor.dependency_installer.install_system_dependencies(
                ["curl", "wget"], accelerate_downloads=False
            )

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
            from remote_execution import FunctionResponse

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

        with patch("subprocess.Popen") as mock_popen:
            # Mock failed installation
            mock_process = MagicMock()
            mock_process.returncode = 1
            mock_process.communicate.return_value = (
                b"",
                b"E: Unable to locate package nonexistent-package",
            )
            mock_popen.return_value = mock_process

            result = executor.dependency_installer.install_dependencies(
                ["nonexistent-package"]
            )

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

            result = executor.dependency_installer.install_system_dependencies(
                ["curl"], accelerate_downloads=False
            )

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
            from remote_execution import FunctionResponse

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
    def test_empty_dependency_lists(self):
        """Test handling of empty dependency lists."""
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
    def test_dependency_command_construction(self):
        """Test that dependency installation commands are constructed correctly."""
        executor = RemoteExecutor()

        with patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.returncode = 0
            mock_process.communicate.return_value = (b"success", b"")
            mock_popen.return_value = mock_process

            # Test Python dependency command
            executor.dependency_installer.install_dependencies(
                ["package1", "package2>=1.0.0"]
            )

            py_call = mock_popen.call_args
            expected_cmd = [
                "uv",
                "pip",
                "install",
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
            executor.dependency_installer.install_system_dependencies(
                ["pkg1", "pkg2"], accelerate_downloads=False
            )

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
            py_result = executor.dependency_installer.install_dependencies(
                ["some-package"]
            )
            assert py_result.success is False
            assert "Exception during package installation" in py_result.error
            assert "Subprocess error" in py_result.error

            # Test system dependency exception
            sys_result = executor.dependency_installer.install_system_dependencies(
                ["some-package"], accelerate_downloads=False
            )
            assert sys_result.success is False
            assert "Exception during system package installation" in sys_result.error
            assert "Subprocess error" in sys_result.error

    @pytest.mark.integration
    def test_system_dependency_installation_with_nala_acceleration(self):
        """Test system dependency installation with nala acceleration enabled."""
        executor = RemoteExecutor()

        with patch("subprocess.Popen") as mock_popen:
            # Mock nala availability check
            nala_check = MagicMock()
            nala_check.returncode = 0
            nala_check.communicate.return_value = (b"/usr/bin/nala", b"")

            # Mock nala update
            nala_update = MagicMock()
            nala_update.returncode = 0
            nala_update.communicate.return_value = (b"Reading package lists...", b"")

            # Mock nala install
            nala_install = MagicMock()
            nala_install.returncode = 0
            nala_install.communicate.return_value = (
                b"Successfully installed build-essential",
                b"",
            )

            mock_popen.side_effect = [nala_check, nala_update, nala_install]

            result = executor.dependency_installer.install_system_dependencies(
                ["build-essential"], accelerate_downloads=True
            )

            assert result.success is True
            assert "Installed with nala" in result.stdout

            # Verify nala commands were used
            calls = mock_popen.call_args_list
            assert len(calls) == 3
            assert calls[0][0][0] == ["which", "nala"]  # Availability check
            assert calls[1][0][0] == ["nala", "update"]  # Update
            assert calls[2][0][0] == [
                "nala",
                "install",
                "-y",
                "build-essential",
            ]  # Install

    @pytest.mark.integration
    def test_system_dependency_installation_nala_fallback(self):
        """Test system dependency installation fallback when nala fails."""
        executor = RemoteExecutor()

        with patch("subprocess.Popen") as mock_popen:
            # Mock nala availability check
            nala_check = MagicMock()
            nala_check.returncode = 0
            nala_check.communicate.return_value = (b"/usr/bin/nala", b"")

            # Mock nala update failure
            nala_update = MagicMock()
            nala_update.returncode = 1
            nala_update.communicate.return_value = (b"", b"nala update failed")

            # Mock successful apt-get fallback
            apt_update = MagicMock()
            apt_update.returncode = 0
            apt_update.communicate.return_value = (b"Reading package lists...", b"")

            apt_install = MagicMock()
            apt_install.returncode = 0
            apt_install.communicate.return_value = (
                b"Successfully installed python3-dev",
                b"",
            )

            mock_popen.side_effect = [nala_check, nala_update, apt_update, apt_install]

            result = executor.dependency_installer.install_system_dependencies(
                ["python3-dev"], accelerate_downloads=True
            )

            assert result.success is True
            assert "Installed with nala" not in result.stdout

            # Verify fallback to apt-get was used
            calls = mock_popen.call_args_list
            assert len(calls) == 4
            assert calls[2][0][0] == ["apt-get", "update"]  # apt-get update
            assert calls[3][0][0] == [
                "apt-get",
                "install",
                "-y",
                "--no-install-recommends",
                "python3-dev",
            ]

    @pytest.mark.integration
    def test_system_dependency_installation_no_nala_available(self):
        """Test system dependency installation when nala is not available."""
        executor = RemoteExecutor()

        with patch("subprocess.Popen") as mock_popen:
            # Mock nala not available
            nala_check = MagicMock()
            nala_check.returncode = 1
            nala_check.communicate.return_value = (b"", b"which: nala: not found")

            # Mock successful apt-get operations
            apt_update = MagicMock()
            apt_update.returncode = 0
            apt_update.communicate.return_value = (b"Reading package lists...", b"")

            apt_install = MagicMock()
            apt_install.returncode = 0
            apt_install.communicate.return_value = (b"Successfully installed gcc", b"")

            mock_popen.side_effect = [nala_check, apt_update, apt_install]

            result = executor.dependency_installer.install_system_dependencies(
                ["gcc"], accelerate_downloads=True
            )

            assert result.success is True
            assert "Installed with nala" not in result.stdout

            # Verify standard apt-get was used
            calls = mock_popen.call_args_list
            assert len(calls) == 3
            assert calls[1][0][0] == ["apt-get", "update"]
            assert calls[2][0][0] == [
                "apt-get",
                "install",
                "-y",
                "--no-install-recommends",
                "gcc",
            ]

    @pytest.mark.integration
    def test_system_dependency_installation_with_small_packages(self):
        """Test system dependency installation with small packages (no acceleration)."""
        executor = RemoteExecutor()

        with patch("subprocess.Popen") as mock_popen:
            # Mock apt-get operations (should be used for small packages)
            apt_update = MagicMock()
            apt_update.returncode = 0
            apt_update.communicate.return_value = (b"Reading package lists...", b"")

            apt_install = MagicMock()
            apt_install.returncode = 0
            apt_install.communicate.return_value = (b"Successfully installed nano", b"")

            mock_popen.side_effect = [apt_update, apt_install]

            result = executor.dependency_installer.install_system_dependencies(
                ["nano", "vim"], accelerate_downloads=True
            )

            assert result.success is True
            assert "Installed with nala" not in result.stdout

            # Should use apt-get because these are not large packages
            calls = mock_popen.call_args_list
            assert len(calls) == 2
            assert calls[0][0][0] == ["apt-get", "update"]
            assert calls[1][0][0] == [
                "apt-get",
                "install",
                "-y",
                "--no-install-recommends",
                "nano",
                "vim",
            ]
