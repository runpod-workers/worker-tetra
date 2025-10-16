import os
import logging
import asyncio
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional
from constants import NAMESPACE, CACHE_DIR, VOLUME_CACHE_PATH
from subprocess_utils import run_logged_subprocess


class CacheSyncManager:
    """Manages async fire-and-forget cache synchronization to network volume."""

    def __init__(self):
        self.logger = logging.getLogger(f"{NAMESPACE}.{__name__.split('.')[-1]}")
        self._should_sync_cached: Optional[bool] = None
        self._endpoint_id = os.environ.get("RUNPOD_ENDPOINT_ID")
        self._baseline_time: Optional[float] = None

    @property
    def _tarball_path(self) -> str:
        """Get the path to the cache tarball for this endpoint."""
        return f"{VOLUME_CACHE_PATH}/cache-{self._endpoint_id}.tar"

    @property
    def _hydration_marker_path(self) -> str:
        """Get the path to the cache hydration marker file."""
        return f"{CACHE_DIR}/.cache-last-hydrated"

    def _cleanup_temp_file(self, path: str, description: str) -> None:
        """Clean up a temporary file, logging any errors at debug level."""
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception as e:
                self.logger.debug(f"Failed to clean up {description}: {e}")

    def should_sync(self) -> bool:
        """
        Determine if cache sync functionality is available.

        Checks if all prerequisites for cache synchronization are met:
        - RUNPOD_ENDPOINT_ID is set
        - Network volume is mounted
        - Volume cache directory exists or can be created

        Result is cached after first check.

        Returns:
            True if sync functionality is available, False otherwise
        """
        if self._should_sync_cached is not None:
            return self._should_sync_cached

        # Skip if no endpoint ID
        if not self._endpoint_id:
            self.logger.debug("No RUNPOD_ENDPOINT_ID set, skipping cache sync")
            self._should_sync_cached = False
            return False

        # Skip if volume not mounted
        volume_root = os.path.dirname(VOLUME_CACHE_PATH)
        if not os.path.exists(volume_root):
            self.logger.debug(f"Volume {volume_root} not mounted, skipping cache sync")
            self._should_sync_cached = False
            return False

        # Ensure volume cache directory exists
        try:
            os.makedirs(VOLUME_CACHE_PATH, exist_ok=True)
        except Exception as e:
            self.logger.warning(
                f"Failed to create volume cache directory {VOLUME_CACHE_PATH}: {e}"
            )
            self._should_sync_cached = False
            return False

        self._should_sync_cached = True
        return True

    def mark_baseline(self) -> None:
        """Mark baseline timestamp before installation."""
        if not self.should_sync():
            return

        try:
            tarball_path = self._tarball_path
            if os.path.exists(tarball_path):
                # Subsequent run: use tarball mtime as baseline
                self._baseline_time = os.path.getmtime(tarball_path)
                baseline_source = "tarball"
            else:
                # First run: use current time as baseline
                self._baseline_time = datetime.now().timestamp()
                baseline_source = "current time"

            self.logger.debug(
                f"Baseline ({baseline_source}): {datetime.fromtimestamp(self._baseline_time).strftime('%Y-%m-%d %H:%M:%S')}"
            )
        except Exception as e:
            self.logger.warning(f"Failed to mark cache baseline: {e}")
            self._baseline_time = None

    async def sync_to_volume(self) -> None:
        """Background worker to collect delta and create tarball."""
        if not self.should_sync() or not self._baseline_time:
            return

        try:
            baseline_time = self._baseline_time
            tarball_path = self._tarball_path
            tarball_exists = os.path.exists(tarball_path)

            self.logger.debug(
                f"Sync cache to persist from {CACHE_DIR} to {tarball_path}"
            )

            # Format timestamp for find -newermt
            baseline_str = datetime.fromtimestamp(baseline_time).strftime(
                "%Y-%m-%d %H:%M:%S"
            )

            # Find files newer than baseline
            find_result = await asyncio.to_thread(
                run_logged_subprocess,
                command=[
                    "find",
                    CACHE_DIR,
                    "-newermt",
                    baseline_str,
                    "-type",
                    "f",
                    "-not",
                    "-path",
                    "*/refs/*",
                    "-not",
                    "-path",
                    "*/.no_exist/*",
                    "-not",
                    "-name",
                    ".cache-last-hydrated",
                ],
                logger=self.logger,
                operation_name="Finding new cache files",
                suppress_output=True,
            )

            if not find_result.success:
                self.logger.warning(f"Failed to find cache delta: {find_result.error}")
                return

            # Check if there are any new files
            new_files = (find_result.stdout or "").strip()
            if not new_files:
                self.logger.debug("No new cache files to sync")
                return

            # Log summary instead of full file list
            file_count = len(new_files.split("\n"))
            self.logger.debug(f"Found {file_count} new cache files to sync")

            # Monitor tarball size if it exists
            if tarball_exists:
                try:
                    tarball_size = os.path.getsize(tarball_path)
                    tarball_mb = tarball_size / (1024 * 1024)
                    self.logger.debug(f"Current tarball size: {tarball_mb:.1f}MB")

                    # Check volume capacity and warn if tarball exceeds 50%
                    volume_root = os.path.dirname(VOLUME_CACHE_PATH)
                    stat = os.statvfs(volume_root)
                    volume_total = stat.f_blocks * stat.f_frsize
                    threshold = volume_total * 0.75

                    if tarball_size > threshold:
                        volume_total_gb = volume_total / (1024**3)
                        self.logger.warning(
                            f"Tarball size ({tarball_mb:.1f}MB) exceeds 75% of volume capacity ({volume_total_gb:.1f}GB)"
                        )
                except OSError as e:
                    self.logger.debug(f"Failed to check tarball size: {e}")

            # Write file list to temporary file
            file_list_fd = tempfile.NamedTemporaryFile(
                prefix=".cache-files-", dir="/tmp", delete=False, mode="w"
            )
            file_list_path = file_list_fd.name
            try:
                file_list_fd.write(new_files)
                file_list_fd.close()
            except Exception as e:
                self.logger.warning(f"Failed to write file list: {e}")
                file_list_fd.close()
                return

            # Always create tarball of new files first
            new_tarball = f"{tarball_path}.new"
            temp_tarball = f"{tarball_path}.tmp"

            try:
                # Create tarball containing only new files
                create_result = await asyncio.to_thread(
                    run_logged_subprocess,
                    command=["tar", "cf", new_tarball, "-T", file_list_path],
                    logger=self.logger,
                    operation_name="Creating tarball of new files",
                )

                if not create_result.success:
                    self.logger.warning(
                        f"Failed to create new files tarball: {create_result.error}"
                    )
                    return

                if tarball_exists:
                    # Move existing tarball to temp location
                    move_to_temp_result = await asyncio.to_thread(
                        run_logged_subprocess,
                        command=["mv", tarball_path, temp_tarball],
                        logger=self.logger,
                        operation_name="Moving existing tarball to temp",
                    )

                    if not move_to_temp_result.success:
                        self.logger.warning(
                            f"Failed to move tarball to temp: {move_to_temp_result.error}"
                        )
                        return

                    # Concatenate new tarball into temp (faster than append)
                    concat_result = await asyncio.to_thread(
                        run_logged_subprocess,
                        command=["tar", "-A", "-f", temp_tarball, new_tarball],
                        logger=self.logger,
                        operation_name="Concatenating new files to tarball",
                    )

                    if not concat_result.success:
                        self.logger.warning(
                            f"Failed to concatenate tarball: {concat_result.error}"
                        )
                        return

                    # Atomically move temp to final location
                    rename_result = await asyncio.to_thread(
                        run_logged_subprocess,
                        command=["mv", temp_tarball, tarball_path],
                        logger=self.logger,
                        operation_name="Moving tarball to final location",
                    )

                    if rename_result.success:
                        self.logger.info(
                            f"Successfully concatenated cache tarball at {tarball_path}"
                        )
                        self.mark_last_hydrated()
                    else:
                        self.logger.warning(
                            f"Failed to move tarball: {rename_result.error}"
                        )
                else:
                    # No existing tarball, just move new one to final location
                    rename_result = await asyncio.to_thread(
                        run_logged_subprocess,
                        command=["mv", new_tarball, tarball_path],
                        logger=self.logger,
                        operation_name="Moving tarball to final location",
                    )

                    if rename_result.success:
                        self.logger.info(
                            f"Successfully created cache tarball at {tarball_path}"
                        )
                        self.mark_last_hydrated()
                    else:
                        self.logger.warning(
                            f"Failed to move tarball: {rename_result.error}"
                        )
            finally:
                # Clean up temporary files
                self._cleanup_temp_file(file_list_path, "file list")
                self._cleanup_temp_file(new_tarball, "new files tarball")
                self._cleanup_temp_file(temp_tarball, "temp tarball")

        except Exception as e:
            self.logger.error(f"Unexpected error in cache sync: {e}", exc_info=True)

    def should_hydrate(self) -> bool:
        """
        Check if cache hydration should run.

        Returns:
            True if tarball exists and is newer than last hydration, False otherwise
        """
        if not self.should_sync():
            return False

        tarball_path = self._tarball_path
        if not os.path.exists(tarball_path):
            self.logger.debug(
                f"Tarball {tarball_path} does not exist, skipping hydration"
            )
            return False

        # Check last hydrated marker
        marker_path = self._hydration_marker_path
        if not os.path.exists(marker_path):
            self.logger.debug("No hydration marker found, hydration needed")
            return True

        try:
            tarball_mtime = os.path.getmtime(tarball_path)
            marker_mtime = os.path.getmtime(marker_path)

            if tarball_mtime > marker_mtime:
                self.logger.debug(
                    "Tarball is newer than last hydration, hydration needed"
                )
                return True
            else:
                self.logger.debug(
                    "Tarball is older than last hydration, skipping hydration"
                )
                return False
        except Exception as e:
            self.logger.warning(f"Failed to check hydration status: {e}")
            return True

    def mark_last_hydrated(self) -> None:
        """Mark timestamp of last hydration."""
        if not self.should_sync():
            return

        try:
            Path(self._hydration_marker_path).touch()
            self.logger.debug(
                f"Marked cache last hydrated at {self._hydration_marker_path}"
            )
        except Exception as e:
            self.logger.warning(f"Failed to mark cache last hydrated: {e}")

    async def hydrate_from_volume(self) -> None:
        """Extract tarball from volume to hydrate local cache."""
        if not self.should_hydrate():
            return

        try:
            tarball_path = self._tarball_path
            self.logger.debug(f"Hydrating cache from {tarball_path} to {CACHE_DIR}")

            # Ensure cache directory exists
            try:
                os.makedirs(CACHE_DIR, exist_ok=True)
            except Exception as e:
                self.logger.warning(
                    f"Failed to create cache directory {CACHE_DIR}: {e}"
                )
                return

            # Extract tarball to cache directory
            tar_result = await asyncio.to_thread(
                run_logged_subprocess,
                command=["tar", "xf", tarball_path, "-C", "/"],
                logger=self.logger,
                operation_name="Extracting cache tarball",
            )

            if tar_result.success:
                self.logger.info(f"Successfully hydrated cache from {tarball_path}")
                self.mark_last_hydrated()
            else:
                self.logger.warning(f"Failed to extract tarball: {tar_result.error}")

        except Exception as e:
            self.logger.error(f"Unexpected error during hydration: {e}", exc_info=True)
