"""Tests for WorkspaceManager component."""

from unittest.mock import patch

from workspace_manager import WorkspaceManager
from constants import (
    RUNPOD_VOLUME_PATH,
    DEFAULT_WORKSPACE_PATH,
    RUNTIMES_DIR_NAME,
)


class TestEndpointIsolation:
    """Test endpoint-specific workspace isolation."""

    @patch("os.path.exists")
    def test_different_endpoints_get_different_workspaces(self, mock_exists):
        """Test that different endpoint IDs create separate workspaces."""
        mock_exists.return_value = True

        # Test with endpoint-1
        with patch.dict("os.environ", {"RUNPOD_ENDPOINT_ID": "endpoint-1"}):
            manager1 = WorkspaceManager()
            expected_workspace1 = f"{RUNPOD_VOLUME_PATH}/{RUNTIMES_DIR_NAME}/endpoint-1"
            assert manager1.workspace_path == expected_workspace1

        # Test with endpoint-2
        with patch.dict("os.environ", {"RUNPOD_ENDPOINT_ID": "endpoint-2"}):
            manager2 = WorkspaceManager()
            expected_workspace2 = f"{RUNPOD_VOLUME_PATH}/{RUNTIMES_DIR_NAME}/endpoint-2"
            assert manager2.workspace_path == expected_workspace2

        # Workspaces should be different
        assert manager1.workspace_path != manager2.workspace_path

    @patch("os.path.exists")
    def test_default_endpoint_id_when_not_set(self, mock_exists):
        """Test that 'default' is used when RUNPOD_ENDPOINT_ID is not set."""
        mock_exists.return_value = True

        with patch.dict("os.environ", {}, clear=True):
            manager = WorkspaceManager()
            expected_workspace = f"{RUNPOD_VOLUME_PATH}/{RUNTIMES_DIR_NAME}/default"
            assert manager.workspace_path == expected_workspace
            assert manager.endpoint_id == "default"


class TestVolumeDetection:
    """Test detection of RunPod volume availability."""

    @patch("os.path.exists")
    def test_detects_runpod_volume_exists(self, mock_exists):
        """Test that manager detects when /runpod-volume exists."""
        mock_exists.return_value = True

        manager = WorkspaceManager()

        assert manager.has_runpod_volume is True
        expected_workspace = f"{RUNPOD_VOLUME_PATH}/{RUNTIMES_DIR_NAME}/default"
        assert manager.workspace_path == expected_workspace
        mock_exists.assert_called_with(RUNPOD_VOLUME_PATH)

    @patch("os.path.exists")
    def test_detects_runpod_volume_missing(self, mock_exists):
        """Test fallback behavior when no volume is present."""
        mock_exists.return_value = False

        manager = WorkspaceManager()

        assert manager.has_runpod_volume is False
        assert manager.workspace_path == DEFAULT_WORKSPACE_PATH


class TestSyncOperations:
    """Test volume sync operations."""

    @patch("os.path.exists")
    def test_sync_from_volume_to_container_returns_success(self, mock_exists):
        """Test sync from volume to container interface."""
        mock_exists.return_value = True

        manager = WorkspaceManager()
        result = manager.sync_from_volume_to_container()

        assert result.success is True
        assert "replicator" in result.stdout.lower()

    @patch("os.path.exists")
    def test_sync_from_container_to_volume_returns_success(self, mock_exists):
        """Test sync from container to volume interface."""
        mock_exists.return_value = True

        manager = WorkspaceManager()
        result = manager.sync_from_container_to_volume()

        assert result.success is True
        assert "replicator" in result.stdout.lower()

    @patch("os.path.exists")
    def test_sync_accepts_optional_source_path(self, mock_exists):
        """Test sync methods accept optional source path parameter."""
        mock_exists.return_value = True

        manager = WorkspaceManager()

        # Should not raise exceptions
        result1 = manager.sync_from_volume_to_container("/some/path")
        result2 = manager.sync_from_container_to_volume("/some/other/path")

        assert result1.success is True
        assert result2.success is True
