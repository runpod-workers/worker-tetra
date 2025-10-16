"""
Tarball loader for production worker code execution.

Handles loading and extraction of worker code tarballs from RunPod network volumes
at worker startup time for production deployments.
"""

import logging
import os
import tarfile
from pathlib import Path

from constants import WORKERS_CODE_DIR

log = logging.getLogger(__name__)


def should_load_tarball() -> bool:
    """
    Check if tarball loading is enabled.

    Returns:
        True if TETRA_TARBALL_PATH environment variable is set, False otherwise.
    """
    return bool(os.getenv("TETRA_TARBALL_PATH"))


def load_and_extract_tarball() -> bool:
    """
    Load and extract code tarball from network volume.

    The tarball path is configurable via TETRA_TARBALL_PATH environment variable.
    Extraction is skipped if code is already present (registry.json exists).

    Environment variables:
        TETRA_TARBALL_PATH: Path to tarball on mounted volume
            Example: /runpod-volume/projects/my-project/workers.tar.gz

    Returns:
        True if successful or already extracted, False on error.
    """
    tarball_path_str = os.getenv("TETRA_TARBALL_PATH")
    if not tarball_path_str:
        log.info("TETRA_TARBALL_PATH not set, skipping tarball loading")
        return True

    tarball_path = Path(tarball_path_str)
    extract_dir = Path(WORKERS_CODE_DIR)
    registry_file = extract_dir / "registry.json"

    log.info(f"Tarball loading initiated: {tarball_path}")

    # Check if already extracted
    if registry_file.exists():
        log.info(f"Code already extracted at {extract_dir}, skipping extraction")
        return True

    # Validate tarball exists
    if not tarball_path.exists():
        log.error(f"Tarball not found at path: {tarball_path}")
        log.error("Verify network volume is mounted and path is correct")
        return False

    try:
        # Log tarball metadata
        size_bytes = tarball_path.stat().st_size
        size_mb = size_bytes / (1024 * 1024)
        log.info(f"Tarball size: {size_mb:.2f} MB")

        # Create extraction directory
        extract_dir.mkdir(parents=True, exist_ok=True)
        log.info(f"Extracting tarball to {extract_dir}")

        # Extract tarball
        with tarfile.open(tarball_path, "r:gz") as tar:
            tar.extractall(extract_dir)

        # Verify extraction succeeded
        if not registry_file.exists():
            log.error("Extraction failed: registry.json not found after extraction")
            return False

        log.info("Tarball extraction completed successfully")
        return True

    except tarfile.TarError as e:
        log.error(f"Tarball extraction failed: {e}")
        return False
    except Exception as e:
        log.error(f"Unexpected error during tarball loading: {e}")
        return False
