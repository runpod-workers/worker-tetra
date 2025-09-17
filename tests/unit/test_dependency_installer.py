"""Tests for DependencyInstaller component."""

import subprocess
from unittest.mock import Mock, patch

from dependency_installer import DependencyInstaller
from workspace_manager import WorkspaceManager


class TestSystemDependencies:
    """Test system dependency installation."""

    def setup_method(self):
        """Setup for each test method."""
        self.workspace_manager = Mock(spec=WorkspaceManager)
        self.installer = DependencyInstaller(self.workspace_manager)

    @patch("platform.system")
    @patch("subprocess.Popen")
    def test_install_system_dependencies_success(self, mock_popen, mock_platform):
        """Test successful system dependency installation with small packages (no nala acceleration)."""
        mock_platform.return_value = "Linux"
        # Mock apt-get update
        update_process = Mock()
        update_process.returncode = 0
        update_process.communicate.return_value = (b"Updated", b"")

        # Mock apt-get install
        install_process = Mock()
        install_process.returncode = 0
        install_process.communicate.return_value = (b"Installed packages", b"")

        mock_popen.side_effect = [update_process, install_process]

        # Use small packages that won't trigger nala acceleration
        result = self.installer.install_system_dependencies(["nano", "vim"])

        assert result.success is True
        assert "Installed packages" in result.stdout
        assert mock_popen.call_count == 2

    @patch("platform.system")
    @patch("subprocess.Popen")
    def test_install_system_dependencies_update_failure(
        self, mock_popen, mock_platform
    ):
        """Test system dependency installation with update failure."""
        mock_platform.return_value = "Linux"
        update_process = Mock()
        update_process.returncode = 1
        update_process.communicate.return_value = (b"", b"Update failed")

        mock_popen.return_value = update_process

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
        self.workspace_manager = Mock(spec=WorkspaceManager)
        self.installer = DependencyInstaller(self.workspace_manager)

    @patch("subprocess.Popen")
    def test_nala_availability_check_available(self, mock_popen):
        """Test nala availability detection when nala is available."""
        process = Mock()
        process.returncode = 0
        process.communicate.return_value = (b"/usr/bin/nala", b"")
        mock_popen.return_value = process

        # First call should check availability
        assert self.installer._check_nala_available() is True

        # Second call should use cached result
        assert self.installer._check_nala_available() is True

        # Should only call subprocess once due to caching
        assert mock_popen.call_count == 1

    @patch("subprocess.Popen")
    def test_nala_availability_check_unavailable(self, mock_popen):
        """Test nala availability detection when nala is not available."""
        process = Mock()
        process.returncode = 1
        process.communicate.return_value = (b"", b"which: nala: not found")
        mock_popen.return_value = process

        assert self.installer._check_nala_available() is False

    @patch("subprocess.Popen")
    def test_nala_availability_check_exception(self, mock_popen):
        """Test nala availability detection when subprocess raises exception."""
        mock_popen.side_effect = Exception("Command failed")

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

    @patch("subprocess.Popen")
    def test_install_system_with_nala_success(self, mock_popen):
        """Test successful system package installation with nala."""
        # Mock nala update
        update_process = Mock()
        update_process.returncode = 0
        update_process.communicate.return_value = (b"Updated with nala", b"")

        # Mock nala install
        install_process = Mock()
        install_process.returncode = 0
        install_process.communicate.return_value = (b"Installed with nala", b"")

        mock_popen.side_effect = [update_process, install_process]

        result = self.installer._install_system_with_nala(["build-essential"])

        assert result.success is True
        assert "Installed with nala" in result.stdout
        assert mock_popen.call_count == 2

    @patch("subprocess.Popen")
    def test_install_system_with_nala_update_failure_fallback(self, mock_popen):
        """Test nala installation fallback when update fails."""
        # Mock failed nala update
        update_process = Mock()
        update_process.returncode = 1
        update_process.communicate.return_value = (b"", b"Update failed")

        # Mock successful apt-get operations for fallback
        apt_update_process = Mock()
        apt_update_process.returncode = 0
        apt_update_process.communicate.return_value = (b"Updated", b"")

        apt_install_process = Mock()
        apt_install_process.returncode = 0
        apt_install_process.communicate.return_value = (b"Installed", b"")

        mock_popen.side_effect = [
            update_process,
            apt_update_process,
            apt_install_process,
        ]

        result = self.installer._install_system_with_nala(["build-essential"])

        assert result.success is True
        assert "Installed with nala" not in result.stdout

    @patch("platform.system")
    @patch("subprocess.Popen")
    def test_install_system_dependencies_with_acceleration(
        self, mock_popen, mock_platform
    ):
        """Test system dependency installation with acceleration enabled."""
        mock_platform.return_value = "Linux"
        # Mock nala availability check
        nala_check = Mock()
        nala_check.returncode = 0
        nala_check.communicate.return_value = (b"/usr/bin/nala", b"")

        # Mock nala operations
        nala_update = Mock()
        nala_update.returncode = 0
        nala_update.communicate.return_value = (b"Updated", b"")

        nala_install = Mock()
        nala_install.returncode = 0
        nala_install.communicate.return_value = (b"Installed with nala", b"")

        mock_popen.side_effect = [nala_check, nala_update, nala_install]

        result = self.installer.install_system_dependencies(
            ["build-essential", "python3-dev"], accelerate_downloads=True
        )

        assert result.success is True
        assert "Installed with nala" in result.stdout

    @patch("subprocess.Popen")
    def test_install_system_dependencies_without_acceleration(self, mock_popen):
        """Test system dependency installation with acceleration disabled."""
        # Mock apt-get operations
        apt_update = Mock()
        apt_update.returncode = 0
        apt_update.communicate.return_value = (b"Updated", b"")

        apt_install = Mock()
        apt_install.returncode = 0
        apt_install.communicate.return_value = (b"Installed", b"")

        mock_popen.side_effect = [apt_update, apt_install]

        result = self.installer.install_system_dependencies(
            ["build-essential"], accelerate_downloads=False
        )

        assert result.success is True
        assert "Installed with nala" not in result.stdout

    @patch("subprocess.Popen")
    def test_install_system_dependencies_no_large_packages(self, mock_popen):
        """Test system dependency installation when no large packages are present."""
        # Mock apt-get operations (should fallback to standard)
        apt_update = Mock()
        apt_update.returncode = 0
        apt_update.communicate.return_value = (b"Updated", b"")

        apt_install = Mock()
        apt_install.returncode = 0
        apt_install.communicate.return_value = (b"Installed", b"")

        mock_popen.side_effect = [apt_update, apt_install]

        result = self.installer.install_system_dependencies(
            ["nano", "vim"], accelerate_downloads=True
        )

        assert result.success is True
        assert "Installed with nala" not in result.stdout


class TestPythonDependencies:
    """Test Python dependency installation."""

    def setup_method(self):
        """Setup for each test method."""
        self.workspace_manager = Mock(spec=WorkspaceManager)
        self.workspace_manager.has_runpod_volume = False
        self.workspace_manager.cache_path = None
        self.installer = DependencyInstaller(self.workspace_manager)

    @patch("subprocess.Popen")
    def test_install_dependencies_success(self, mock_popen):
        """Test successful Python dependency installation."""
        process = Mock()
        process.returncode = 0
        process.communicate.return_value = ("Successfully installed", "")
        mock_popen.return_value = process

        result = self.installer.install_dependencies(["requests", "numpy"])

        assert result.success is True
        assert "Successfully installed" in result.stdout
        # Verify UV was called with correct command
        mock_popen.assert_called_once()
        args = mock_popen.call_args[0][0]
        assert args[:4] == ["uv", "pip", "install", "--system"]
        assert "requests" in args
        assert "numpy" in args

    @patch("subprocess.Popen")
    def test_install_dependencies_failure(self, mock_popen):
        """Test Python dependency installation failure."""
        process = Mock()
        process.returncode = 1
        process.communicate.return_value = ("", "Package not found")
        mock_popen.return_value = process

        result = self.installer.install_dependencies(["nonexistent-package"])

        assert result.success is False
        assert result.error == "Package not found"

    def test_install_dependencies_empty_list(self):
        """Test Python dependency installation with empty package list."""
        result = self.installer.install_dependencies([])

        assert result.success is True
        assert "No packages to install" in result.stdout

    @patch("subprocess.Popen")
    def test_install_dependencies_with_acceleration_enabled(self, mock_popen):
        """Test Python dependency installation with acceleration enabled (uses UV)."""
        process = Mock()
        process.returncode = 0
        process.communicate.return_value = ("Successfully installed with UV", "")
        mock_popen.return_value = process

        result = self.installer.install_dependencies(
            ["requests", "numpy"], accelerate_downloads=True
        )

        assert result.success is True
        assert "Successfully installed with UV" in result.stdout
        # Verify UV was called with correct command
        mock_popen.assert_called_once()
        args = mock_popen.call_args[0][0]
        assert args[:4] == ["uv", "pip", "install", "--system"]
        assert "requests" in args
        assert "numpy" in args

    @patch("subprocess.Popen")
    def test_install_dependencies_with_acceleration_disabled(self, mock_popen):
        """Test Python dependency installation with acceleration disabled (uses pip)."""
        process = Mock()
        process.returncode = 0
        process.communicate.return_value = ("Successfully installed with pip", "")
        mock_popen.return_value = process

        result = self.installer.install_dependencies(
            ["requests", "numpy"], accelerate_downloads=False
        )

        assert result.success is True
        assert "Successfully installed with pip" in result.stdout
        # Verify pip was called with correct command
        mock_popen.assert_called_once()
        args = mock_popen.call_args[0][0]
        assert args[:2] == ["pip", "install"]
        assert "requests" in args
        assert "numpy" in args

    @patch("subprocess.Popen")
    def test_install_dependencies_exception(self, mock_popen):
        """Test Python dependency installation exception handling."""
        mock_popen.side_effect = Exception("Subprocess error")

        result = self.installer.install_dependencies(["some-package"])

        assert result.success is False
        assert "Subprocess error" in result.error

    @patch("subprocess.Popen")
    def test_install_dependencies_timeout(self, mock_popen):
        """Test Python dependency installation timeout handling."""
        process = Mock()
        process.communicate.side_effect = subprocess.TimeoutExpired("cmd", 300)
        mock_popen.return_value = process

        result = self.installer.install_dependencies(["some-package"])

        assert result.success is False
        assert "timed out after 300 seconds" in result.error
        process.kill.assert_called_once()
