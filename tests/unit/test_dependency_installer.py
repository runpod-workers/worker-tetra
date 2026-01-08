"""Tests for DependencyInstaller component."""

from unittest.mock import patch

from dependency_installer import DependencyInstaller
from remote_execution import FunctionResponse


class TestSystemDependencies:
    """Test system dependency installation."""

    def setup_method(self):
        """Setup for each test method."""
        self.installer = DependencyInstaller()

    @patch("platform.system")
    @patch("dependency_installer.run_logged_subprocess")
    def test_install_system_dependencies_success(self, mock_subprocess, mock_platform):
        """Test successful system dependency installation with small packages (no nala acceleration)."""
        mock_platform.return_value = "Linux"

        # Mock successful responses for apt-get update and install
        mock_subprocess.side_effect = [
            FunctionResponse(success=True, stdout="Updated"),
            FunctionResponse(success=True, stdout="Installed packages"),
        ]

        # Use small packages that won't trigger nala acceleration
        result = self.installer.install_system_dependencies(["nano", "vim"])

        assert result.success is True
        assert "Installed packages" in result.stdout
        assert mock_subprocess.call_count == 2

    @patch("platform.system")
    @patch("dependency_installer.run_logged_subprocess")
    def test_install_system_dependencies_update_failure(
        self, mock_subprocess, mock_platform
    ):
        """Test system dependency installation with update failure."""
        mock_platform.return_value = "Linux"

        # Mock failed apt-get update
        mock_subprocess.return_value = FunctionResponse(
            success=False, error="Update failed"
        )

        result = self.installer.install_system_dependencies(["curl"])

        assert result.success is False
        assert "Error updating package list" in result.error

    @patch("platform.system")
    def test_install_system_dependencies_empty_list(self, mock_platform):
        """Test system dependency installation with empty package list."""
        mock_platform.return_value = "Linux"
        result = self.installer.install_system_dependencies([])

        assert result.success is True
        assert "No system packages to install" in result.stdout


class TestSystemPackageAcceleration:
    """Test system package acceleration with nala."""

    def setup_method(self):
        """Setup for each test method."""
        self.installer = DependencyInstaller()

    @patch("dependency_installer.run_logged_subprocess")
    def test_nala_availability_check_available(self, mock_subprocess):
        """Test nala availability detection when nala is available."""
        mock_subprocess.return_value = FunctionResponse(
            success=True, stdout="/usr/bin/nala"
        )

        # First call should check availability
        assert self.installer._check_nala_available() is True

        # Second call should use cached result
        assert self.installer._check_nala_available() is True

        # Should only call subprocess once due to caching
        assert mock_subprocess.call_count == 1

    @patch("dependency_installer.run_logged_subprocess")
    def test_nala_availability_check_unavailable(self, mock_subprocess):
        """Test nala availability detection when nala is not available."""
        mock_subprocess.return_value = FunctionResponse(
            success=False, error="which: nala: not found"
        )

        assert self.installer._check_nala_available() is False

    @patch("dependency_installer.run_logged_subprocess")
    def test_nala_availability_check_exception(self, mock_subprocess):
        """Test nala availability detection when subprocess raises exception."""
        mock_subprocess.side_effect = Exception("Command failed")

        assert self.installer._check_nala_available() is False

    def test_identify_large_system_packages(self):
        """Test identification of large system packages."""
        packages = ["build-essential", "curl", "python3-dev", "nano", "gcc"]
        large_packages = self.installer._identify_large_system_packages(packages)

        expected = ["build-essential", "curl", "python3-dev", "gcc"]
        assert set(large_packages) == set(expected)

    def test_identify_large_system_packages_empty(self):
        """Test identification when no large packages are present."""
        packages = ["nano", "vim", "htop"]
        large_packages = self.installer._identify_large_system_packages(packages)

        assert large_packages == []

    @patch("dependency_installer.run_logged_subprocess")
    def test_install_system_with_nala_success(self, mock_subprocess):
        """Test successful system package installation with nala."""
        # Mock successful nala update and install
        mock_subprocess.side_effect = [
            FunctionResponse(success=True, stdout="Updated with nala"),
            FunctionResponse(success=True, stdout="Installed with nala"),
        ]

        result = self.installer._install_system_with_nala(["build-essential"])

        assert result.success is True
        assert "Installed with nala" in result.stdout
        assert mock_subprocess.call_count == 2

    @patch("dependency_installer.run_logged_subprocess")
    def test_install_system_with_nala_update_failure_fallback(self, mock_subprocess):
        """Test nala installation fallback when update fails."""
        # Mock failed nala update, then successful apt-get operations for fallback
        mock_subprocess.side_effect = [
            FunctionResponse(success=False, error="Update failed"),
            FunctionResponse(success=True, stdout="Updated"),
            FunctionResponse(success=True, stdout="Installed"),
        ]

        result = self.installer._install_system_with_nala(["build-essential"])

        assert result.success is True
        assert "Installed with nala" not in result.stdout

    @patch("platform.system")
    @patch("dependency_installer.run_logged_subprocess")
    def test_install_system_dependencies_with_acceleration(
        self, mock_subprocess, mock_platform
    ):
        """Test system dependency installation with acceleration enabled."""
        mock_platform.return_value = "Linux"

        # Mock nala availability check and operations
        mock_subprocess.side_effect = [
            FunctionResponse(success=True, stdout="/usr/bin/nala"),
            FunctionResponse(success=True, stdout="Updated"),
            FunctionResponse(success=True, stdout="Installed with nala"),
        ]

        result = self.installer.install_system_dependencies(
            ["build-essential", "python3-dev"], accelerate_downloads=True
        )

        assert result.success is True
        assert "Installed with nala" in result.stdout

    @patch("dependency_installer.run_logged_subprocess")
    def test_install_system_dependencies_without_acceleration(self, mock_subprocess):
        """Test system dependency installation with acceleration disabled."""
        # Mock successful apt-get operations
        mock_subprocess.side_effect = [
            FunctionResponse(success=True, stdout="Updated"),
            FunctionResponse(success=True, stdout="Installed"),
        ]

        result = self.installer.install_system_dependencies(
            ["build-essential"], accelerate_downloads=False
        )

        assert result.success is True
        assert "Installed with nala" not in result.stdout

    @patch("dependency_installer.run_logged_subprocess")
    def test_install_system_dependencies_no_large_packages(self, mock_subprocess):
        """Test system dependency installation when no large packages are present."""
        # Mock successful apt-get operations (should fallback to standard)
        mock_subprocess.side_effect = [
            FunctionResponse(success=True, stdout="Updated"),
            FunctionResponse(success=True, stdout="Installed"),
        ]

        result = self.installer.install_system_dependencies(
            ["nano", "vim"], accelerate_downloads=True
        )

        assert result.success is True
        assert "Installed with nala" not in result.stdout


class TestPythonDependencies:
    """Test Python dependency installation."""

    def setup_method(self):
        """Setup for each test method."""
        self.installer = DependencyInstaller()

    @patch("dependency_installer.run_logged_subprocess")
    def test_install_dependencies_success(self, mock_subprocess):
        """Test successful Python dependency installation."""
        mock_subprocess.return_value = FunctionResponse(
            success=True, stdout="Successfully installed"
        )

        # Use a package that's unlikely to be installed
        result = self.installer.install_dependencies(["nonexistent-test-package-12345"])

        assert result.success is True
        assert "Successfully installed" in result.stdout
        # Verify subprocess utility was called
        mock_subprocess.assert_called_once()

    @patch("dependency_installer.run_logged_subprocess")
    def test_install_dependencies_failure(self, mock_subprocess):
        """Test Python dependency installation failure."""
        mock_subprocess.return_value = FunctionResponse(
            success=False, error="Package not found"
        )

        result = self.installer.install_dependencies(["nonexistent-package"])

        assert result.success is False
        assert result.error == "Package not found"

    def test_install_dependencies_empty_list(self):
        """Test Python dependency installation with empty package list."""
        result = self.installer.install_dependencies([])

        assert result.success is True
        assert "No packages to install" in result.stdout

    @patch("dependency_installer.run_logged_subprocess")
    def test_install_dependencies_with_acceleration_enabled(self, mock_subprocess):
        """Test Python dependency installation with acceleration enabled (uses UV)."""
        mock_subprocess.return_value = FunctionResponse(
            success=True, stdout="Successfully installed with UV"
        )

        # Use a package that's unlikely to be installed
        result = self.installer.install_dependencies(
            ["nonexistent-test-package-uv-12345"], accelerate_downloads=True
        )

        assert result.success is True
        assert "Successfully installed with UV" in result.stdout
        # Verify subprocess utility was called
        mock_subprocess.assert_called_once()

    @patch("dependency_installer.run_logged_subprocess")
    def test_install_dependencies_with_acceleration_disabled(self, mock_subprocess):
        """Test Python dependency installation with acceleration disabled (uses pip)."""
        mock_subprocess.return_value = FunctionResponse(
            success=True, stdout="Successfully installed with pip"
        )

        # Use a package that's unlikely to be installed
        result = self.installer.install_dependencies(
            ["nonexistent-test-package-pip-12345"], accelerate_downloads=False
        )

        assert result.success is True
        assert "Successfully installed with pip" in result.stdout
        # Verify subprocess utility was called
        mock_subprocess.assert_called_once()

    @patch("dependency_installer.run_logged_subprocess")
    def test_install_dependencies_exception(self, mock_subprocess):
        """Test Python dependency installation exception handling."""
        mock_subprocess.side_effect = Exception("Subprocess error")

        result = self.installer.install_dependencies(["some-package"])

        assert result.success is False
        assert "Subprocess error" in result.error

    @patch("dependency_installer.run_logged_subprocess")
    def test_install_dependencies_timeout(self, mock_subprocess):
        """Test Python dependency installation timeout handling."""
        mock_subprocess.return_value = FunctionResponse(
            success=False, error="Command timed out after 300 seconds"
        )

        result = self.installer.install_dependencies(["some-package"])

        assert result.success is False
        assert "timed out after 300 seconds" in result.error


class TestCompilationAutoRetry:
    """Test automatic build-essential installation when compilation needed."""

    def setup_method(self):
        """Setup for each test method."""
        self.installer = DependencyInstaller()

    def test_needs_compilation_gcc_not_found(self):
        """Test detection of missing gcc compiler."""
        result = FunctionResponse(
            success=False,
            error="error: command 'gcc' failed: No such file or directory",
        )

        assert self.installer._needs_compilation(result) is True

    def test_needs_compilation_unable_to_execute_gcc(self):
        """Test detection of unable to execute gcc."""
        result = FunctionResponse(
            success=False,
            error="unable to execute 'gcc': No such file or directory",
        )

        assert self.installer._needs_compilation(result) is True

    def test_needs_compilation_distutils_error(self):
        """Test detection of distutils compilation errors."""
        result = FunctionResponse(
            success=False,
            error="distutils.errors.CompileError: command 'gcc' failed",
        )

        assert self.installer._needs_compilation(result) is True

    def test_needs_compilation_cc_command_failed(self):
        """Test detection of cc command failure."""
        result = FunctionResponse(
            success=False, stdout="error: command 'cc' failed with exit code 1"
        )

        assert self.installer._needs_compilation(result) is True

    def test_needs_compilation_gxx_missing(self):
        """Test detection of missing g++ compiler."""
        result = FunctionResponse(
            success=False, error="unable to execute 'g++': No such file or directory"
        )

        assert self.installer._needs_compilation(result) is True

    def test_needs_compilation_false_for_unrelated_error(self):
        """Test that unrelated errors don't trigger compilation detection."""
        result = FunctionResponse(
            success=False, error="Network error: Could not find package"
        )

        assert self.installer._needs_compilation(result) is False

    def test_needs_compilation_false_for_success(self):
        """Test that successful installations don't trigger compilation detection."""
        result = FunctionResponse(success=True, stdout="Successfully installed")

        assert self.installer._needs_compilation(result) is False

    @patch("platform.system")
    @patch("dependency_installer.run_logged_subprocess")
    def test_auto_retry_installs_build_essential_on_gcc_error(
        self, mock_subprocess, mock_platform
    ):
        """Test auto-retry automatically installs build-essential when gcc missing."""
        mock_platform.return_value = "Linux"

        # First call: pip install fails with gcc error
        # Second call: nala check (not available)
        # Third call: apt-get update
        # Fourth call: apt-get install build-essential
        # Fifth call: pip install retry (succeeds)
        mock_subprocess.side_effect = [
            FunctionResponse(
                success=False, error="error: command 'gcc' failed: No such file"
            ),
            FunctionResponse(success=False),  # nala not available
            FunctionResponse(success=True, stdout="Updated"),  # apt-get update
            FunctionResponse(
                success=True, stdout="Installed build-essential"
            ),  # apt-get install
            FunctionResponse(success=True, stdout="Successfully installed package"),
        ]

        result = self.installer.install_dependencies(["some-package-needing-gcc"])

        assert result.success is True
        assert "Successfully installed package" in result.stdout
        assert mock_subprocess.call_count == 5

    @patch("dependency_installer.run_logged_subprocess")
    def test_auto_retry_no_retry_for_non_compilation_errors(self, mock_subprocess):
        """Test that non-compilation errors don't trigger auto-retry."""
        # Pip install fails with network error (not compilation related)
        mock_subprocess.return_value = FunctionResponse(
            success=False, error="Network error: Could not fetch package"
        )

        result = self.installer.install_dependencies(["some-package"])

        assert result.success is False
        assert "Network error" in result.error
        # Should only be called once (no retry)
        assert mock_subprocess.call_count == 1

    @patch("platform.system")
    @patch("dependency_installer.run_logged_subprocess")
    def test_auto_retry_fails_if_build_essential_install_fails(
        self, mock_subprocess, mock_platform
    ):
        """Test that if build-essential installation fails, the error is returned."""
        mock_platform.return_value = "Linux"

        # First call: pip install fails with gcc error
        # Second call: nala check (not available)
        # Third call: apt-get update (fails)
        mock_subprocess.side_effect = [
            FunctionResponse(
                success=False, error="error: command 'gcc' failed: No such file"
            ),
            FunctionResponse(success=False),  # nala not available
            FunctionResponse(success=False, error="apt-get update failed"),
        ]

        result = self.installer.install_dependencies(["some-package-needing-gcc"])

        assert result.success is False
        assert "Failed to install build tools" in result.error

    @patch("platform.system")
    @patch("dependency_installer.run_logged_subprocess")
    def test_auto_retry_with_nala_acceleration(self, mock_subprocess, mock_platform):
        """Test auto-retry uses nala when available for build-essential installation."""
        mock_platform.return_value = "Linux"

        # First call: pip install fails with gcc error
        # Second call: nala check (available)
        # Third call: nala update
        # Fourth call: nala install build-essential
        # Fifth call: pip install retry (succeeds)
        mock_subprocess.side_effect = [
            FunctionResponse(
                success=False, error="error: command 'gcc' failed: No such file"
            ),
            FunctionResponse(success=True, stdout="/usr/bin/nala"),  # nala available
            FunctionResponse(success=True, stdout="Updated with nala"),
            FunctionResponse(
                success=True, stdout="Installed build-essential with nala"
            ),
            FunctionResponse(success=True, stdout="Successfully installed package"),
        ]

        result = self.installer.install_dependencies(["some-package-needing-gcc"])

        assert result.success is True
        assert "Successfully installed package" in result.stdout
        assert mock_subprocess.call_count == 5

    @patch("platform.system")
    @patch("dependency_installer.run_logged_subprocess")
    def test_auto_retry_succeeds_with_warnings_no_infinite_loop(
        self, mock_subprocess, mock_platform
    ):
        """Test that warnings mentioning gcc in retry output don't trigger another retry."""
        mock_platform.return_value = "Linux"

        # First call: pip install fails with gcc error
        # Second call: nala check (not available)
        # Third call: apt-get update
        # Fourth call: apt-get install build-essential
        # Fifth call: pip install retry (succeeds but has warning mentioning gcc)
        mock_subprocess.side_effect = [
            FunctionResponse(
                success=False,
                error="error: command 'gcc' failed: No such file or directory",
            ),
            FunctionResponse(success=False),  # nala not available
            FunctionResponse(success=True, stdout="Updated"),  # apt-get update
            FunctionResponse(
                success=True, stdout="Installed build-essential"
            ),  # apt-get install
            FunctionResponse(
                success=True,
                stdout="Successfully installed package\nWarning: gcc was used for compilation",
            ),
        ]

        result = self.installer.install_dependencies(["some-package-needing-gcc"])

        assert result.success is True
        assert "Successfully installed package" in result.stdout
        assert "Warning: gcc was used" in result.stdout
        # Should only be called 5 times (no infinite retry loop)
        assert mock_subprocess.call_count == 5
