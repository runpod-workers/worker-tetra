"""
Tarball loader for Flash Server startup.

Downloads and extracts project tarballs from RunPod network volumes before server starts.
"""

import logging
import os
import tarfile
from pathlib import Path

log = logging.getLogger(__name__)


def should_load_tarball() -> bool:
    """Check if tarball loading is enabled."""
    return bool(os.getenv("TETRA_CODE_TARBALL"))


def download_and_extract_tarball() -> bool:
    """
    Download and extract project tarball from network volume.

    Environment variables:
        TETRA_CODE_TARBALL: S3 key of tarball to download
        RUNPOD_VOLUME_ENDPOINT: S3-compatible endpoint URL
        RUNPOD_VOLUME_ACCESS_KEY: S3 access key
        RUNPOD_VOLUME_SECRET_KEY: S3 secret key
        RUNPOD_VOLUME_BUCKET: S3 bucket name

    Returns:
        True if successful, False otherwise
    """
    tarball_key = os.getenv("TETRA_CODE_TARBALL")
    if not tarball_key:
        log.info("No TETRA_CODE_TARBALL specified - skipping tarball loading")
        return True

    log.info(f"Loading project tarball: {tarball_key}")

    # Check if already extracted
    project_dir = Path("/app/project")
    marker_file = project_dir / ".tarball_loaded"

    if marker_file.exists():
        log.info(f"Project already extracted at {project_dir}")
        return True

    # Get volume configuration
    endpoint_url = os.getenv("RUNPOD_VOLUME_ENDPOINT")
    access_key = os.getenv("RUNPOD_VOLUME_ACCESS_KEY")
    secret_key = os.getenv("RUNPOD_VOLUME_SECRET_KEY")
    bucket_name = os.getenv("RUNPOD_VOLUME_BUCKET", "tetra-code")

    if not all([endpoint_url, access_key, secret_key]):
        log.error(
            "Volume not configured - missing RUNPOD_VOLUME_* environment variables"
        )
        return False

    try:
        import boto3

        # Create S3 client
        s3 = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name="eu-ro-1",
        )

        # Download tarball to temp location
        tarball_path = Path("/tmp") / "project.tar.gz"
        tarball_path.parent.mkdir(parents=True, exist_ok=True)

        log.info(f"   Downloading from s3://{bucket_name}/{tarball_key}")
        s3.download_file(bucket_name, tarball_key, str(tarball_path))

        size_kb = tarball_path.stat().st_size / 1024
        log.info(f"   Downloaded: {size_kb:.1f} KB")

        # Extract to /app/project
        project_dir.mkdir(parents=True, exist_ok=True)
        log.info(f"   Extracting to {project_dir}")

        with tarfile.open(tarball_path, "r:gz") as tar:
            tar.extractall(project_dir)

        # Create marker file
        marker_file.write_text(tarball_key)

        log.info("Project tarball loaded successfully")
        log.info(f"   Location: {project_dir}")

        # Clean up temp file
        tarball_path.unlink()

        return True

    except ImportError:
        log.error("boto3 not installed - cannot download from volume")
        log.error("   Install with: pip install boto3")
        return False

    except Exception as e:
        log.error(f"Failed to load tarball: {e}")
        return False


if __name__ == "__main__":
    # Can be run standalone for testing
    logging.basicConfig(level=logging.INFO)
    success = download_and_extract_tarball()
    exit(0 if success else 1)
