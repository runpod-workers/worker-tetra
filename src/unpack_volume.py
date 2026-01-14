from __future__ import annotations

import logging
import os
import sys
import tarfile
import threading
from pathlib import Path

from constants import DEFAULT_APP_DIR, DEFAULT_ARTIFACT_PATH

logger = logging.getLogger(__name__)


def _safe_extract_tar(tar: tarfile.TarFile, target_dir: Path) -> None:
    target_dir_resolved = target_dir.resolve()

    for member in tar.getmembers():
        member_path = (target_dir / member.name).resolve()
        if not member_path.is_relative_to(target_dir_resolved):
            raise ValueError(f"unsafe tar member path: {member.name}")

    tar.extractall(path=target_dir)


def _canonical_project_artifact_path() -> Path:
    return Path(os.getenv("FLASH_BUILD_ARTIFACT_PATH", DEFAULT_ARTIFACT_PATH))


def unpack_app_from_volume(
    *,
    app_dir: str | Path = DEFAULT_APP_DIR,
) -> bool:
    """Extract the build artifact from the volume into the app directory.

    Args:
        app_dir: Target directory for extraction (default: /app)

    Returns:
        True if extraction succeeds

    Raises:
        FileNotFoundError: If the artifact file is not found
        RuntimeError: If extraction fails
    """

    app_dir_path = Path(app_dir)
    app_dir_path.mkdir(parents=True, exist_ok=True)

    # ensure /app is importable
    app_dir_str = str(app_dir_path)
    if app_dir_str not in sys.path:
        sys.path.insert(0, app_dir_str)

    artifact = _canonical_project_artifact_path()

    if not artifact.exists() or not artifact.is_file():
        raise FileNotFoundError(f"flash build artifact not found at {artifact}")

    try:
        with tarfile.open(artifact, mode="r:*") as tf:
            _safe_extract_tar(tf, app_dir_path)
    except (OSError, tarfile.TarError, ValueError) as e:
        raise RuntimeError(f"failed to extract flash artifact: {e}") from e

    logger.info("successfully extracted build artifact to %s", app_dir_path)
    return True


_UNPACKED = False
_UNPACK_LOCK = threading.Lock()


def _should_unpack_from_volume() -> bool:
    """Determine if Flash artifact unpacking should occur.

    Returns True only for Flash-deployed apps, not Live Serverless.

    Detection logic:
    1. Honor explicit disable flag (FLASH_DISABLE_UNPACK)
    2. Must be in RunPod environment (RUNPOD_POD_ID or RUNPOD_ENDPOINT_ID)
    3. Must be Flash deployment (any of FLASH_IS_MOTHERSHIP, FLASH_MOTHERSHIP_ID, FLASH_RESOURCE_NAME)

    Returns:
        bool: True if unpacking should occur, False otherwise
    """
    # Honor explicit disable flag
    disable_value = os.getenv("FLASH_DISABLE_UNPACK", "").lower()
    if disable_value in {"1", "true", "yes"}:
        logger.debug("unpacking disabled via FLASH_DISABLE_UNPACK")
        return False

    # Must be in RunPod environment
    in_runpod = os.getenv("RUNPOD_POD_ID") or os.getenv("RUNPOD_ENDPOINT_ID")
    if not in_runpod:
        logger.debug("not in RunPod environment, skipping unpacking")
        return False

    # Check if Flash deployment (any Flash-specific env var set)
    is_flash = any(
        [
            os.getenv("FLASH_IS_MOTHERSHIP") == "true",
            os.getenv("FLASH_MOTHERSHIP_ID"),
            os.getenv("FLASH_RESOURCE_NAME"),
        ]
    )

    if is_flash:
        logger.debug("Flash deployment detected, will unpack artifact")
    else:
        logger.debug("Live Serverless deployment detected, skipping unpacking")

    return is_flash


def maybe_unpack():
    """Unpack build artifact from volume if conditions are met.

    Thread-safe: multiple concurrent calls will only unpack once.
    """
    global _UNPACKED

    # Fast path: check without lock first
    if _UNPACKED:
        return
    if not _should_unpack_from_volume():
        return

    # Slow path: acquire lock and check again
    with _UNPACK_LOCK:
        if _UNPACKED:
            return

        _UNPACKED = True
        logger.info("unpacking app from volume")

        try:
            unpack_app_from_volume()
        except (FileNotFoundError, RuntimeError) as e:
            logger.error("failed to unpack app from volume: %s", e, exc_info=True)
            raise RuntimeError(f"failed to unpack app from volume: {e}") from e
