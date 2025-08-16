"""
Download acceleration using aria2c multi-connection downloads.

This module provides accelerated download capabilities for packages and models,
improving download speeds by 2-5x through parallel connections.
"""

import os
import re
import time
import subprocess
import logging
from dataclasses import dataclass
from typing import Optional, Dict, List, Any

from remote_execution import FunctionResponse
from constants import (
    DEFAULT_DOWNLOAD_CONNECTIONS,
    MIN_SIZE_FOR_ACCELERATION_MB,
    MAX_DOWNLOAD_CONNECTIONS,
    DOWNLOAD_TIMEOUT_SECONDS,
    DOWNLOAD_PROGRESS_UPDATE_INTERVAL,
)


@dataclass
class DownloadMetrics:
    """Performance metrics for download operations."""

    method: str
    file_size_bytes: int
    total_time_seconds: float
    average_speed_mbps: float
    peak_speed_mbps: float
    connections_used: int
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


class ProgressTracker:
    """Real-time progress tracking for downloads."""

    def __init__(self, update_interval: float = DOWNLOAD_PROGRESS_UPDATE_INTERVAL):
        self.update_interval = update_interval
        self.current_bytes = 0
        self.total_bytes = 0
        self.start_time = time.time()
        self.last_update = self.start_time
        self.speeds: List[float] = []
        self.peak_speed = 0.0
        self.running = False
        self.logger = logging.getLogger(__name__)

    def start(self, total_bytes: int = 0):
        """Start progress tracking."""
        self.total_bytes = total_bytes
        self.start_time = time.time()
        self.last_update = self.start_time
        self.current_bytes = 0
        self.speeds = []
        self.peak_speed = 0
        self.running = True

    def update(self, bytes_downloaded: int):
        """Update progress with new byte count."""
        if not self.running:
            return

        self.current_bytes = bytes_downloaded
        current_time = time.time()

        if current_time - self.last_update >= self.update_interval:
            elapsed = current_time - self.start_time
            if elapsed > 0:
                current_speed = (self.current_bytes * 8) / (1024 * 1024 * elapsed)
                self.speeds.append(current_speed)

                if len(self.speeds) > 10:
                    self.speeds.pop(0)

                self.peak_speed = max(self.peak_speed, current_speed)
                self._log_progress()

            self.last_update = current_time

    def _log_progress(self):
        """Log current progress."""
        if self.total_bytes > 0:
            percent = (self.current_bytes / self.total_bytes) * 100
            mb_downloaded = self.current_bytes / (1024 * 1024)
            mb_total = self.total_bytes / (1024 * 1024)

            current_speed = self.speeds[-1] if self.speeds else 0

            self.logger.info(
                f"Download progress: {percent:.1f}% ({mb_downloaded:.1f}/{mb_total:.1f}MB) "
                f"at {current_speed:.1f}Mbps"
            )

    def stop(self):
        """Stop progress tracking."""
        self.running = False

    def get_final_metrics(self) -> Dict[str, Any]:
        """Get final performance metrics."""
        total_time = time.time() - self.start_time
        avg_speed = sum(self.speeds) / len(self.speeds) if self.speeds else 0

        return {
            "total_time": total_time,
            "average_speed_mbps": avg_speed,
            "peak_speed_mbps": self.peak_speed,
            "bytes_downloaded": self.current_bytes,
        }


class Aria2Downloader:
    """Multi-connection downloader using aria2c."""

    def __init__(
        self,
        connections: int = DEFAULT_DOWNLOAD_CONNECTIONS,
        timeout: int = DOWNLOAD_TIMEOUT_SECONDS,
    ):
        self.connections = connections
        self.timeout = timeout
        self.logger = logging.getLogger(__name__)
        self.aria2c_available = self._check_aria2c()

    def _check_aria2c(self) -> bool:
        """Check if aria2c is available."""
        try:
            result = subprocess.run(
                ["aria2c", "--version"], capture_output=True, text=True, timeout=5
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def download(
        self,
        url: str,
        output_path: str,
        connections: Optional[int] = None,
        show_progress: bool = False,
    ) -> DownloadMetrics:
        """
        Download file using aria2c with multiple connections.

        Args:
            url: URL to download
            output_path: Local file path to save to
            connections: Number of connections (defaults to instance setting)
            show_progress: Whether to show real-time progress

        Returns:
            DownloadMetrics with performance data
        """
        if not self.aria2c_available:
            raise RuntimeError(
                "aria2c not available - install with: apt-get install aria2"
            )

        connections = connections or self.connections
        connections = min(connections, MAX_DOWNLOAD_CONNECTIONS)

        # Build aria2c command
        cmd = [
            "aria2c",
            "--max-connection-per-server",
            str(connections),
            "--split",
            str(connections),
            "--min-split-size",
            "1M",
            "--summary-interval",
            "1",
            "--console-log-level",
            "warn",
            "--out",
            os.path.basename(output_path),
            "--dir",
            os.path.dirname(output_path) or ".",
            url,
        ]

        # Add authentication if HF token is available
        hf_token = os.environ.get("HF_TOKEN")
        if hf_token and "huggingface.co" in url:
            cmd.extend(["--header", f"Authorization: Bearer {hf_token}"])

        progress_tracker = None
        if show_progress:
            progress_tracker = ProgressTracker()
            progress_tracker.start()

        start_time = time.time()

        try:
            if show_progress:
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    universal_newlines=True,
                )

                output_lines = []
                while True:
                    if process.stdout is None:
                        break
                    line = process.stdout.readline()
                    if line:
                        output_lines.append(line)
                        if progress_tracker:
                            self._parse_aria2_progress(line, progress_tracker)

                    if process.poll() is not None:
                        break

                remaining_output, _ = process.communicate()
                if remaining_output:
                    output_lines.append(remaining_output)

                stdout = "".join(output_lines)
                stderr = ""
            else:
                process = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
                )
                stdout, stderr = process.communicate(timeout=self.timeout)

            end_time = time.time()

            if progress_tracker:
                progress_tracker.stop()

            if process.returncode != 0:
                raise RuntimeError(f"aria2c failed: {stderr or stdout}")

            file_size = (
                os.path.getsize(output_path) if os.path.exists(output_path) else 0
            )
            total_time = end_time - start_time

            if progress_tracker:
                metrics = progress_tracker.get_final_metrics()
                avg_speed = metrics["average_speed_mbps"]
                peak_speed = metrics["peak_speed_mbps"]
            else:
                if total_time > 0 and file_size > 0:
                    bits_per_second = (file_size * 8) / total_time
                    avg_speed = bits_per_second / (1024 * 1024)
                    peak_speed = avg_speed
                else:
                    avg_speed = peak_speed = 0

            self.logger.info(
                f"Downloaded {file_size / (1024 * 1024):.1f}MB in {total_time:.1f}s "
                f"({avg_speed / 8:.1f} MB/s) using {connections} connections"
            )

            return DownloadMetrics(
                method=f"aria2c-{connections}conn",
                file_size_bytes=file_size,
                total_time_seconds=total_time,
                average_speed_mbps=avg_speed,
                peak_speed_mbps=peak_speed,
                connections_used=connections,
                success=True,
            )

        except subprocess.TimeoutExpired:
            if progress_tracker:
                progress_tracker.stop()
            process.kill()
            raise RuntimeError(f"Download timed out after {self.timeout}s")
        except Exception as e:
            if progress_tracker:
                progress_tracker.stop()
            raise RuntimeError(f"Download failed: {str(e)}")

    def _parse_aria2_progress(self, line: str, progress_tracker: ProgressTracker):
        """Parse aria2c output line for progress information."""
        progress_match = re.search(
            r"\[#\w+\s+([\d.]+)([KMGT]?)iB/([\d.]+)([KMGT]?)iB\((\d+)%\)", line
        )
        if progress_match:
            downloaded_val = float(progress_match.group(1))
            downloaded_unit = progress_match.group(2)
            total_val = float(progress_match.group(3))
            total_unit = progress_match.group(4)

            downloaded_bytes = self._convert_to_bytes(downloaded_val, downloaded_unit)
            total_bytes = self._convert_to_bytes(total_val, total_unit)

            if progress_tracker.total_bytes == 0:
                progress_tracker.total_bytes = total_bytes

            progress_tracker.update(downloaded_bytes)

    def _convert_to_bytes(self, value: float, unit: str) -> int:
        """Convert size value with unit to bytes."""
        multipliers = {"": 1024**2, "K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}
        return int(value * multipliers.get(unit, 1024**2))


class DownloadAccelerator:
    """
    Main download acceleration coordinator.

    Decides when to use acceleration based on file size and availability.
    """

    def __init__(self, workspace_manager=None):
        self.workspace_manager = workspace_manager
        self.logger = logging.getLogger(__name__)
        self.aria2_downloader = Aria2Downloader()

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
        if not self.aria2_downloader.aria2c_available:
            return False

        if estimated_size_mb >= MIN_SIZE_FOR_ACCELERATION_MB:
            return True

        # For HuggingFace URLs, always try acceleration
        if "huggingface.co" in url:
            return True

        return False

    def download_with_fallback(
        self,
        url: str,
        output_path: str,
        estimated_size_mb: float = 0,
        show_progress: bool = False,
    ) -> FunctionResponse:
        """
        Download with acceleration if beneficial, fallback to standard if needed.

        Args:
            url: URL to download
            output_path: Local file path
            estimated_size_mb: Estimated size for acceleration decision
            show_progress: Whether to show progress

        Returns:
            FunctionResponse with download result
        """
        if self.should_accelerate_download(url, estimated_size_mb):
            try:
                self.logger.info(f"Accelerating download: {url}")

                # Calculate optimal connections based on file size
                if estimated_size_mb > 100:
                    connections = 16
                elif estimated_size_mb > 50:
                    connections = 12
                elif estimated_size_mb > 20:
                    connections = 8
                else:
                    connections = 4

                metrics = self.aria2_downloader.download(
                    url,
                    output_path,
                    connections=connections,
                    show_progress=show_progress,
                )

                return FunctionResponse(
                    success=True,
                    stdout=f"Downloaded {metrics.file_size_mb:.1f}MB in {metrics.total_time_seconds:.1f}s "
                    f"({metrics.speed_mb_per_sec:.1f} MB/s) using {metrics.connections_used} connections",
                )

            except Exception as e:
                self.logger.warning(
                    f"Accelerated download failed, falling back to standard: {e}"
                )
                return self._fallback_download(url, output_path)
        else:
            self.logger.info(f"Using standard download: {url}")
            return self._fallback_download(url, output_path)

    def _fallback_download(self, url: str, output_path: str) -> FunctionResponse:
        """Fallback to standard download methods."""
        try:
            # Use curl as fallback
            start_time = time.time()

            cmd = ["curl", "-L", "-o", output_path, url]

            # Add authentication if HF token is available
            hf_token = os.environ.get("HF_TOKEN")
            if hf_token and "huggingface.co" in url:
                cmd.extend(["-H", f"Authorization: Bearer {hf_token}"])

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=DOWNLOAD_TIMEOUT_SECONDS
            )
            end_time = time.time()

            if result.returncode != 0:
                return FunctionResponse(
                    success=False,
                    error=f"Download failed: {result.stderr}",
                    stdout=result.stdout,
                )

            file_size = (
                os.path.getsize(output_path) if os.path.exists(output_path) else 0
            )
            total_time = end_time - start_time

            self.logger.info(
                f"Downloaded {file_size / (1024 * 1024):.1f}MB in {total_time:.1f}s using standard method"
            )

            return FunctionResponse(
                success=True,
                stdout=f"Downloaded {file_size / (1024 * 1024):.1f}MB in {total_time:.1f}s",
            )

        except Exception as e:
            return FunctionResponse(
                success=False, error=f"Standard download failed: {str(e)}"
            )
