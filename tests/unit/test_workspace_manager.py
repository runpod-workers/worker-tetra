"""Tests for WorkspaceManager component."""

import os
import threading
from unittest.mock import patch

from workspace_manager import WorkspaceManager
from remote_execution import FunctionResponse
from constants import (
    RUNPOD_VOLUME_PATH,
    DEFAULT_WORKSPACE_PATH,
    VENV_DIR_NAME,
    UV_CACHE_DIR_NAME,
    HF_CACHE_DIR_NAME,
    RUNTIMES_DIR_NAME,
)


class TestEndpointIsolation:
    """Test endpoint-specific workspace isolation."""

    @patch("os.makedirs")
    @patch("os.path.exists")
    def test_different_endpoints_get_different_workspaces(
        self, mock_exists, mock_makedirs
    ):
        """Test that different endpoint IDs create separate workspaces."""
        mock_exists.return_value = True

        # Test with endpoint-1
        with patch.dict("os.environ", {"RUNPOD_ENDPOINT_ID": "endpoint-1"}):
            manager1 = WorkspaceManager()
            expected_workspace1 = f"{RUNPOD_VOLUME_PATH}/{RUNTIMES_DIR_NAME}/endpoint-1"
            assert manager1.workspace_path == expected_workspace1
            assert manager1.venv_path == f"{expected_workspace1}/{VENV_DIR_NAME}"

        # Test with endpoint-2
        with patch.dict("os.environ", {"RUNPOD_ENDPOINT_ID": "endpoint-2"}):
            manager2 = WorkspaceManager()
            expected_workspace2 = f"{RUNPOD_VOLUME_PATH}/{RUNTIMES_DIR_NAME}/endpoint-2"
            assert manager2.workspace_path == expected_workspace2
            assert manager2.venv_path == f"{expected_workspace2}/{VENV_DIR_NAME}"

        # Workspaces should be different
        assert manager1.workspace_path != manager2.workspace_path
        assert manager1.venv_path != manager2.venv_path

        # But caches should be shared
        assert (
            manager1.cache_path
            == manager2.cache_path
            == f"{RUNPOD_VOLUME_PATH}/{UV_CACHE_DIR_NAME}"
        )
        assert (
            manager1.hf_cache_path
            == manager2.hf_cache_path
            == f"{RUNPOD_VOLUME_PATH}/{HF_CACHE_DIR_NAME}"
        )

    @patch("os.makedirs")
    @patch("os.path.exists")
    def test_default_endpoint_id_when_not_set(self, mock_exists, mock_makedirs):
        """Test that 'default' is used when RUNPOD_ENDPOINT_ID is not set."""
        mock_exists.return_value = True

        with patch.dict("os.environ", {}, clear=True):
            manager = WorkspaceManager()
            expected_workspace = f"{RUNPOD_VOLUME_PATH}/{RUNTIMES_DIR_NAME}/default"
            assert manager.workspace_path == expected_workspace
            assert manager.endpoint_id == "default"


class TestVolumeDetection:
    """Test detection of RunPod volume availability."""

    @patch("os.makedirs")
    @patch("os.path.exists")
    def test_detects_runpod_volume_exists(self, mock_exists, mock_makedirs):
        """Test that manager detects when /runpod-volume exists."""
        mock_exists.return_value = True

        manager = WorkspaceManager()

        assert manager.has_runpod_volume is True
        # Workspace is now endpoint-specific (using 'default' when RUNPOD_ENDPOINT_ID not set)
        expected_workspace = f"{RUNPOD_VOLUME_PATH}/{RUNTIMES_DIR_NAME}/default"
        assert manager.workspace_path == expected_workspace
        assert manager.venv_path == f"{expected_workspace}/{VENV_DIR_NAME}"
        # Caches are shared at volume root
        assert manager.cache_path == f"{RUNPOD_VOLUME_PATH}/{UV_CACHE_DIR_NAME}"
        assert manager.hf_cache_path == f"{RUNPOD_VOLUME_PATH}/{HF_CACHE_DIR_NAME}"
        mock_exists.assert_called_with(RUNPOD_VOLUME_PATH)

    @patch("os.path.exists")
    def test_detects_runpod_volume_missing(self, mock_exists):
        """Test fallback behavior when no volume is present."""
        mock_exists.return_value = False

        manager = WorkspaceManager()

        assert manager.has_runpod_volume is False
        assert manager.workspace_path == DEFAULT_WORKSPACE_PATH
        assert manager.venv_path is None
        assert manager.cache_path is None
        assert manager.hf_cache_path is None


class TestWorkspaceInitialization:
    """Test workspace initialization functionality."""

    @patch("os.makedirs")
    @patch("os.path.exists")
    def test_workspace_initialization_creates_venv(self, mock_exists, mock_makedirs):
        """Test that workspace initialization creates virtual environment."""
        mock_exists.side_effect = lambda path: path == RUNPOD_VOLUME_PATH

        manager = WorkspaceManager()

        with patch.object(manager, "_create_virtual_environment") as mock_create:
            mock_create.return_value = FunctionResponse(
                success=True, stdout="venv created"
            )
            with (
                patch("os.makedirs"),
                patch("builtins.open"),
                patch("os.open", return_value=42),
                patch("os.close"),
                patch("os.remove"),
                patch("fcntl.flock"),
            ):
                with patch.object(
                    manager, "_is_workspace_functional", return_value=False
                ):
                    with patch.object(
                        manager, "_validate_workspace_directory"
                    ) as mock_validate:
                        mock_validate.return_value = FunctionResponse(success=True)

                        result = manager.initialize_workspace()

            assert result.success is True
            mock_create.assert_called_once()

    @patch("os.makedirs")
    @patch("workspace_manager.WorkspaceManager._validate_virtual_environment")
    @patch("os.path.exists")
    def test_workspace_already_initialized_skips_creation(
        self, mock_exists, mock_validate, mock_makedirs
    ):
        """Test that existing workspace is not re-initialized."""
        expected_workspace = f"{RUNPOD_VOLUME_PATH}/{RUNTIMES_DIR_NAME}/default"
        mock_exists.side_effect = lambda path: path in [
            RUNPOD_VOLUME_PATH,
            expected_workspace,
            f"{expected_workspace}/{VENV_DIR_NAME}",
        ]
        mock_validate.return_value = FunctionResponse(success=True, stdout="Valid venv")

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
    @patch("os.open")
    @patch("os.close")
    @patch("os.remove")
    @patch("fcntl.flock")
    def test_concurrent_workspace_initialization(
        self,
        mock_flock,
        mock_remove,
        mock_close,
        mock_open_fd,
        mock_open,
        mock_makedirs,
        mock_exists,
    ):
        """Test that concurrent initialization is handled safely."""
        mock_exists.side_effect = lambda path: path == RUNPOD_VOLUME_PATH
        mock_open_fd.return_value = 42

        results = []

        def init_workspace():
            manager = WorkspaceManager()
            with patch.object(
                manager, "_validate_workspace_directory"
            ) as mock_validate:
                mock_validate.return_value = FunctionResponse(success=True)
                with patch.object(
                    manager, "_create_virtual_environment"
                ) as mock_create:
                    mock_create.return_value = FunctionResponse(
                        success=True, stdout="venv created"
                    )
                    with patch.object(
                        manager, "_is_workspace_functional", return_value=False
                    ):
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

    @patch("os.path.exists")
    @patch("os.makedirs")
    @patch("builtins.open")
    @patch("os.open")
    @patch("os.close")
    @patch("os.remove")
    @patch("fcntl.flock")
    @patch("time.sleep")
    @patch("time.time")
    def test_lock_timeout_handling(
        self,
        mock_time,
        mock_sleep,
        mock_flock,
        mock_remove,
        mock_close,
        mock_open_fd,
        mock_open,
        mock_makedirs,
        mock_exists,
    ):
        """Test that lock timeout is handled properly."""
        mock_exists.side_effect = lambda path: path == RUNPOD_VOLUME_PATH
        mock_open_fd.return_value = 42

        # Mock time.time() to simulate timeout
        mock_time.side_effect = [0, 15, 31]  # Start, during wait, timeout exceeded

        # Mock flock to always raise BlockingIOError (lock not available)
        mock_flock.side_effect = BlockingIOError("Resource temporarily unavailable")

        manager = WorkspaceManager()
        with patch.object(manager, "_is_workspace_functional", return_value=False):
            with patch.object(
                manager, "_validate_workspace_directory"
            ) as mock_validate:
                mock_validate.return_value = FunctionResponse(success=True)

                result = manager.initialize_workspace(timeout=30)

                assert result.success is False
                assert "timeout" in result.error.lower()

    @patch("os.path.exists")
    @patch("os.makedirs")
    @patch("os.open")
    @patch("fcntl.flock")
    @patch("os.close")
    @patch("os.remove")
    def test_lock_file_descriptor_cleanup(
        self,
        mock_remove,
        mock_close,
        mock_flock,
        mock_open_fd,
        mock_makedirs,
        mock_exists,
    ):
        """Test that file descriptors are properly cleaned up even on errors."""
        mock_exists.side_effect = lambda path: path == RUNPOD_VOLUME_PATH
        mock_open_fd.return_value = 42  # Mock file descriptor

        # Mock flock to raise an exception during lock acquisition
        mock_flock.side_effect = OSError("Lock operation failed")

        manager = WorkspaceManager()
        with patch.object(manager, "_validate_workspace_directory") as mock_validate:
            mock_validate.return_value = FunctionResponse(success=True)

            result = manager.initialize_workspace()

            # Should handle the error gracefully
            assert result.success is False

            # File descriptor should be closed even on error
            mock_close.assert_called_once_with(42)

    @patch("os.path.exists")
    @patch("os.makedirs")
    def test_workspace_directory_validation_failure(self, mock_makedirs, mock_exists):
        """Test handling of workspace directory validation failure."""
        # Setup initial mocking for WorkspaceManager __init__
        mock_exists.side_effect = lambda path: path == RUNPOD_VOLUME_PATH

        # Create manager with successful initialization first
        manager = WorkspaceManager()

        # Now test the specific failure case by patching the validation method
        with patch.object(manager, "_validate_workspace_directory") as mock_validate:
            mock_validate.return_value = FunctionResponse(
                success=False,
                error="Cannot create workspace directory: Permission denied",
            )

            result = manager.initialize_workspace()

            assert result.success is False
            assert "Cannot create workspace directory" in result.error

    @patch("os.path.exists")
    @patch("os.makedirs")
    @patch("builtins.open")
    @patch("os.remove")
    def test_workspace_write_permission_validation(
        self, mock_remove, mock_open_builtin, mock_makedirs, mock_exists
    ):
        """Test validation of write permissions in workspace directory."""
        mock_exists.side_effect = lambda path: path == RUNPOD_VOLUME_PATH

        # Mock open to raise PermissionError for write test
        mock_open_builtin.side_effect = PermissionError("Write permission denied")

        manager = WorkspaceManager()
        result = manager.initialize_workspace()

        assert result.success is False
        assert "not writable" in result.error

    @patch("os.path.exists")
    @patch("os.makedirs")
    @patch("builtins.open")
    @patch("fcntl.flock")
    @patch("os.open")
    @patch("os.close")
    @patch("os.remove")
    def test_concurrent_workspace_check_race_condition(
        self,
        mock_remove,
        mock_close,
        mock_open_fd,
        mock_flock,
        mock_open_builtin,
        mock_makedirs,
        mock_exists,
    ):
        """Test race condition where workspace becomes functional during lock wait."""
        mock_exists.side_effect = lambda path: path == RUNPOD_VOLUME_PATH
        mock_open_fd.return_value = 42

        # First flock call fails (lock not available), but workspace becomes ready
        call_count = 0

        def mock_flock_behavior(fd, operation):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise BlockingIOError("Lock not available")

        mock_flock.side_effect = mock_flock_behavior

        manager = WorkspaceManager()
        with patch.object(manager, "_validate_workspace_directory") as mock_validate:
            mock_validate.return_value = FunctionResponse(success=True)

            with patch.object(manager, "_is_workspace_functional") as mock_functional:
                # First call returns False, second call (during wait) returns True
                mock_functional.side_effect = [False, True]

                result = manager.initialize_workspace()

                assert result.success is True
                assert "initialized by another worker" in result.stdout


class TestEnvironmentConfiguration:
    """Test environment variable configuration."""

    @patch("os.makedirs")
    @patch("os.path.exists")
    def test_configure_volume_environment(self, mock_exists, mock_makedirs):
        """Test environment variables are set for volume usage."""
        mock_exists.return_value = True

        with patch.dict("os.environ", {}, clear=True):
            WorkspaceManager()

            # UV cache is shared at volume root
            assert (
                os.environ.get("UV_CACHE_DIR")
                == f"{RUNPOD_VOLUME_PATH}/{UV_CACHE_DIR_NAME}"
            )
            # HF cache is shared at volume root
            assert (
                os.environ.get("HF_HOME") == f"{RUNPOD_VOLUME_PATH}/{HF_CACHE_DIR_NAME}"
            )
            assert (
                os.environ.get("TRANSFORMERS_CACHE")
                == f"{RUNPOD_VOLUME_PATH}/{HF_CACHE_DIR_NAME}/transformers"
            )
            assert (
                os.environ.get("HF_DATASETS_CACHE")
                == f"{RUNPOD_VOLUME_PATH}/{HF_CACHE_DIR_NAME}/datasets"
            )
            assert (
                os.environ.get("HUGGINGFACE_HUB_CACHE")
                == f"{RUNPOD_VOLUME_PATH}/{HF_CACHE_DIR_NAME}/hub"
            )
            # Virtual environment is endpoint-specific
            expected_venv = (
                f"{RUNPOD_VOLUME_PATH}/{RUNTIMES_DIR_NAME}/default/{VENV_DIR_NAME}"
            )
            assert os.environ.get("VIRTUAL_ENV") == expected_venv
            assert f"{expected_venv}/bin" in os.environ.get("PATH", "")

    @patch("os.path.exists")
    def test_no_environment_changes_without_volume(self, mock_exists):
        """Test no environment changes when no volume present."""
        mock_exists.return_value = False

        with patch.dict("os.environ", {}, clear=True):
            WorkspaceManager()

            assert "UV_CACHE_DIR" not in os.environ
            assert "HF_HOME" not in os.environ
            assert "TRANSFORMERS_CACHE" not in os.environ
            assert "HF_DATASETS_CACHE" not in os.environ
            assert "HUGGINGFACE_HUB_CACHE" not in os.environ
            assert "VIRTUAL_ENV" not in os.environ


class TestWorkspaceOperations:
    """Test workspace directory operations."""

    @patch("os.makedirs")
    @patch("os.path.exists")
    @patch("os.getcwd")
    @patch("os.chdir")
    def test_change_to_workspace(
        self, mock_chdir, mock_getcwd, mock_exists, mock_makedirs
    ):
        """Test changing to workspace directory."""
        mock_exists.return_value = True
        mock_getcwd.return_value = "/original"

        manager = WorkspaceManager()
        original_cwd = manager.change_to_workspace()

        assert original_cwd == "/original"
        # Now changes to endpoint-specific workspace
        expected_workspace = f"{RUNPOD_VOLUME_PATH}/{RUNTIMES_DIR_NAME}/default"
        mock_chdir.assert_called_once_with(expected_workspace)

    @patch("os.path.exists")
    def test_change_to_workspace_no_volume(self, mock_exists):
        """Test no directory change when no volume."""
        mock_exists.return_value = False

        manager = WorkspaceManager()
        original_cwd = manager.change_to_workspace()

        assert original_cwd is None

    @patch("os.makedirs")
    @patch("workspace_manager.WorkspaceManager._validate_virtual_environment")
    @patch("os.path.exists")
    @patch("glob.glob")
    def test_setup_python_path(
        self, mock_glob, mock_exists, mock_validate, mock_makedirs
    ):
        """Test Python path setup with virtual environment."""
        expected_workspace = f"{RUNPOD_VOLUME_PATH}/{RUNTIMES_DIR_NAME}/default"
        expected_venv = f"{expected_workspace}/{VENV_DIR_NAME}"
        mock_exists.side_effect = lambda path: path in [
            RUNPOD_VOLUME_PATH,
            expected_venv,
        ]
        mock_glob.return_value = [f"{expected_venv}/lib/python3.12/site-packages"]
        mock_validate.return_value = FunctionResponse(success=True, stdout="Valid venv")

        manager = WorkspaceManager()

        import sys

        original_path = sys.path.copy()
        try:
            manager.setup_python_path()
            assert f"{expected_venv}/lib/python3.12/site-packages" in sys.path
        finally:
            sys.path = original_path
