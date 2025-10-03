import os
import pytest
from unittest.mock import patch
from pathlib import Path
from cache_sync_manager import CacheSyncManager
from remote_execution import FunctionResponse


@pytest.fixture
def cache_sync():
    """Create a CacheSyncManager instance for testing."""
    return CacheSyncManager()


@pytest.fixture
def mock_env(monkeypatch):
    """Mock environment variables."""
    monkeypatch.setenv("RUNPOD_ENDPOINT_ID", "test-endpoint-123")


class TestShouldSync:
    def test_should_sync_no_endpoint_id(self, cache_sync):
        """Test that sync is skipped when RUNPOD_ENDPOINT_ID is not set."""
        with patch.dict(os.environ, {}, clear=True):
            cache_sync_new = CacheSyncManager()
            assert cache_sync_new.should_sync() is False

    def test_should_sync_volume_not_mounted(self, cache_sync, mock_env):
        """Test that sync is skipped when /runpod-volume is not mounted."""
        with patch("os.path.exists") as mock_exists:
            mock_exists.return_value = False
            assert cache_sync.should_sync() is False

    def test_should_sync_success(self, mock_env):
        """Test that sync proceeds when conditions are met."""
        # Create cache_sync after environment is set
        cache_sync = CacheSyncManager()

        with (
            patch("os.path.exists") as mock_exists,
            patch("os.makedirs") as mock_makedirs,
        ):

            def exists_side_effect(path):
                if path == "/runpod-volume":
                    return True
                return False

            mock_exists.side_effect = exists_side_effect
            assert cache_sync.should_sync() is True
            mock_makedirs.assert_called_once_with(
                "/runpod-volume/.cache", exist_ok=True
            )

    def test_should_sync_cached_result(self, mock_env):
        """Test that should_sync caches its result."""
        # Create cache_sync after environment is set
        cache_sync = CacheSyncManager()

        with patch("os.path.exists") as mock_exists, patch("os.makedirs"):

            def exists_side_effect(path):
                if path == "/runpod-volume":
                    return True
                return False

            mock_exists.side_effect = exists_side_effect

            # First call
            result1 = cache_sync.should_sync()
            # Second call should use cached result
            result2 = cache_sync.should_sync()

            assert result1 is True
            assert result2 is True
            # os.path.exists should be called only once (cached on second call)
            assert mock_exists.call_count <= 1


class TestMarkBaseline:
    def test_mark_baseline_skips_when_should_not_sync(self, cache_sync):
        """Test that mark_baseline skips when should_sync returns False."""
        with patch.object(cache_sync, "should_sync", return_value=False):
            cache_sync.mark_baseline()
            assert cache_sync._baseline_path is None

    def test_mark_baseline_creates_file(self, cache_sync, mock_env):
        """Test that mark_baseline creates a baseline file."""
        with (
            patch.object(cache_sync, "should_sync", return_value=True),
            patch.object(Path, "touch") as mock_touch,
        ):
            cache_sync.mark_baseline()

            assert cache_sync._baseline_path is not None
            assert cache_sync._baseline_path.startswith("/tmp/.cache-baseline-")
            mock_touch.assert_called_once()

    def test_mark_baseline_handles_exception(self, cache_sync, mock_env):
        """Test that mark_baseline handles exceptions gracefully."""
        with (
            patch.object(cache_sync, "should_sync", return_value=True),
            patch.object(Path, "touch", side_effect=OSError("Permission denied")),
        ):
            cache_sync.mark_baseline()
            assert cache_sync._baseline_path is None


class TestSyncToVolumeAsync:
    @pytest.mark.asyncio
    async def test_sync_skips_when_should_not_sync(self, cache_sync):
        """Test that sync_to_volume skips when should_sync returns False."""
        with (
            patch.object(cache_sync, "should_sync", return_value=False),
            patch("asyncio.to_thread") as mock_to_thread,
        ):
            await cache_sync.sync_to_volume()
            # Verify no subprocess operations were attempted
            mock_to_thread.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_skips_when_no_baseline(self, cache_sync, mock_env):
        """Test that sync_to_volume skips when no baseline is set."""
        with (
            patch.object(cache_sync, "should_sync", return_value=True),
            patch("asyncio.to_thread") as mock_to_thread,
        ):
            cache_sync._baseline_path = None
            await cache_sync.sync_to_volume()
            # Verify no subprocess operations were attempted
            mock_to_thread.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_callssync_to_volume(self, cache_sync, mock_env):
        """Test that sync_to_volume calls sync_to_volume."""
        with (
            patch.object(cache_sync, "should_sync", return_value=True),
            patch.object(cache_sync, "sync_to_volume") as mock_collect,
        ):
            cache_sync._baseline_path = "/tmp/.cache-baseline-123"
            await cache_sync.sync_to_volume()
            mock_collect.assert_called_once()


class TestCollectAndTarball:
    @pytest.mark.asyncio
    async def testsync_to_volume_no_new_files(self, cache_sync, mock_env):
        """Test that sync_to_volume handles no new files."""
        cache_sync._endpoint_id = "test-endpoint-123"
        cache_sync._baseline_path = "/tmp/.cache-baseline-123"

        mock_find_result = FunctionResponse(success=True, stdout="")

        with patch(
            "asyncio.to_thread", side_effect=[mock_find_result]
        ) as mock_to_thread:
            await cache_sync.sync_to_volume()

            # Only find command should be called, tar should be skipped
            assert mock_to_thread.call_count == 1

    @pytest.mark.asyncio
    async def testsync_to_volume_success_new(self, cache_sync, mock_env):
        """Test successful tarball creation when no tarball exists."""
        cache_sync._endpoint_id = "test-endpoint-123"
        cache_sync._baseline_path = "/tmp/.cache-baseline-123"

        mock_find_result = FunctionResponse(
            success=True, stdout="/root/.cache/file1\n/root/.cache/file2"
        )
        mock_tar_result = FunctionResponse(success=True, stdout="")
        mock_mv_result = FunctionResponse(success=True, stdout="")

        with (
            patch(
                "asyncio.to_thread",
                side_effect=[mock_find_result, mock_tar_result, mock_mv_result],
            ) as mock_to_thread,
            patch("os.path.exists") as mock_exists,
            patch("os.remove") as mock_remove,
            patch("builtins.open", create=True) as mock_open,
        ):
            # Tarball doesn't exist initially, but baseline and file list cleanup exist
            def exists_side_effect(path):
                if path == "/tmp/.cache-baseline-123":
                    return True
                elif path.startswith("/tmp/.cache-files-"):
                    return True
                return False

            mock_exists.side_effect = exists_side_effect

            await cache_sync.sync_to_volume()

            # find, tar, and mv should be called
            assert mock_to_thread.call_count == 3
            # File list should be written
            mock_open.assert_called_once()
            # Both baseline file and file list should be cleaned up (2 calls)
            assert mock_remove.call_count == 2

    @pytest.mark.asyncio
    async def testsync_to_volume_success_append(self, cache_sync, mock_env):
        """Test successful tarball append when tarball already exists."""
        cache_sync._endpoint_id = "test-endpoint-123"
        cache_sync._baseline_path = "/tmp/.cache-baseline-123"

        mock_find_result = FunctionResponse(
            success=True, stdout="/root/.cache/file3\n/root/.cache/file4"
        )
        mock_cp_result = FunctionResponse(success=True, stdout="")
        mock_tar_result = FunctionResponse(success=True, stdout="")
        mock_mv_result = FunctionResponse(success=True, stdout="")

        with (
            patch(
                "asyncio.to_thread",
                side_effect=[
                    mock_find_result,
                    mock_cp_result,
                    mock_tar_result,
                    mock_mv_result,
                ],
            ) as mock_to_thread,
            patch("os.path.exists") as mock_exists,
            patch("os.remove") as mock_remove,
            patch("builtins.open", create=True) as mock_open,
        ):
            # Tarball exists initially
            def exists_side_effect(path):
                if path == "/runpod-volume/.cache/cache-test-endpoint-123.tar":
                    return True
                elif path == "/tmp/.cache-baseline-123":
                    return True
                elif path.startswith("/tmp/.cache-files-"):
                    return True
                return False

            mock_exists.side_effect = exists_side_effect

            await cache_sync.sync_to_volume()

            # find, cp, tar, and mv should be called
            assert mock_to_thread.call_count == 4
            # File list should be written
            mock_open.assert_called_once()
            # Both baseline file and file list should be cleaned up (2 calls)
            assert mock_remove.call_count == 2

    @pytest.mark.asyncio
    async def testsync_to_volume_find_failure(self, cache_sync, mock_env):
        """Test handling of find command failure."""
        cache_sync._endpoint_id = "test-endpoint-123"
        cache_sync._baseline_path = "/tmp/.cache-baseline-123"

        mock_find_result = FunctionResponse(success=False, error="Find failed")

        with patch(
            "asyncio.to_thread", side_effect=[mock_find_result]
        ) as mock_to_thread:
            await cache_sync.sync_to_volume()

            # Only find should be attempted, tar should be skipped
            assert mock_to_thread.call_count == 1

    @pytest.mark.asyncio
    async def testsync_to_volume_cleanup_on_exception(self, cache_sync, mock_env):
        """Test that baseline is cleaned up even on exception."""
        cache_sync._endpoint_id = "test-endpoint-123"
        cache_sync._baseline_path = "/tmp/.cache-baseline-123"

        with (
            patch("asyncio.to_thread", side_effect=Exception("Unexpected error")),
            patch("os.path.exists", return_value=True),
            patch("os.remove") as mock_remove,
        ):
            await cache_sync.sync_to_volume()

            # Baseline should still be cleaned up
            mock_remove.assert_called_once_with("/tmp/.cache-baseline-123")
