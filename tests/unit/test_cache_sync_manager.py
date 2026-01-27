import os
import pytest
from unittest.mock import patch
from pathlib import Path
from cache_sync_manager import CacheSyncManager
from tetra_rp.protos.remote_execution import FunctionResponse


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
            mock_makedirs.assert_called_once_with("/runpod-volume/.cache", exist_ok=True)

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
            assert cache_sync._baseline_time is None

    def test_mark_baseline_stores_timestamp(self, cache_sync, mock_env):
        """Test that mark_baseline stores current timestamp."""
        with (
            patch.object(cache_sync, "should_sync", return_value=True),
            patch("cache_sync_manager.datetime") as mock_datetime,
        ):
            # Mock datetime.now().timestamp()
            mock_now = mock_datetime.now.return_value
            mock_now.timestamp.return_value = 1234567890.0

            cache_sync.mark_baseline()

            assert cache_sync._baseline_time == 1234567890.0

    def test_mark_baseline_handles_exception(self, cache_sync, mock_env):
        """Test that mark_baseline handles exceptions gracefully."""
        with (
            patch.object(cache_sync, "should_sync", return_value=True),
            patch("cache_sync_manager.datetime") as mock_datetime,
        ):
            mock_datetime.now.side_effect = Exception("Time error")

            cache_sync.mark_baseline()
            assert cache_sync._baseline_time is None


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


class TestCollectAndTarball:
    @pytest.mark.asyncio
    async def test_sync_to_volume_no_new_files(self, cache_sync, mock_env):
        """Test that sync_to_volume handles no new files."""
        cache_sync._endpoint_id = "test-endpoint-123"
        cache_sync._baseline_time = 1234567890.0

        mock_find_result = FunctionResponse(success=True, stdout="")

        with (
            patch.object(cache_sync, "should_sync", return_value=True),
            patch("os.path.exists", return_value=True),
            patch("os.path.getmtime", return_value=1234567890.0),
            patch("asyncio.to_thread", side_effect=[mock_find_result]) as mock_to_thread,
        ):
            await cache_sync.sync_to_volume()

            # Only find command should be called, tar should be skipped
            assert mock_to_thread.call_count == 1

    @pytest.mark.asyncio
    async def test_sync_to_volume_success_new(self, cache_sync, mock_env):
        """Test successful tarball creation when no tarball exists (uses baseline_time)."""
        cache_sync._endpoint_id = "test-endpoint-123"
        cache_sync._baseline_time = 1234567890.0

        mock_find_result = FunctionResponse(
            success=True, stdout="/root/.cache/file1\n/root/.cache/file2"
        )
        mock_create_result = FunctionResponse(success=True, stdout="")
        mock_mv_result = FunctionResponse(success=True, stdout="")

        with (
            patch.object(cache_sync, "should_sync", return_value=True),
            patch(
                "asyncio.to_thread",
                side_effect=[mock_find_result, mock_create_result, mock_mv_result],
            ) as mock_to_thread,
            patch("os.path.exists") as mock_exists,
            patch("os.remove") as mock_remove,
            patch("tempfile.NamedTemporaryFile") as mock_tempfile,
            patch.object(cache_sync, "mark_last_hydrated") as mock_mark,
        ):
            # Mock tempfile for file list
            mock_file_list = mock_tempfile.return_value
            mock_file_list.name = "/tmp/.cache-files-abc123"

            # Tarball doesn't exist initially, but temp files exist
            def exists_side_effect(path):
                if path == "/runpod-volume/.cache/cache-test-endpoint-123.tar":
                    return False
                elif path.endswith(".new") or path.endswith(".tmp"):
                    return True
                elif path.startswith("/tmp/.cache-files-"):
                    return True
                return False

            mock_exists.side_effect = exists_side_effect

            await cache_sync.sync_to_volume()

            # find, tar cf (create new), and mv should be called
            assert mock_to_thread.call_count == 3
            # File list and temp files should be cleaned up (3 calls)
            assert mock_remove.call_count == 3
            # mark_last_hydrated should be called after successful sync
            mock_mark.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_to_volume_success_append(self, cache_sync, mock_env):
        """Test successful tarball concatenation when tarball already exists (uses baseline_time)."""
        cache_sync._endpoint_id = "test-endpoint-123"
        cache_sync._baseline_time = 1234567890.0

        mock_find_result = FunctionResponse(
            success=True, stdout="/root/.cache/file3\n/root/.cache/file4"
        )
        mock_create_result = FunctionResponse(success=True, stdout="")
        mock_mv_to_temp_result = FunctionResponse(success=True, stdout="")
        mock_concat_result = FunctionResponse(success=True, stdout="")
        mock_mv_to_final_result = FunctionResponse(success=True, stdout="")

        with (
            patch.object(cache_sync, "should_sync", return_value=True),
            patch(
                "asyncio.to_thread",
                side_effect=[
                    mock_find_result,
                    mock_create_result,
                    mock_mv_to_temp_result,
                    mock_concat_result,
                    mock_mv_to_final_result,
                ],
            ) as mock_to_thread,
            patch("os.path.exists") as mock_exists,
            patch("os.remove") as mock_remove,
            patch("tempfile.NamedTemporaryFile") as mock_tempfile,
            patch.object(cache_sync, "mark_last_hydrated") as mock_mark,
        ):
            # Mock tempfile for file list
            mock_file_list = mock_tempfile.return_value
            mock_file_list.name = "/tmp/.cache-files-abc123"

            # Tarball exists initially, plus temp files
            def exists_side_effect(path):
                if path == "/runpod-volume/.cache/cache-test-endpoint-123.tar":
                    return True
                elif path.endswith(".new") or path.endswith(".tmp"):
                    return True
                elif path.startswith("/tmp/.cache-files-"):
                    return True
                return False

            mock_exists.side_effect = exists_side_effect

            await cache_sync.sync_to_volume()

            # find, tar cf (create new), mv (to temp), tar -A (concat), mv (to final)
            assert mock_to_thread.call_count == 5
            # File list and temp files should be cleaned up (3 calls)
            assert mock_remove.call_count == 3
            # mark_last_hydrated should be called after successful sync
            mock_mark.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_to_volume_move_to_temp_failure(self, cache_sync, mock_env):
        """Test handling of move to temp failure when concatenating."""
        cache_sync._endpoint_id = "test-endpoint-123"
        cache_sync._baseline_time = 1234567890.0

        mock_find_result = FunctionResponse(
            success=True, stdout="/root/.cache/file3\n/root/.cache/file4"
        )
        mock_create_result = FunctionResponse(success=True, stdout="")
        mock_mv_to_temp_result = FunctionResponse(success=False, error="Move to temp failed")

        with (
            patch.object(cache_sync, "should_sync", return_value=True),
            patch(
                "asyncio.to_thread",
                side_effect=[
                    mock_find_result,
                    mock_create_result,
                    mock_mv_to_temp_result,
                ],
            ) as mock_to_thread,
            patch("os.path.exists") as mock_exists,
        ):
            # Tarball exists initially
            def exists_side_effect(path):
                if path == "/runpod-volume/.cache/cache-test-endpoint-123.tar":
                    return True
                return False

            mock_exists.side_effect = exists_side_effect

            await cache_sync.sync_to_volume()

            # find, tar cf (create new), and mv to temp should be called
            assert mock_to_thread.call_count == 3

    @pytest.mark.asyncio
    async def test_sync_to_volume_find_failure(self, cache_sync, mock_env):
        """Test handling of find command failure."""
        cache_sync._endpoint_id = "test-endpoint-123"
        cache_sync._baseline_time = 1234567890.0

        mock_find_result = FunctionResponse(success=False, error="Find failed")

        with (
            patch.object(cache_sync, "should_sync", return_value=True),
            patch("os.path.exists", return_value=True),
            patch("asyncio.to_thread", side_effect=[mock_find_result]) as mock_to_thread,
        ):
            await cache_sync.sync_to_volume()

            # Only find should be attempted, tar should be skipped
            assert mock_to_thread.call_count == 1

    @pytest.mark.asyncio
    async def test_sync_to_volume_handles_exception(self, cache_sync, mock_env):
        """Test that sync_to_volume handles unexpected exceptions."""
        cache_sync._endpoint_id = "test-endpoint-123"
        cache_sync._baseline_time = 1234567890.0

        with (
            patch.object(cache_sync, "should_sync", return_value=True),
            patch("os.path.exists", return_value=True),
            patch("asyncio.to_thread", side_effect=Exception("Unexpected error")),
        ):
            # Should not raise exception
            await cache_sync.sync_to_volume()


class TestShouldHydrate:
    def test_should_hydrate_when_should_sync_false(self, cache_sync):
        """Test that hydration skips when should_sync returns False."""
        with patch.object(cache_sync, "should_sync", return_value=False):
            assert cache_sync.should_hydrate() is False

    def test_should_hydrate_when_no_tarball(self, cache_sync, mock_env):
        """Test that hydration skips when tarball doesn't exist."""
        with (
            patch.object(cache_sync, "should_sync", return_value=True),
            patch("os.path.exists", return_value=False),
        ):
            assert cache_sync.should_hydrate() is False

    def test_should_hydrate_when_no_marker(self, cache_sync, mock_env):
        """Test that hydration proceeds when no marker exists."""
        cache_sync._endpoint_id = "test-endpoint-123"

        with (
            patch.object(cache_sync, "should_sync", return_value=True),
            patch("os.path.exists") as mock_exists,
        ):

            def exists_side_effect(path):
                if "cache-test-endpoint-123.tar" in path:
                    return True
                return False

            mock_exists.side_effect = exists_side_effect
            assert cache_sync.should_hydrate() is True

    def test_should_hydrate_when_tarball_newer(self, cache_sync, mock_env):
        """Test that hydration proceeds when tarball is newer than marker."""
        cache_sync._endpoint_id = "test-endpoint-123"

        with (
            patch.object(cache_sync, "should_sync", return_value=True),
            patch("os.path.exists", return_value=True),
            patch("os.path.getmtime") as mock_getmtime,
        ):

            def getmtime_side_effect(path):
                if "cache-test-endpoint-123.tar" in path:
                    return 2000.0
                return 1000.0

            mock_getmtime.side_effect = getmtime_side_effect
            assert cache_sync.should_hydrate() is True

    def test_should_hydrate_when_tarball_older(self, cache_sync, mock_env):
        """Test that hydration skips when tarball is older than marker."""
        cache_sync._endpoint_id = "test-endpoint-123"

        with (
            patch.object(cache_sync, "should_sync", return_value=True),
            patch("os.path.exists", return_value=True),
            patch("os.path.getmtime") as mock_getmtime,
        ):

            def getmtime_side_effect(path):
                if "cache-test-endpoint-123.tar" in path:
                    return 1000.0
                return 2000.0

            mock_getmtime.side_effect = getmtime_side_effect
            assert cache_sync.should_hydrate() is False

    def test_should_hydrate_handles_exception(self, cache_sync, mock_env):
        """Test that should_hydrate handles exceptions gracefully."""
        cache_sync._endpoint_id = "test-endpoint-123"

        with (
            patch.object(cache_sync, "should_sync", return_value=True),
            patch("os.path.exists", return_value=True),
            patch("os.path.getmtime", side_effect=OSError("Permission denied")),
        ):
            # Should return True on exception (safe default)
            assert cache_sync.should_hydrate() is True


class TestHydrateFromVolume:
    @pytest.mark.asyncio
    async def test_hydrate_skips_when_should_not_hydrate(self, cache_sync):
        """Test that hydrate_from_volume skips when should_hydrate returns False."""
        with (
            patch.object(cache_sync, "should_hydrate", return_value=False),
            patch("asyncio.to_thread") as mock_to_thread,
        ):
            await cache_sync.hydrate_from_volume()
            mock_to_thread.assert_not_called()

    @pytest.mark.asyncio
    async def test_hydrate_success(self, cache_sync, mock_env):
        """Test successful cache hydration from tarball."""
        cache_sync._endpoint_id = "test-endpoint-123"

        mock_tar_result = FunctionResponse(success=True, stdout="")

        with (
            patch.object(cache_sync, "should_hydrate", return_value=True),
            patch("os.makedirs") as mock_makedirs,
            patch.object(Path, "glob", return_value=[]),
            patch("asyncio.to_thread", return_value=mock_tar_result) as mock_to_thread,
            patch.object(cache_sync, "mark_last_hydrated") as mock_mark,
        ):
            await cache_sync.hydrate_from_volume()

            # Cache dir should be created
            mock_makedirs.assert_called_once_with("/root/.cache", exist_ok=True)
            # Tar extraction should be called
            assert mock_to_thread.call_count == 1
            # Hydration marker should be set
            mock_mark.assert_called_once()

    @pytest.mark.asyncio
    async def test_hydrate_tar_failure(self, cache_sync, mock_env):
        """Test handling of tar extraction failure."""
        cache_sync._endpoint_id = "test-endpoint-123"

        mock_tar_result = FunctionResponse(success=False, error="Extraction failed")

        with (
            patch.object(cache_sync, "should_hydrate", return_value=True),
            patch("os.makedirs"),
            patch.object(Path, "glob", return_value=[]),
            patch("asyncio.to_thread", return_value=mock_tar_result),
            patch.object(cache_sync, "mark_last_hydrated") as mock_mark,
        ):
            await cache_sync.hydrate_from_volume()

            # Marker should NOT be set on failure
            mock_mark.assert_not_called()

    @pytest.mark.asyncio
    async def test_hydrate_makedirs_failure(self, cache_sync, mock_env):
        """Test handling of cache directory creation failure."""
        cache_sync._endpoint_id = "test-endpoint-123"

        with (
            patch.object(cache_sync, "should_hydrate", return_value=True),
            patch("os.makedirs", side_effect=OSError("Permission denied")),
            patch("asyncio.to_thread") as mock_to_thread,
        ):
            await cache_sync.hydrate_from_volume()

            # Tar should not be attempted if mkdir fails
            mock_to_thread.assert_not_called()

    @pytest.mark.asyncio
    async def test_hydrate_handles_exception(self, cache_sync, mock_env):
        """Test that hydrate_from_volume handles unexpected exceptions."""
        cache_sync._endpoint_id = "test-endpoint-123"

        with (
            patch.object(cache_sync, "should_hydrate", return_value=True),
            patch("os.makedirs", side_effect=Exception("Unexpected error")),
        ):
            # Should not raise exception
            await cache_sync.hydrate_from_volume()


class TestMarkLastHydrated:
    def test_mark_last_hydrated_skips_when_should_not_sync(self, cache_sync):
        """Test that mark_last_hydrated skips when should_sync returns False."""
        with (
            patch.object(cache_sync, "should_sync", return_value=False),
            patch.object(Path, "touch") as mock_touch,
        ):
            cache_sync.mark_last_hydrated()
            # Should not touch the file when should_sync is False
            mock_touch.assert_not_called()

    def test_mark_last_hydrated_creates_marker(self, cache_sync, mock_env):
        """Test that mark_last_hydrated creates a marker file."""
        with (
            patch.object(cache_sync, "should_sync", return_value=True),
            patch.object(Path, "touch") as mock_touch,
        ):
            cache_sync.mark_last_hydrated()

            # Should touch the hydration marker path
            mock_touch.assert_called_once()

    def test_mark_last_hydrated_handles_exception(self, cache_sync, mock_env):
        """Test that mark_last_hydrated handles exceptions gracefully."""
        with (
            patch.object(cache_sync, "should_sync", return_value=True),
            patch.object(Path, "touch", side_effect=OSError("Permission denied")),
        ):
            # Should not raise exception
            cache_sync.mark_last_hydrated()
