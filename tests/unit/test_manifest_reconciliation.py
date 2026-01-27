"""Unit tests for manifest reconciliation module."""

import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
import time

from manifest_reconciliation import (
    refresh_manifest_if_stale,
    is_flash_deployment,
    _is_manifest_stale,
    _save_manifest,
    _fetch_and_save_manifest,
)


@pytest.fixture
def sample_manifest() -> dict:
    """Sample Flash manifest with endpoint URLs."""
    return {
        "version": "1.0",
        "project_name": "test_app",
        "resources": {
            "cpu_endpoint": {
                "resource_type": "CpuLiveLoadBalancer",
                "handler_file": "handler_cpu.py",
                "endpoint_url": "https://ep-cpu-001.runpod.io",
            },
            "gpu_endpoint": {
                "resource_type": "LiveLoadBalancer",
                "handler_file": "handler_gpu.py",
                "endpoint_url": "https://ep-gpu-001.runpod.io",
            },
        },
        "function_registry": {
            "cpu_func": "cpu_endpoint",
            "gpu_func": "gpu_endpoint",
        },
    }


class TestIsFlashDeployment:
    """Test Flash deployment detection."""

    def test_is_flash_deployment_mothership(self) -> None:
        """Test detection with FLASH_IS_MOTHERSHIP."""
        with patch.dict(
            "os.environ",
            {
                "RUNPOD_ENDPOINT_ID": "ep-001",
                "FLASH_IS_MOTHERSHIP": "true",
            },
        ):
            assert is_flash_deployment() is True

    def test_is_flash_deployment_resource_name(self) -> None:
        """Test detection with FLASH_RESOURCE_NAME."""
        with patch.dict(
            "os.environ",
            {
                "RUNPOD_ENDPOINT_ID": "ep-001",
                "FLASH_RESOURCE_NAME": "cpu_endpoint",
            },
            clear=False,
        ):
            assert is_flash_deployment() is True

    def test_is_flash_deployment_no_endpoint_id(self) -> None:
        """Test detection fails without RUNPOD_ENDPOINT_ID."""
        with patch.dict(
            "os.environ",
            {
                "FLASH_IS_MOTHERSHIP": "true",
            },
            clear=True,
        ):
            assert is_flash_deployment() is False

    def test_is_flash_deployment_not_flash(self) -> None:
        """Test detection fails for non-Flash deployment."""
        with patch.dict(
            "os.environ",
            {
                "RUNPOD_ENDPOINT_ID": "ep-001",
            },
            clear=True,
        ):
            assert is_flash_deployment() is False


class TestSaveManifest:
    """Test manifest saving."""

    def test_save_manifest_success(self, tmp_path: Path, sample_manifest: dict) -> None:
        """Test successful manifest save."""
        manifest_file = tmp_path / "manifest.json"

        result = _save_manifest(sample_manifest, manifest_file)

        assert result is True
        assert manifest_file.exists()
        saved = json.loads(manifest_file.read_text())
        assert saved == sample_manifest

    def test_save_manifest_permission_error(self, sample_manifest: dict) -> None:
        """Test save failure with permission error."""
        manifest_file = Mock(spec=Path)
        manifest_file.write_text.side_effect = OSError("Permission denied")

        result = _save_manifest(sample_manifest, manifest_file)

        assert result is False


class TestIsManifestStale:
    """Test manifest staleness detection."""

    def test_manifest_missing_is_stale(self, tmp_path: Path) -> None:
        """Test that missing manifest is considered stale."""
        manifest_file = tmp_path / "nonexistent.json"
        result = _is_manifest_stale(manifest_file)
        assert result is True

    def test_manifest_fresh_not_stale(self, tmp_path: Path, sample_manifest: dict) -> None:
        """Test that fresh manifest is not stale."""
        manifest_file = tmp_path / "manifest.json"
        manifest_file.write_text(json.dumps(sample_manifest))

        # Just created, should be fresh
        result = _is_manifest_stale(manifest_file, ttl_seconds=60)
        assert result is False

    def test_manifest_old_is_stale(self, tmp_path: Path, sample_manifest: dict) -> None:
        """Test that old manifest is considered stale."""
        manifest_file = tmp_path / "manifest.json"
        manifest_file.write_text(json.dumps(sample_manifest))

        # Set modification time to past
        old_time = time.time() - 400  # 400 seconds ago
        import os as os_module

        os_module.utime(manifest_file, (old_time, old_time))

        result = _is_manifest_stale(manifest_file, ttl_seconds=300)
        assert result is True

    def test_manifest_at_ttl_boundary(self, tmp_path: Path, sample_manifest: dict) -> None:
        """Test manifest at exact TTL boundary."""
        manifest_file = tmp_path / "manifest.json"
        manifest_file.write_text(json.dumps(sample_manifest))

        # Set modification time to exactly TTL ago
        old_time = time.time() - 300  # Exactly 5 minutes ago
        import os as os_module

        os_module.utime(manifest_file, (old_time, old_time))

        # At boundary should be considered stale (>= TTL)
        result = _is_manifest_stale(manifest_file, ttl_seconds=300)
        assert result is True

    def test_manifest_just_before_ttl(self, tmp_path: Path, sample_manifest: dict) -> None:
        """Test manifest just before TTL expiration."""
        manifest_file = tmp_path / "manifest.json"
        manifest_file.write_text(json.dumps(sample_manifest))

        # Set modification time to just under TTL
        old_time = time.time() - 299  # 1 second before TTL
        import os as os_module

        os_module.utime(manifest_file, (old_time, old_time))

        result = _is_manifest_stale(manifest_file, ttl_seconds=300)
        assert result is False


class TestFetchAndSaveManifest:
    """Test manifest fetch and save from State Manager."""

    @pytest.mark.asyncio
    async def test_fetch_and_save_success(self, tmp_path: Path, sample_manifest: dict) -> None:
        """Test successful fetch and save."""
        manifest_path = tmp_path / "manifest.json"
        endpoint_id = "ep-test-001"

        mock_client = AsyncMock()
        mock_client.get_persisted_manifest = AsyncMock(return_value=sample_manifest)

        with patch(
            "tetra_rp.runtime.state_manager_client.StateManagerClient", return_value=mock_client
        ):
            result = await _fetch_and_save_manifest(manifest_path, endpoint_id)

        assert result is True
        assert manifest_path.exists()
        saved = json.loads(manifest_path.read_text())
        assert saved == sample_manifest

    @pytest.mark.asyncio
    async def test_fetch_and_save_state_manager_unavailable(self, tmp_path: Path) -> None:
        """Test when State Manager is unavailable."""
        manifest_path = tmp_path / "manifest.json"
        endpoint_id = "ep-test-001"

        with patch(
            "tetra_rp.runtime.state_manager_client.StateManagerClient",
            side_effect=Exception("API error"),
        ):
            result = await _fetch_and_save_manifest(manifest_path, endpoint_id)

        assert result is False

    @pytest.mark.asyncio
    async def test_fetch_and_save_no_manifest(self, tmp_path: Path) -> None:
        """Test when State Manager has no manifest."""
        manifest_path = tmp_path / "manifest.json"
        endpoint_id = "ep-test-001"

        mock_client = AsyncMock()
        mock_client.get_persisted_manifest = AsyncMock(return_value=None)

        with patch(
            "tetra_rp.runtime.state_manager_client.StateManagerClient", return_value=mock_client
        ):
            result = await _fetch_and_save_manifest(manifest_path, endpoint_id)

        assert result is False

    @pytest.mark.asyncio
    async def test_fetch_and_save_write_error(self, sample_manifest: dict) -> None:
        """Test handling of write errors."""
        mock_path = Mock(spec=Path)
        mock_path.write_text.side_effect = OSError("Permission denied")

        mock_client = AsyncMock()
        mock_client.get_persisted_manifest = AsyncMock(return_value=sample_manifest)

        with patch(
            "tetra_rp.runtime.state_manager_client.StateManagerClient", return_value=mock_client
        ):
            result = await _fetch_and_save_manifest(mock_path, "ep-test-001")

        assert result is False


class TestRefreshManifestIfStale:
    """Test request-scoped manifest refresh with TTL."""

    @pytest.mark.asyncio
    async def test_refresh_not_flash_deployment(self, tmp_path: Path) -> None:
        """Test refresh skipped when not in Flash deployment."""
        manifest_path = tmp_path / "manifest.json"

        with patch.dict("os.environ", {}, clear=True):
            result = await refresh_manifest_if_stale(manifest_path)

        assert result is False

    @pytest.mark.asyncio
    async def test_refresh_no_endpoint_id(self, tmp_path: Path) -> None:
        """Test refresh skipped when RUNPOD_ENDPOINT_ID not set."""
        manifest_path = tmp_path / "manifest.json"

        with patch.dict("os.environ", {"FLASH_IS_MOTHERSHIP": "true"}, clear=True):
            result = await refresh_manifest_if_stale(manifest_path)

        assert result is False

    @pytest.mark.asyncio
    async def test_refresh_no_api_key(self, tmp_path: Path) -> None:
        """Test refresh skipped when RUNPOD_API_KEY not set."""
        manifest_path = tmp_path / "manifest.json"

        with patch.dict(
            "os.environ",
            {
                "RUNPOD_ENDPOINT_ID": "ep-001",
                "FLASH_IS_MOTHERSHIP": "true",
            },
            clear=True,
        ):
            result = await refresh_manifest_if_stale(manifest_path)

        assert result is False

    @pytest.mark.asyncio
    async def test_refresh_fresh_manifest_no_query(
        self, tmp_path: Path, sample_manifest: dict
    ) -> None:
        """Test fresh manifest skips State Manager query."""
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(sample_manifest))

        mock_client = AsyncMock()

        with patch.dict(
            "os.environ",
            {
                "RUNPOD_ENDPOINT_ID": "ep-test-001",
                "FLASH_IS_MOTHERSHIP": "true",
                "RUNPOD_API_KEY": "test-key",
            },
            clear=True,
        ):
            with patch(
                "tetra_rp.runtime.state_manager_client.StateManagerClient", return_value=mock_client
            ):
                result = await refresh_manifest_if_stale(manifest_path, ttl_seconds=300)

        assert result is True
        # Should not query State Manager for fresh manifest
        mock_client.get_persisted_manifest.assert_not_called()

    @pytest.mark.asyncio
    async def test_refresh_stale_manifest_queries_state_manager(
        self, tmp_path: Path, sample_manifest: dict
    ) -> None:
        """Test stale manifest queries State Manager."""
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(sample_manifest))

        # Set modification time to old
        old_time = time.time() - 400
        import os as os_module

        os_module.utime(manifest_path, (old_time, old_time))

        updated_manifest = {
            **sample_manifest,
            "resources": {
                **sample_manifest["resources"],
                "cpu_endpoint": {
                    **sample_manifest["resources"]["cpu_endpoint"],
                    "endpoint_url": "https://ep-cpu-new.runpod.io",
                },
            },
        }

        mock_client = AsyncMock()
        mock_client.get_persisted_manifest = AsyncMock(return_value=updated_manifest)

        with patch.dict(
            "os.environ",
            {
                "RUNPOD_ENDPOINT_ID": "ep-test-001",
                "FLASH_IS_MOTHERSHIP": "true",
                "RUNPOD_API_KEY": "test-key",
            },
            clear=True,
        ):
            with patch(
                "tetra_rp.runtime.state_manager_client.StateManagerClient", return_value=mock_client
            ):
                result = await refresh_manifest_if_stale(manifest_path, ttl_seconds=300)

        assert result is True
        mock_client.get_persisted_manifest.assert_called_once()

        # Verify manifest was updated
        saved = json.loads(manifest_path.read_text())
        assert saved["resources"]["cpu_endpoint"]["endpoint_url"] == "https://ep-cpu-new.runpod.io"

    @pytest.mark.asyncio
    async def test_refresh_state_manager_error_continues(
        self, tmp_path: Path, sample_manifest: dict
    ) -> None:
        """Test refresh continues with stale manifest on State Manager error."""
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(sample_manifest))

        # Set modification time to old
        old_time = time.time() - 400
        import os as os_module

        os_module.utime(manifest_path, (old_time, old_time))

        mock_client = AsyncMock()
        mock_client.get_persisted_manifest = AsyncMock(side_effect=Exception("API timeout"))

        with patch.dict(
            "os.environ",
            {
                "RUNPOD_ENDPOINT_ID": "ep-test-001",
                "FLASH_IS_MOTHERSHIP": "true",
                "RUNPOD_API_KEY": "test-key",
            },
            clear=True,
        ):
            with patch(
                "tetra_rp.runtime.state_manager_client.StateManagerClient", return_value=mock_client
            ):
                result = await refresh_manifest_if_stale(manifest_path, ttl_seconds=300)

        # Should return True (non-fatal error)
        assert result is True

        # Manifest should be unchanged (refresh failed)
        saved = json.loads(manifest_path.read_text())
        assert saved == sample_manifest

    @pytest.mark.asyncio
    async def test_refresh_custom_ttl(self, tmp_path: Path, sample_manifest: dict) -> None:
        """Test refresh with custom TTL value."""
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(sample_manifest))

        # Set modification time to 50 seconds old
        old_time = time.time() - 50
        import os as os_module

        os_module.utime(manifest_path, (old_time, old_time))

        mock_client = AsyncMock()

        with patch.dict(
            "os.environ",
            {
                "RUNPOD_ENDPOINT_ID": "ep-test-001",
                "FLASH_IS_MOTHERSHIP": "true",
                "RUNPOD_API_KEY": "test-key",
            },
            clear=True,
        ):
            with patch(
                "tetra_rp.runtime.state_manager_client.StateManagerClient", return_value=mock_client
            ):
                # With TTL of 100 seconds, 50-second-old manifest should be fresh
                result = await refresh_manifest_if_stale(manifest_path, ttl_seconds=100)

        assert result is True
        # Should not query State Manager for fresh manifest
        mock_client.get_persisted_manifest.assert_not_called()
