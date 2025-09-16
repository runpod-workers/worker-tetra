"""
Download acceleration using hf_transfer for optimal HuggingFace model downloads.

This module provides accelerated download capabilities optimized for HuggingFace models:
- hf_transfer for accelerated downloads when available
- hf_xet acceleration is automatically handled by HuggingFace Hub (huggingface_hub>=0.32.0)
- Standard HF hub as reliable fallback
"""

import os
import time
import logging
from dataclasses import dataclass
from typing import Optional

from remote_execution import FunctionResponse
from constants import (
    MIN_SIZE_FOR_ACCELERATION_MB,
    HF_TRANSFER_ENABLED,
)


@dataclass
class DownloadMetrics:
    """Performance metrics for download operations."""

    method: str
    file_size_bytes: int
    total_time_seconds: float
    average_speed_mbps: float
    success: bool
    error_message: Optional[str] = None

    @property
    def speed_mb_per_sec(self) -> float:
        """Convert to MB/s for easier reading."""
        return self.average_speed_mbps / 8.0

    @property
    def file_size_mb(self) -> float:
        """File size in megabytes."""
        return self.file_size_bytes / (1024 * 1024)


class HfTransferDownloader:
    """HuggingFace Transfer downloader for fresh downloads."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.hf_transfer_available = self._check_hf_transfer()

    def _check_hf_transfer(self) -> bool:
        """Check if hf_transfer is available."""
        import importlib.util

        if importlib.util.find_spec("hf_transfer") is not None:
            return HF_TRANSFER_ENABLED
        else:
            self.logger.debug("hf_transfer not available")
            return False

    def download(
        self,
        url: str,
        output_path: str,
        show_progress: bool = False,
    ) -> DownloadMetrics:
        """
        Download file using hf_transfer for maximum speed.

        Args:
            url: URL to download
            output_path: Local file path to save to
            show_progress: Whether to show real-time progress

        Returns:
            DownloadMetrics with performance data
        """
        if not self.hf_transfer_available:
            raise RuntimeError("hf_transfer not available")

        start_time = time.time()

        try:
            # Set HF_HUB_ENABLE_HF_TRANSFER environment variable
            env = os.environ.copy()
            env["HF_HUB_ENABLE_HF_TRANSFER"] = "1"

            # Add authentication if HF token is available
            hf_token = os.environ.get("HF_TOKEN")
            if hf_token:
                env["HF_TOKEN"] = hf_token

            # Use hf_transfer via huggingface_hub
            from huggingface_hub import hf_hub_download

            # Extract model_id and filename from URL
            # URL format: https://huggingface.co/{model_id}/resolve/{revision}/{filename}
            if "huggingface.co" in url and "/resolve/" in url:
                parts = url.replace("https://huggingface.co/", "").split("/resolve/")
                model_id = parts[0]
                revision_and_filename = parts[1].split("/", 1)
                revision = revision_and_filename[0]
                filename = revision_and_filename[1]

                # Create output directory
                os.makedirs(os.path.dirname(output_path), exist_ok=True)

                # Download using hf_hub_download with hf_transfer enabled
                downloaded_path = hf_hub_download(
                    repo_id=model_id,
                    filename=filename,
                    revision=revision,
                    cache_dir=os.path.dirname(output_path),
                    local_dir=os.path.dirname(output_path),
                    local_dir_use_symlinks=False,
                )

                # Move to expected location if needed
                if downloaded_path != output_path:
                    import shutil

                    shutil.move(downloaded_path, output_path)

            else:
                # Fallback to direct download for non-HF URLs
                raise ValueError("hf_transfer only supports HuggingFace URLs")

            end_time = time.time()
            file_size = (
                os.path.getsize(output_path) if os.path.exists(output_path) else 0
            )
            total_time = end_time - start_time

            if total_time > 0 and file_size > 0:
                bits_per_second = (file_size * 8) / total_time
                avg_speed = bits_per_second / (1024 * 1024)
            else:
                avg_speed = 0

            self.logger.info(
                f"Downloaded {file_size / (1024 * 1024):.1f}MB in {total_time:.1f}s "
                f"({avg_speed / 8:.1f} MB/s) using hf_transfer"
            )

            return DownloadMetrics(
                method="hf_transfer",
                file_size_bytes=file_size,
                total_time_seconds=total_time,
                average_speed_mbps=avg_speed,
                success=True,
            )

        except Exception as e:
            self.logger.error(f"hf_transfer download failed: {str(e)}")
            return DownloadMetrics(
                method="hf_transfer",
                file_size_bytes=0,
                total_time_seconds=time.time() - start_time,
                average_speed_mbps=0,
                success=False,
                error_message=str(e),
            )


class DownloadAccelerator:
    """
    Main download acceleration coordinator using hf_transfer.

    Note: hf_xet acceleration is now automatically handled by HuggingFace Hub
    when using hf_hub_download() or snapshot_download() functions.
    """

    def __init__(self, workspace_manager=None):
        self.workspace_manager = workspace_manager
        self.logger = logging.getLogger(__name__)
        self.hf_transfer_downloader = HfTransferDownloader()

    def should_accelerate_download(
        self, url: str, estimated_size_mb: float = 0
    ) -> bool:
        """
        Determine if download should be accelerated.

        Args:
            url: Download URL
            estimated_size_mb: Estimated file size in MB

        Returns:
            True if download should be accelerated
        """
        # Only accelerate HuggingFace downloads with our new methods
        if "huggingface.co" not in url:
            return False

        if estimated_size_mb >= MIN_SIZE_FOR_ACCELERATION_MB:
            return True

        # For HuggingFace URLs, always try acceleration
        return True

    def is_file_cached(self, output_path: str) -> bool:
        """Check if file is already cached locally."""
        return os.path.exists(output_path) and os.path.getsize(output_path) > 0

    def download_with_fallback(
        self,
        url: str,
        output_path: str,
        estimated_size_mb: float = 0,
        show_progress: bool = False,
    ) -> FunctionResponse:
        """
        Download with HF optimization when applicable.

        Strategy:
        1. Use hf_transfer for HF URLs when available and size warrants acceleration
        2. Otherwise return failure - let HF's native download handling work

        Args:
            url: URL to download
            output_path: Local file path
            estimated_size_mb: Estimated size for acceleration decision
            show_progress: Whether to show progress

        Returns:
            FunctionResponse with download result
        """
        if not self.should_accelerate_download(url, estimated_size_mb):
            self.logger.info(
                f"Not accelerating download, letting HF handle natively: {url}"
            )
            return FunctionResponse(
                success=False,
                error="No acceleration available - defer to HF native handling",
            )

        # Strategy 1: Try hf_transfer (hf_xet is automatically used by HF Hub when available)
        if self.hf_transfer_downloader.hf_transfer_available:
            try:
                self.logger.info(f"Using hf_transfer for download: {url}")
                metrics = self.hf_transfer_downloader.download(
                    url, output_path, show_progress=show_progress
                )

                if metrics.success:
                    return FunctionResponse(
                        success=True,
                        stdout=f"Downloaded {metrics.file_size_mb:.1f}MB in {metrics.total_time_seconds:.1f}s "
                        f"({metrics.speed_mb_per_sec:.1f} MB/s) using hf_transfer",
                    )
                else:
                    self.logger.warning(
                        f"hf_transfer download failed: {metrics.error_message}"
                    )
            except Exception as e:
                self.logger.warning(f"hf_transfer download failed: {e}")

        # No acceleration available - let HF handle natively
        self.logger.info(
            f"No acceleration available for {url}, deferring to HF native handling"
        )
        return FunctionResponse(
            success=False,
            error="Acceleration not available - defer to HF native handling",
        )
