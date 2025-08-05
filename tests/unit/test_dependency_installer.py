"""Tests for DependencyInstaller component."""

from unittest.mock import Mock, patch

from dependency_installer import DependencyInstaller
from workspace_manager import WorkspaceManager
from constants import RUNPOD_VOLUME_PATH, VENV_DIR_NAME


class TestSystemDependencies:
    """Test system dependency installation."""

    def setup_method(self):
        """Setup for each test method."""
        self.workspace_manager = Mock(spec=WorkspaceManager)
        self.installer = DependencyInstaller(self.workspace_manager)

    @patch("subprocess.Popen")
    def test_install_system_dependencies_success(self, mock_popen):
        """Test successful system dependency installation."""
        # Mock apt-get update
        update_process = Mock()
        update_process.returncode = 0
        update_process.communicate.return_value = (b"Updated", b"")

        # Mock apt-get install
        install_process = Mock()
        install_process.returncode = 0
        install_process.communicate.return_value = (b"Installed packages", b"")

        mock_popen.side_effect = [update_process, install_process]

        result = self.installer.install_system_dependencies(["curl", "wget"])

        assert result.success is True
        assert "Installed packages" in result.stdout
        assert mock_popen.call_count == 2

    @patch("subprocess.Popen")
    def test_install_system_dependencies_update_failure(self, mock_popen):
        """Test system dependency installation with update failure."""
        update_process = Mock()
        update_process.returncode = 1
        update_process.communicate.return_value = (b"", b"Update failed")

        mock_popen.return_value = update_process

        result = self.installer.install_system_dependencies(["curl"])

        assert result.success is False
        assert "Error updating package list" in result.error

    def test_install_system_dependencies_empty_list(self):
        """Test system dependency installation with empty package list."""
        result = self.installer.install_system_dependencies([])

        assert result.success is True
        assert "No system packages to install" in result.stdout


class TestPythonDependencies:
    """Test Python dependency installation."""

    def setup_method(self):
        """Setup for each test method."""
        self.workspace_manager = Mock(spec=WorkspaceManager)
        self.workspace_manager.has_runpod_volume = False
        self.workspace_manager.venv_path = None
        self.installer = DependencyInstaller(self.workspace_manager)

    @patch("subprocess.Popen")
    @patch("importlib.invalidate_caches")
    def test_install_dependencies_success(self, mock_invalidate, mock_popen):
        """Test successful Python dependency installation."""
        process = Mock()
        process.returncode = 0
        process.communicate.return_value = (b"Successfully installed", b"")
        mock_popen.return_value = process

        result = self.installer.install_dependencies(["requests", "numpy"])

        assert result.success is True
        assert "Successfully installed" in result.stdout
        mock_invalidate.assert_called_once()

    @patch("subprocess.Popen")
    def test_install_dependencies_failure(self, mock_popen):
        """Test Python dependency installation failure."""
        process = Mock()
        process.returncode = 1
        process.communicate.return_value = (b"", b"Package not found")
        mock_popen.return_value = process

        result = self.installer.install_dependencies(["nonexistent-package"])

        assert result.success is False
        assert "Error installing packages" in result.error

    def test_install_dependencies_empty_list(self):
        """Test Python dependency installation with empty package list."""
        result = self.installer.install_dependencies([])

        assert result.success is True
        assert "No packages to install" in result.stdout


class TestDifferentialInstallation:
    """Test differential package installation with volume."""

    def setup_method(self):
        """Setup for each test method."""
        self.workspace_manager = Mock(spec=WorkspaceManager)
        self.workspace_manager.has_runpod_volume = True
        self.workspace_manager.venv_path = f"{RUNPOD_VOLUME_PATH}/{VENV_DIR_NAME}"
        self.installer = DependencyInstaller(self.workspace_manager)

    @patch("os.path.exists")
    @patch("subprocess.Popen")
    def test_get_installed_packages(self, mock_popen, mock_exists):
        """Test getting list of installed packages."""
        mock_exists.return_value = True

        process = Mock()
        process.returncode = 0
        process.communicate.return_value = (b"numpy==1.21.0\npandas==1.3.0\n", b"")
        mock_popen.return_value = process

        packages = self.installer._get_installed_packages()

        assert packages == {"numpy": "1.21.0", "pandas": "1.3.0"}

    @patch("os.path.exists")
    def test_get_installed_packages_no_venv(self, mock_exists):
        """Test getting installed packages with no virtual environment."""
        mock_exists.return_value = False

        packages = self.installer._get_installed_packages()

        assert packages == {}

    def test_filter_packages_to_install(self):
        """Test filtering packages that need installation."""
        installed = {"numpy": "1.21.0", "pandas": "1.3.0"}
        requested = ["numpy==1.21.0", "pandas==1.4.0", "requests"]

        filtered = self.installer._filter_packages_to_install(requested, installed)

        # Should install pandas (different version) and requests (not installed)
        assert "numpy==1.21.0" not in filtered  # Same version, skip
        assert "pandas==1.4.0" in filtered  # Different version, install
        assert "requests" in filtered  # Not installed, install

    @patch("os.path.exists")
    @patch("subprocess.Popen")
    def test_skip_already_installed_packages(self, mock_popen, mock_exists):
        """Test that already installed packages are skipped."""
        mock_exists.return_value = True

        # Mock getting installed packages
        list_process = Mock()
        list_process.returncode = 0
        list_process.communicate.return_value = (b"numpy==1.21.0\n", b"")

        # No install process should be called since all packages are installed
        mock_popen.return_value = list_process

        with patch.object(
            self.installer, "_get_installed_packages", return_value={"numpy": "1.21.0"}
        ):
            result = self.installer.install_dependencies(["numpy==1.21.0"])

        assert result.success is True
        assert "All packages already installed" in result.stdout
