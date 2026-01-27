"""Manifest reconciliation and synchronization with State Manager.

This module handles on-demand manifest refresh from State Manager using a
TTL-based staleness check. Manifest refresh happens during cross-endpoint
routing, not at boot or in background threads (serverless-compatible).
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict

from constants import FLASH_MANIFEST_PATH


logger = logging.getLogger(__name__)

# Default TTL for manifest staleness (5 minutes)
DEFAULT_MANIFEST_TTL_SECONDS = 300


def is_flash_deployment() -> bool:
    """Check if running in Flash deployment mode.

    Returns:
        True if running as a Flash endpoint, False otherwise.
    """
    endpoint_id = os.getenv("RUNPOD_ENDPOINT_ID")
    is_flash = any(
        [
            os.getenv("FLASH_IS_MOTHERSHIP") == "true",
            os.getenv("FLASH_RESOURCE_NAME"),
        ]
    )
    return bool(endpoint_id and is_flash)


def _save_manifest(manifest: Dict[str, Any], manifest_path: Path) -> bool:
    """Save manifest to file.

    Args:
        manifest: Manifest dict to save.
        manifest_path: Path to write to.

    Returns:
        True if successful, False otherwise.
    """
    try:
        manifest_path.write_text(json.dumps(manifest, indent=2))
        return True
    except OSError as e:
        logger.error(f"Failed to write manifest to {manifest_path}: {e}")
        return False


def _is_manifest_stale(
    manifest_path: Path,
    ttl_seconds: int = DEFAULT_MANIFEST_TTL_SECONDS,
) -> bool:
    """Check if manifest file is older than TTL.

    Args:
        manifest_path: Path to manifest file.
        ttl_seconds: Maximum age before considering stale (default 5 min).

    Returns:
        True if manifest is stale or missing, False if fresh.
    """
    if not manifest_path.exists():
        return True  # Missing manifest is always stale

    try:
        mtime = manifest_path.stat().st_mtime
        age_seconds = time.time() - mtime
        is_stale = age_seconds >= ttl_seconds
        if is_stale:
            logger.debug(f"Manifest is stale: {age_seconds:.0f}s old (TTL: {ttl_seconds}s)")
        return is_stale
    except OSError:
        return True  # Error reading file, consider stale


async def _fetch_and_save_manifest(
    manifest_path: Path,
    endpoint_id: str,
) -> bool:
    """Fetch manifest from State Manager and save to disk.

    Args:
        manifest_path: Path to write manifest.
        endpoint_id: Current endpoint ID for State Manager query.

    Returns:
        True if successful, False on error.
    """
    try:
        from tetra_rp.runtime.state_manager_client import StateManagerClient  # type: ignore[import-untyped]

        state_client = StateManagerClient()
        state_manifest = await state_client.get_persisted_manifest(endpoint_id)

        if not state_manifest:
            logger.warning("No manifest in State Manager")
            return False

        # Write State Manager manifest (State Manager wins)
        if not _save_manifest(state_manifest, manifest_path):
            return False

        logger.info("Manifest refreshed from State Manager")
        return True

    except Exception as e:
        logger.warning(f"Failed to refresh manifest from State Manager: {e}")
        return False


async def refresh_manifest_if_stale(
    manifest_path: Path = Path(FLASH_MANIFEST_PATH),
    ttl_seconds: int = DEFAULT_MANIFEST_TTL_SECONDS,
) -> bool:
    """Refresh manifest from State Manager if stale (older than TTL).

    This function is called by RemoteExecutor before cross-endpoint routing.
    It checks the manifest file modification time and only queries State Manager
    if the manifest is older than the TTL.

    Flow:
    1. Check manifest file modification time
    2. If fresh (< TTL): return immediately (no State Manager query)
    3. If stale (>= TTL):
       - Query State Manager for persisted manifest
       - Write State Manager manifest to disk (State Manager wins)
       - Return success
    4. If State Manager unavailable: log warning, use stale manifest

    Args:
        manifest_path: Local manifest file path (default: /app/flash_manifest.json)
        ttl_seconds: Maximum age before refresh (default 300 = 5 minutes)

    Returns:
        True if manifest is fresh or refresh succeeded, False on error.
    """
    # Skip if not in Flash deployment
    if not is_flash_deployment():
        return False

    endpoint_id = os.getenv("RUNPOD_ENDPOINT_ID")
    if not endpoint_id:
        logger.debug("RUNPOD_ENDPOINT_ID not set, skipping manifest refresh")
        return False

    api_key = os.getenv("RUNPOD_API_KEY")
    if not api_key:
        logger.debug("RUNPOD_API_KEY not set, skipping manifest refresh")
        return False

    # Check if manifest is fresh (no refresh needed)
    if not _is_manifest_stale(manifest_path, ttl_seconds):
        logger.debug("Manifest is fresh, skipping refresh")
        return True

    # Manifest is stale, query State Manager
    logger.debug("Manifest is stale, refreshing from State Manager")
    success = await _fetch_and_save_manifest(manifest_path, endpoint_id)

    if not success:
        logger.warning("Manifest refresh failed, continuing with potentially stale manifest")
        # Non-fatal: continue with stale manifest

    return True
