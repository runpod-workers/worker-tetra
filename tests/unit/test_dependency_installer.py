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
