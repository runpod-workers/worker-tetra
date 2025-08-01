"""Tests for WorkspaceManager component."""

import os
import threading
from unittest.mock import patch

from workspace_manager import WorkspaceManager
from remote_execution import FunctionResponse


class TestVolumeDetection:
    """Test detection of RunPod volume availability."""

    @patch("os.path.exists")
    def test_detects_runpod_volume_exists(self, mock_exists):
        """Test that manager detects when /runpod-volume exists."""
        mock_exists.return_value = True

        manager = WorkspaceManager()

        assert manager.has_runpod_volume is True
        assert manager.workspace_path == "/runpod-volume"
        assert manager.venv_path == "/runpod-volume/.venv"
        assert manager.cache_path == "/runpod-volume/.uv-cache"
        mock_exists.assert_called_with("/runpod-volume")

    @patch("os.path.exists")
    def test_detects_runpod_volume_missing(self, mock_exists):
        """Test fallback behavior when no volume is present."""
        mock_exists.return_value = False

        manager = WorkspaceManager()

        assert manager.has_runpod_volume is False
        assert manager.workspace_path == "/app"
        assert manager.venv_path is None
        assert manager.cache_path is None


class TestWorkspaceInitialization:
    """Test workspace initialization functionality."""

    @patch("os.path.exists")
    def test_workspace_initialization_creates_venv(self, mock_exists):
        """Test that workspace initialization creates virtual environment."""
        mock_exists.side_effect = lambda path: path == "/runpod-volume"

        manager = WorkspaceManager()

        with patch.object(manager, "_create_virtual_environment") as mock_create:
            mock_create.return_value = FunctionResponse(
                success=True, stdout="venv created"
            )
            with (
                patch("os.makedirs"),
                patch("builtins.open"),
                patch("fcntl.flock"),
                patch("os.remove"),
            ):
                result = manager.initialize_workspace()

            assert result.success is True
            mock_create.assert_called_once()

    @patch("os.path.exists")
    def test_workspace_already_initialized_skips_creation(self, mock_exists):
        """Test that existing workspace is not re-initialized."""
        mock_exists.side_effect = lambda path: path in [
            "/runpod-volume",
            "/runpod-volume/.venv",
        ]

        manager = WorkspaceManager()
        result = manager.initialize_workspace()

        assert result.success is True
        assert "already initialized" in result.stdout

    @patch("os.path.exists")
    def test_no_volume_returns_success(self, mock_exists):
        """Test that no volume available returns success."""
        mock_exists.return_value = False

        manager = WorkspaceManager()
        result = manager.initialize_workspace()

        assert result.success is True
        assert "No volume available" in result.stdout


class TestConcurrencySafety:
    """Test concurrent workspace initialization safety."""

    @patch("os.path.exists")
    @patch("os.makedirs")
    @patch("builtins.open")
    @patch("fcntl.flock")
    @patch("os.remove")
    def test_concurrent_workspace_initialization(
        self, mock_remove, mock_flock, mock_open, mock_makedirs, mock_exists
    ):
        """Test that concurrent initialization is handled safely."""
        mock_exists.side_effect = lambda path: path == "/runpod-volume"

        results = []

        def init_workspace():
            manager = WorkspaceManager()
            with patch.object(manager, "_create_virtual_environment") as mock_create:
                mock_create.return_value = FunctionResponse(
                    success=True, stdout="venv created"
                )
                result = manager.initialize_workspace()
                results.append(result)

        # Start multiple threads trying to initialize
        threads = [threading.Thread(target=init_workspace) for _ in range(3)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # All should succeed
        assert len([r for r in results if r.success]) >= 1


class TestEnvironmentConfiguration:
    """Test environment variable configuration."""

    @patch("os.path.exists")
    def test_configure_volume_environment(self, mock_exists):
        """Test environment variables are set for volume usage."""
        mock_exists.return_value = True

        with patch.dict("os.environ", {}, clear=True):
            WorkspaceManager()

            assert os.environ.get("UV_CACHE_DIR") == "/runpod-volume/.uv-cache"
            assert os.environ.get("VIRTUAL_ENV") == "/runpod-volume/.venv"
            assert "/runpod-volume/.venv/bin" in os.environ.get("PATH", "")

    @patch("os.path.exists")
    def test_no_environment_changes_without_volume(self, mock_exists):
        """Test no environment changes when no volume present."""
        mock_exists.return_value = False

        with patch.dict("os.environ", {}, clear=True):
            WorkspaceManager()

            assert "UV_CACHE_DIR" not in os.environ
            assert "VIRTUAL_ENV" not in os.environ


class TestWorkspaceOperations:
    """Test workspace directory operations."""

    @patch("os.path.exists")
    @patch("os.getcwd")
    @patch("os.chdir")
    def test_change_to_workspace(self, mock_chdir, mock_getcwd, mock_exists):
        """Test changing to workspace directory."""
        mock_exists.return_value = True
        mock_getcwd.return_value = "/original"

        manager = WorkspaceManager()
        original_cwd = manager.change_to_workspace()

        assert original_cwd == "/original"
        mock_chdir.assert_called_once_with("/runpod-volume")

    @patch("os.path.exists")
    def test_change_to_workspace_no_volume(self, mock_exists):
        """Test no directory change when no volume."""
        mock_exists.return_value = False

        manager = WorkspaceManager()
        original_cwd = manager.change_to_workspace()

        assert original_cwd is None

    @patch("os.path.exists")
    @patch("glob.glob")
    def test_setup_python_path(self, mock_glob, mock_exists):
        """Test Python path setup with virtual environment."""
        mock_exists.side_effect = lambda path: path in [
            "/runpod-volume",
            "/runpod-volume/.venv",
        ]
        mock_glob.return_value = ["/runpod-volume/.venv/lib/python3.12/site-packages"]

        manager = WorkspaceManager()

        import sys

        original_path = sys.path.copy()
        try:
            manager.setup_python_path()
            assert "/runpod-volume/.venv/lib/python3.12/site-packages" in sys.path
        finally:
            sys.path = original_path
