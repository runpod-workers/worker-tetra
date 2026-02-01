"""Integration tests for request-scoped manifest refresh."""

import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

from manifest_reconciliation import refresh_manifest_if_stale
import time


@pytest.fixture
def complete_manifest_data() -> dict:
    """Complete Flash manifest with all endpoint URLs."""
    return {
        "version": "1.0",
        "generated_at": "2026-01-22T00:00:00Z",
        "project_name": "integration_test",
        "resources": {
            "cpu_endpoint": {
                "resource_type": "CpuLiveLoadBalancer",
                "endpoint_url": "https://ep-cpu-001.runpod.io",
                "config_hash": "abc123",
                "status": "healthy",
                "functions": [
                    {
                        "name": "cpu_task",
                        "module": "workers.cpu",
                        "is_async": True,
                        "is_class": False,
                    }
                ],
            },
            "gpu_endpoint": {
                "resource_type": "LiveLoadBalancer",
                "endpoint_url": "https://ep-gpu-001.runpod.io",
                "config_hash": "def456",
                "status": "healthy",
                "functions": [
                    {
                        "name": "gpu_inference",
                        "module": "workers.gpu",
                        "is_async": True,
                        "is_class": False,
                    }
                ],
            },
        },
        "function_registry": {
            "cpu_task": "cpu_endpoint",
            "gpu_inference": "gpu_endpoint",
        },
        "routes": {
            "gpu_endpoint": {
                "POST /infer": "gpu_inference",
            }
        },
    }


@pytest.fixture
def local_manifest_data() -> dict:
    """Local manifest without endpoint URLs (build artifact)."""
    return {
        "version": "1.0",
        "generated_at": "2026-01-22T00:00:00Z",
        "project_name": "integration_test",
        "resources": {
            "cpu_endpoint": {
                "resource_type": "CpuLiveLoadBalancer",
                "config_hash": "abc123",
                "functions": [
                    {
                        "name": "cpu_task",
                        "module": "workers.cpu",
                        "is_async": True,
                        "is_class": False,
                    }
                ],
            },
            "gpu_endpoint": {
                "resource_type": "LiveLoadBalancer",
                "config_hash": "def456",
                "functions": [
                    {
                        "name": "gpu_inference",
                        "module": "workers.gpu",
                        "is_async": True,
                        "is_class": False,
                    }
                ],
            },
        },
        "function_registry": {
            "cpu_task": "cpu_endpoint",
            "gpu_inference": "gpu_endpoint",
        },
        "routes": {
            "gpu_endpoint": {
                "POST /infer": "gpu_inference",
            }
        },
    }


class TestRequestScopedManifestRefresh:
    """Test request-scoped manifest refresh during execution."""

    @pytest.mark.asyncio
    async def test_manifest_refresh_on_cross_endpoint_routing(
        self, tmp_path: Path, local_manifest_data: dict, complete_manifest_data: dict
    ) -> None:
        """Test manifest refreshes during cross-endpoint routing."""
        manifest_path = tmp_path / "flash_manifest.json"
        manifest_path.write_text(json.dumps(local_manifest_data))

        # Set manifest to stale
        old_time = time.time() - 400
        import os as os_module

        os_module.utime(manifest_path, (old_time, old_time))

        mock_client = AsyncMock()
        mock_client.get_persisted_manifest = AsyncMock(return_value=complete_manifest_data)

        with patch.dict(
            "os.environ",
            {
                "RUNPOD_ENDPOINT_ID": "ep-test-001",
                "FLASH_IS_MOTHERSHIP": "true",
                "RUNPOD_API_KEY": "test-api-key",
            },
            clear=True,
        ):
            with patch(
                "tetra_rp.runtime.state_manager_client.StateManagerClient", return_value=mock_client
            ):
                result = await refresh_manifest_if_stale(manifest_path, ttl_seconds=300)

        assert result is True
        mock_client.get_persisted_manifest.assert_called_once()

        # Verify manifest now has endpoint URLs
        saved = json.loads(manifest_path.read_text())
        assert saved["resources"]["cpu_endpoint"]["endpoint_url"] == "https://ep-cpu-001.runpod.io"
        assert saved["resources"]["gpu_endpoint"]["endpoint_url"] == "https://ep-gpu-001.runpod.io"

    @pytest.mark.asyncio
    async def test_manifest_refresh_skipped_if_fresh(
        self, tmp_path: Path, local_manifest_data: dict
    ) -> None:
        """Test fresh manifest skips refresh."""
        manifest_path = tmp_path / "flash_manifest.json"
        manifest_path.write_text(json.dumps(local_manifest_data))

        mock_client = AsyncMock()

        with patch.dict(
            "os.environ",
            {
                "RUNPOD_ENDPOINT_ID": "ep-test-001",
                "FLASH_IS_MOTHERSHIP": "true",
                "RUNPOD_API_KEY": "test-api-key",
            },
            clear=True,
        ):
            with patch(
                "tetra_rp.runtime.state_manager_client.StateManagerClient", return_value=mock_client
            ):
                result = await refresh_manifest_if_stale(manifest_path, ttl_seconds=300)

        assert result is True
        # Fresh manifest should not query State Manager
        mock_client.get_persisted_manifest.assert_not_called()

    @pytest.mark.asyncio
    async def test_manifest_refresh_continues_on_failure(
        self, tmp_path: Path, local_manifest_data: dict
    ) -> None:
        """Test execution continues if manifest refresh fails."""
        manifest_path = tmp_path / "flash_manifest.json"
        manifest_path.write_text(json.dumps(local_manifest_data))

        # Set manifest to stale
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
                "RUNPOD_API_KEY": "test-api-key",
            },
            clear=True,
        ):
            with patch(
                "tetra_rp.runtime.state_manager_client.StateManagerClient", return_value=mock_client
            ):
                result = await refresh_manifest_if_stale(manifest_path, ttl_seconds=300)

        # Should return True (non-fatal error)
        assert result is True

        # Manifest should be unchanged
        saved = json.loads(manifest_path.read_text())
        assert saved == local_manifest_data

    @pytest.mark.asyncio
    async def test_state_manager_unavailable_graceful_degradation(
        self, tmp_path: Path, local_manifest_data: dict
    ) -> None:
        """Test graceful degradation when State Manager unavailable."""
        manifest_path = tmp_path / "flash_manifest.json"
        manifest_path.write_text(json.dumps(local_manifest_data))

        # Set manifest to stale
        old_time = time.time() - 400
        import os as os_module

        os_module.utime(manifest_path, (old_time, old_time))

        with patch.dict(
            "os.environ",
            {
                "RUNPOD_ENDPOINT_ID": "ep-test-001",
                "FLASH_IS_MOTHERSHIP": "true",
                "RUNPOD_API_KEY": "test-api-key",
            },
            clear=True,
        ):
            with patch(
                "tetra_rp.runtime.state_manager_client.StateManagerClient",
                side_effect=Exception("Connection refused"),
            ):
                result = await refresh_manifest_if_stale(manifest_path, ttl_seconds=300)

        # Should return True (non-fatal)
        assert result is True

    @pytest.mark.asyncio
    async def test_local_only_execution_no_refresh(
        self, tmp_path: Path, local_manifest_data: dict
    ) -> None:
        """Test local-only execution never refreshes manifest."""
        manifest_path = tmp_path / "flash_manifest.json"
        manifest_path.write_text(json.dumps(local_manifest_data))

        # Set manifest to stale
        old_time = time.time() - 400
        import os as os_module

        os_module.utime(manifest_path, (old_time, old_time))

        # Simulate Live Serverless (not Flash deployment)
        mock_client = AsyncMock()

        with patch.dict("os.environ", {}, clear=True):
            with patch(
                "tetra_rp.runtime.state_manager_client.StateManagerClient", return_value=mock_client
            ):
                result = await refresh_manifest_if_stale(manifest_path, ttl_seconds=300)

        # Should return False (not Flash deployment)
        assert result is False

        # State Manager should never be queried
        mock_client.get_persisted_manifest.assert_not_called()

        # Manifest should be unchanged
        saved = json.loads(manifest_path.read_text())
        assert saved == local_manifest_data


class TestManifestAsSourceOfTruth:
    """Test State Manager as source of truth."""

    @pytest.mark.asyncio
    async def test_state_manager_overwrites_local(
        self, tmp_path: Path, complete_manifest_data: dict
    ) -> None:
        """Test that State Manager manifest overwrites local."""
        manifest_path = tmp_path / "flash_manifest.json"

        # Write initial local manifest with different endpoint URLs
        old_manifest = {
            **complete_manifest_data,
            "resources": {
                "cpu_endpoint": {
                    **complete_manifest_data["resources"]["cpu_endpoint"],
                    "endpoint_url": "https://old-cpu.runpod.io",
                },
                "gpu_endpoint": {
                    **complete_manifest_data["resources"]["gpu_endpoint"],
                    "endpoint_url": "https://old-gpu.runpod.io",
                },
            },
        }
        manifest_path.write_text(json.dumps(old_manifest))

        # Set manifest to stale
        old_time = time.time() - 400
        import os as os_module

        os_module.utime(manifest_path, (old_time, old_time))

        mock_client = AsyncMock()
        mock_client.get_persisted_manifest = AsyncMock(return_value=complete_manifest_data)

        with patch.dict(
            "os.environ",
            {
                "RUNPOD_ENDPOINT_ID": "ep-test-001",
                "FLASH_IS_MOTHERSHIP": "true",
                "RUNPOD_API_KEY": "test-api-key",
            },
            clear=True,
        ):
            with patch(
                "tetra_rp.runtime.state_manager_client.StateManagerClient", return_value=mock_client
            ):
                result = await refresh_manifest_if_stale(manifest_path, ttl_seconds=300)

        assert result is True

        # Verify local was overwritten with State Manager values
        saved = json.loads(manifest_path.read_text())
        assert saved["resources"]["cpu_endpoint"]["endpoint_url"] == "https://ep-cpu-001.runpod.io"
        assert saved["resources"]["gpu_endpoint"]["endpoint_url"] == "https://ep-gpu-001.runpod.io"

    @pytest.mark.asyncio
    async def test_state_manager_provides_additional_metadata(
        self, tmp_path: Path, local_manifest_data: dict, complete_manifest_data: dict
    ) -> None:
        """Test State Manager provides provisioning-time metadata."""
        manifest_path = tmp_path / "flash_manifest.json"
        manifest_path.write_text(json.dumps(local_manifest_data))

        # Set manifest to stale
        old_time = time.time() - 400
        import os as os_module

        os_module.utime(manifest_path, (old_time, old_time))

        # State manifest has additional fields from provisioning
        enhanced_manifest = {
            **complete_manifest_data,
            "resources": {
                "cpu_endpoint": {
                    **complete_manifest_data["resources"]["cpu_endpoint"],
                    "provisioned_at": "2026-01-22T10:30:00Z",
                    "pod_id": "ep-cpu-001-pod",
                    "machine_type": "CPU",
                },
                "gpu_endpoint": {
                    **complete_manifest_data["resources"]["gpu_endpoint"],
                    "provisioned_at": "2026-01-22T10:31:00Z",
                    "pod_id": "ep-gpu-001-pod",
                    "machine_type": "RTX4090",
                },
            },
        }

        mock_client = AsyncMock()
        mock_client.get_persisted_manifest = AsyncMock(return_value=enhanced_manifest)

        with patch.dict(
            "os.environ",
            {
                "RUNPOD_ENDPOINT_ID": "ep-test-001",
                "FLASH_IS_MOTHERSHIP": "true",
                "RUNPOD_API_KEY": "test-api-key",
            },
            clear=True,
        ):
            with patch(
                "tetra_rp.runtime.state_manager_client.StateManagerClient", return_value=mock_client
            ):
                result = await refresh_manifest_if_stale(manifest_path, ttl_seconds=300)

        assert result is True

        # Verify local contains State Manager's additional metadata
        saved = json.loads(manifest_path.read_text())
        assert saved["resources"]["cpu_endpoint"]["provisioned_at"] == "2026-01-22T10:30:00Z"
        assert saved["resources"]["gpu_endpoint"]["machine_type"] == "RTX4090"


class TestErrorHandling:
    """Test error handling in manifest refresh."""

    @pytest.mark.asyncio
    async def test_fallback_to_local_on_state_manager_error(
        self, tmp_path: Path, local_manifest_data: dict
    ) -> None:
        """Test fallback to local manifest when State Manager errors."""
        manifest_path = tmp_path / "flash_manifest.json"
        manifest_path.write_text(json.dumps(local_manifest_data))

        # Set manifest to stale
        old_time = time.time() - 400
        import os as os_module

        os_module.utime(manifest_path, (old_time, old_time))

        mock_client = AsyncMock()
        mock_client.get_persisted_manifest = AsyncMock(side_effect=Exception("GraphQL API timeout"))

        with patch.dict(
            "os.environ",
            {
                "RUNPOD_ENDPOINT_ID": "ep-test-001",
                "FLASH_IS_MOTHERSHIP": "true",
                "RUNPOD_API_KEY": "test-api-key",
            },
            clear=True,
        ):
            with patch(
                "tetra_rp.runtime.state_manager_client.StateManagerClient", return_value=mock_client
            ):
                result = await refresh_manifest_if_stale(manifest_path, ttl_seconds=300)

        assert result is True

        # Local manifest should be unchanged
        saved = json.loads(manifest_path.read_text())
        assert saved == local_manifest_data

    @pytest.mark.asyncio
    async def test_manifest_file_write_error(
        self, local_manifest_data: dict, complete_manifest_data: dict
    ) -> None:
        """Test handling of file write errors."""
        mock_client = AsyncMock()
        mock_client.get_persisted_manifest = AsyncMock(return_value=complete_manifest_data)

        # Create mock path that fails on write
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.stat.return_value.st_mtime = time.time() - 400
        mock_path.write_text.side_effect = OSError("Permission denied")

        with patch.dict(
            "os.environ",
            {
                "RUNPOD_ENDPOINT_ID": "ep-test-001",
                "FLASH_IS_MOTHERSHIP": "true",
                "RUNPOD_API_KEY": "test-api-key",
            },
            clear=True,
        ):
            with patch(
                "tetra_rp.runtime.state_manager_client.StateManagerClient",
                return_value=mock_client,
            ):
                result = await refresh_manifest_if_stale(mock_path)

        assert result is True  # Non-fatal error


class TestTTLBasedStaleness:
    """Test TTL-based staleness detection."""

    @pytest.mark.asyncio
    async def test_multiple_refreshes_with_ttl(
        self, tmp_path: Path, local_manifest_data: dict, complete_manifest_data: dict
    ) -> None:
        """Test multiple refresh calls respect TTL."""
        manifest_path = tmp_path / "flash_manifest.json"
        manifest_path.write_text(json.dumps(local_manifest_data))

        mock_client = AsyncMock()
        mock_client.get_persisted_manifest = AsyncMock(return_value=complete_manifest_data)

        with patch.dict(
            "os.environ",
            {
                "RUNPOD_ENDPOINT_ID": "ep-test-001",
                "FLASH_IS_MOTHERSHIP": "true",
                "RUNPOD_API_KEY": "test-api-key",
            },
            clear=True,
        ):
            with patch(
                "tetra_rp.runtime.state_manager_client.StateManagerClient", return_value=mock_client
            ):
                # First refresh - manifest is fresh, no State Manager query
                result1 = await refresh_manifest_if_stale(manifest_path, ttl_seconds=60)
                assert result1 is True
                assert mock_client.get_persisted_manifest.call_count == 0

                # Second refresh immediately - still fresh, no query
                result2 = await refresh_manifest_if_stale(manifest_path, ttl_seconds=60)
                assert result2 is True
                assert mock_client.get_persisted_manifest.call_count == 0

                # Simulate time passing - manifest becomes stale
                old_time = time.time() - 70
                import os as os_module

                os_module.utime(manifest_path, (old_time, old_time))

                # Third refresh - manifest is stale, should query
                result3 = await refresh_manifest_if_stale(manifest_path, ttl_seconds=60)
                assert result3 is True
                assert mock_client.get_persisted_manifest.call_count == 1
