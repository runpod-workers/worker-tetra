"""Tests for RunPod volume workspace functionality."""

import subprocess
import threading
from unittest.mock import Mock, patch, MagicMock

from handler import RemoteExecutor


class TestVolumeDetection:
    """Test detection of RunPod volume availability."""

    @patch("os.path.exists")
    def test_detects_runpod_volume_exists(self, mock_exists):
        """Test that executor detects when /runpod-volume exists."""
        mock_exists.return_value = True

        executor = RemoteExecutor()

        # This will fail until we implement volume detection
        assert hasattr(executor, "has_runpod_volume")
        assert executor.has_runpod_volume is True
        mock_exists.assert_called_with("/runpod-volume")

    @patch("os.path.exists")
    def test_detects_runpod_volume_missing(self, mock_exists):
        """Test fallback behavior when no volume is present."""
        mock_exists.return_value = False

        executor = RemoteExecutor()

        # This will fail until we implement volume detection
        assert hasattr(executor, "has_runpod_volume")
        assert executor.has_runpod_volume is False
        mock_exists.assert_called_with("/runpod-volume")

    @patch("os.path.exists")
    @patch("os.makedirs")
    @patch("fcntl.flock")
    @patch("builtins.open")
    @patch("subprocess.Popen")
    def test_workspace_initialization_creates_venv(
        self, mock_popen, mock_open, mock_flock, mock_makedirs, mock_exists
    ):
        """Test that first-time setup creates virtual environment."""
        mock_exists.side_effect = lambda path: path == "/runpod-volume"

        # Mock file operations
        mock_file = MagicMock()
        mock_file.fileno.return_value = 3  # Mock file descriptor
        mock_open.return_value.__enter__.return_value = mock_file

        # Mock successful uv venv creation
        mock_process = Mock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (b"Virtual environment created", b"")
        mock_popen.return_value = mock_process

        executor = RemoteExecutor()

        # This will fail until we implement workspace initialization
        result = executor.initialize_workspace()

        assert result.success is True
        mock_popen.assert_called_with(
            ["uv", "venv", "/runpod-volume/.venv"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )


class TestConcurrencySafety:
    """Test concurrent access safety mechanisms."""

    @patch("os.path.exists")
    @patch("fcntl.flock")
    @patch("builtins.open")
    @patch("os.makedirs")
    @patch("subprocess.Popen")
    def test_concurrent_workspace_initialization(
        self, mock_popen, mock_makedirs, mock_open, mock_flock, mock_exists
    ):
        """Test that multiple workers can safely initialize workspace."""

        # Mock that volume exists but venv doesn't initially
        def exists_side_effect(path):
            if path == "/runpod-volume":
                return True
            elif path == "/runpod-volume/.venv":
                return False  # Force initialization attempt
            return False

        mock_exists.side_effect = exists_side_effect

        # Mock file operations
        mock_file = MagicMock()
        mock_file.fileno.return_value = 3
        mock_open.return_value.__enter__.return_value = mock_file

        # Mock successful uv venv creation
        mock_process = Mock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (b"Virtual environment created", b"")
        mock_popen.return_value = mock_process

        # This will fail until we implement file locking
        executor1 = RemoteExecutor()
        executor2 = RemoteExecutor()

        results = []

        def init_workspace(executor, results_list):
            result = executor.initialize_workspace()
            results_list.append(result)

        # Start two threads trying to initialize simultaneously
        thread1 = threading.Thread(target=init_workspace, args=(executor1, results))
        thread2 = threading.Thread(target=init_workspace, args=(executor2, results))

        thread1.start()
        thread2.start()

        thread1.join()
        thread2.join()

        # Both should succeed, but only one should actually do the work
        assert len(results) == 2
        assert all(result.success for result in results)
        # flock should have been called to coordinate access
        assert mock_flock.called

    @patch("os.path.exists")
    @patch("os.makedirs")
    @patch("builtins.open")
    @patch("fcntl.flock")
    def test_lock_timeout_fallback(
        self, mock_flock, mock_open, mock_makedirs, mock_exists
    ):
        """Test graceful handling when lock acquisition times out."""

        # Mock that volume exists but venv doesn't exist initially
        def exists_side_effect(path):
            if path == "/runpod-volume":
                return True
            elif path == "/runpod-volume/.venv":
                return False  # Force initialization attempt
            return False

        mock_exists.side_effect = exists_side_effect
        mock_flock.side_effect = BlockingIOError("Resource temporarily unavailable")

        # Mock file operations
        mock_file = MagicMock()
        mock_file.fileno.return_value = 3
        mock_open.return_value.__enter__.return_value = mock_file

        executor = RemoteExecutor()

        # This will fail until we implement timeout handling
        result = executor.initialize_workspace(timeout=0.1)

        # Should fallback gracefully instead of crashing
        assert result.success is False
        assert "timeout" in result.error.lower()

    @patch("os.path.exists")
    @patch("fcntl.flock")
    @patch("builtins.open")
    @patch("os.makedirs")
    @patch("os.remove")
    def test_lock_cleanup_on_failure(
        self, mock_remove, mock_makedirs, mock_open, mock_flock, mock_exists
    ):
        """Test that locks are properly cleaned up when initialization fails."""

        # Mock that volume exists but venv doesn't exist initially, then lock file exists for cleanup
        def exists_side_effect(path):
            if path == "/runpod-volume":
                return True
            elif path == "/runpod-volume/.venv":
                return False  # Force initialization attempt
            elif path == "/runpod-volume/.initialization.lock":
                return True  # Lock file exists for cleanup
            return False

        mock_exists.side_effect = exists_side_effect
        mock_file = MagicMock()
        mock_open.return_value.__enter__.return_value = mock_file

        # Make workspace initialization fail after acquiring lock
        with patch.object(
            RemoteExecutor, "_create_virtual_environment"
        ) as mock_create_venv:
            mock_create_venv.side_effect = Exception("Initialization failed")

            executor = RemoteExecutor()

            # This will fail until we implement proper cleanup
            result = executor.initialize_workspace()

            assert result.success is False
            # Lock file should be removed even on failure
            mock_remove.assert_called_with("/runpod-volume/.initialization.lock")


class TestDependencyManagement:
    """Test differential dependency installation."""

    @patch("os.path.exists")
    @patch("subprocess.Popen")
    def test_differential_dependency_installation(self, mock_popen, mock_exists):
        """Test that only missing packages are installed."""
        mock_exists.side_effect = lambda path: path in [
            "/runpod-volume",
            "/runpod-volume/.venv",
        ]

        # Mock uv pip list to show some packages already installed
        mock_list_process = Mock()
        mock_list_process.returncode = 0
        mock_list_process.communicate.return_value = (
            b"numpy==1.21.0\npandas==1.3.0\n",
            b"",
        )

        # Mock uv pip install for missing packages
        mock_install_process = Mock()
        mock_install_process.returncode = 0
        mock_install_process.communicate.return_value = (b"Successfully installed", b"")

        mock_popen.side_effect = [mock_list_process, mock_install_process]

        executor = RemoteExecutor()
        packages = ["numpy==1.21.0", "scipy==1.7.0", "pandas==1.3.0"]

        # This will fail until we implement differential installation
        result = executor.install_dependencies(packages)

        assert result.success is True
        # Should only install scipy (the missing package)
        install_call_args = mock_popen.call_args_list[1][0][0]
        assert "scipy==1.7.0" in install_call_args
        assert "numpy==1.21.0" not in install_call_args
        assert "pandas==1.3.0" not in install_call_args

    @patch("os.path.exists")
    def test_skip_already_installed_packages(self, mock_exists):
        """Test that installation is skipped if all packages are present."""
        mock_exists.side_effect = lambda path: path in [
            "/runpod-volume",
            "/runpod-volume/.venv",
        ]

        with patch.object(
            RemoteExecutor, "_get_installed_packages"
        ) as mock_get_installed:
            mock_get_installed.return_value = {"numpy": "1.21.0", "pandas": "1.3.0"}

            executor = RemoteExecutor()
            packages = ["numpy==1.21.0", "pandas==1.3.0"]

            # This will fail until we implement skip logic
            result = executor.install_dependencies(packages)

            assert result.success is True
            assert "already installed" in result.stdout.lower()

    @patch("os.path.exists")
    @patch("os.environ")
    def test_shared_cache_usage(self, mock_environ, mock_exists):
        """Test that uv cache is configured to use shared volume."""
        mock_exists.return_value = True

        executor = RemoteExecutor()

        # This will fail until we implement cache configuration
        executor.configure_uv_cache()

        # Should set UV_CACHE_DIR to volume location
        assert mock_environ.__setitem__.called
        call_args = mock_environ.__setitem__.call_args_list
        cache_call = next(
            (call for call in call_args if call[0][0] == "UV_CACHE_DIR"), None
        )
        assert cache_call is not None
        assert cache_call[0][1] == "/runpod-volume/.uv-cache"
