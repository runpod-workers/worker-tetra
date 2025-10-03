import os
import logging
import asyncio
import time
from pathlib import Path
from typing import Optional
from constants import NAMESPACE, CACHE_DIR, VOLUME_CACHE_PATH
from subprocess_utils import run_logged_subprocess


class CacheSyncManager:
    """Manages async fire-and-forget cache synchronization to network volume."""

    def __init__(self):
        self.logger = logging.getLogger(f"{NAMESPACE}.{__name__.split('.')[-1]}")
        self._baseline_path: Optional[str] = None
        self._last_hydrated_path: Optional[str] = None
        self._should_sync_cached: Optional[bool] = None
        self._endpoint_id = os.environ.get("RUNPOD_ENDPOINT_ID")

    def should_sync(self) -> bool:
        """
        Check if cache sync should run.

        Returns:
            True if tarball doesn't exist and volume is mounted, False otherwise
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

        timestamp = int(time.time() * 1000)
        self._baseline_path = f"/tmp/.cache-baseline-{timestamp}"

        try:
            Path(self._baseline_path).touch()
            self.logger.debug(f"Marked cache baseline at {self._baseline_path}")
        except Exception as e:
            self.logger.warning(f"Failed to mark cache baseline: {e}")
            self._baseline_path = None

    async def sync_to_volume(self) -> None:
        """Background worker to collect delta and create tarball."""
        if not self.should_sync() or not self._baseline_path:
            return

        try:
            tarball_path = f"{VOLUME_CACHE_PATH}/cache-{self._endpoint_id}.tar"
            tarball_exists = os.path.exists(tarball_path)

            self.logger.debug(
                f"Starting background cache sync from {CACHE_DIR} to {tarball_path}"
            )

            # Ensure baseline path is set
            if not self._baseline_path:
                self.logger.warning("No baseline path set, skipping cache sync")
                return

            # Find files newer than baseline (suppress verbose output logging)
            # Create a temporary logger that only logs warnings/errors
            temp_logger = logging.getLogger(f"{self.logger.name}.quiet")
            temp_logger.setLevel(logging.WARNING)

            find_result = await asyncio.to_thread(
                run_logged_subprocess,
                command=[
                    "find",
                    CACHE_DIR,
                    "-newer",
                    self._baseline_path,
                    "-type",
                    "f",
                ],
                logger=temp_logger,
                operation_name="Finding new cache files",
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

            # Write file list to temporary file (tar -r doesn't work well with stdin)
            file_list_path = (
                f"/tmp/.cache-files-{self._endpoint_id}-{int(time.time() * 1000)}"
            )
            try:
                with open(file_list_path, "w") as f:
                    f.write(new_files)
            except Exception as e:
                self.logger.warning(f"Failed to write file list: {e}")
                return

            try:
                # Choose tar operation: append to existing or create new
                if tarball_exists:
                    # Append to existing tarball
                    temp_tarball = f"{tarball_path}.tmp"
                    tar_command = ["tar", "rf", temp_tarball, "-T", file_list_path]
                    operation_name = "Appending to cache tarball"

                    # Copy existing tarball to temp location first
                    copy_result = await asyncio.to_thread(
                        run_logged_subprocess,
                        command=["cp", tarball_path, temp_tarball],
                        logger=self.logger,
                        operation_name="Copying existing tarball",
                    )

                    if not copy_result.success:
                        self.logger.warning(
                            f"Failed to copy tarball: {copy_result.error}"
                        )
                        return
                else:
                    # Create new tarball
                    temp_tarball = f"{tarball_path}.tmp"
                    tar_command = ["tar", "cf", temp_tarball, "-T", file_list_path]
                    operation_name = "Creating cache tarball"

                # Create/append tarball from file list
                tar_result = await asyncio.to_thread(
                    run_logged_subprocess,
                    command=tar_command,
                    logger=self.logger,
                    operation_name=operation_name,
                )
            finally:
                # Clean up file list
                if os.path.exists(file_list_path):
                    try:
                        os.remove(file_list_path)
                    except Exception as e:
                        self.logger.debug(f"Failed to clean up file list: {e}")

            if tar_result.success:
                # Atomically replace old tarball with new one
                rename_result = await asyncio.to_thread(
                    run_logged_subprocess,
                    command=["mv", temp_tarball, tarball_path],
                    logger=self.logger,
                    operation_name="Moving tarball to final location",
                )

                if rename_result.success:
                    action = "appended to" if tarball_exists else "created"
                    self.logger.info(
                        f"Successfully {action} cache tarball at {tarball_path}"
                    )
                else:
                    self.logger.warning(
                        f"Failed to move tarball: {rename_result.error}"
                    )
            else:
                self.logger.warning(
                    f"Failed to create cache tarball: {tar_result.error}"
                )
                # Clean up temp file on failure
                if os.path.exists(temp_tarball):
                    try:
                        os.remove(temp_tarball)
                    except Exception as e:
                        self.logger.debug(f"Failed to clean up temp tarball: {e}")

        except Exception as e:
            self.logger.error(f"Unexpected error in cache sync: {e}", exc_info=True)
        finally:
            # Clean up baseline file
            if self._baseline_path and os.path.exists(self._baseline_path):
                try:
                    os.remove(self._baseline_path)
                except Exception as e:
                    self.logger.debug(f"Failed to clean up baseline file: {e}")

    def should_hydrate(self) -> bool:
        """
        Check if cache hydration should run.

        Returns:
            True if tarball exists and is newer than last hydration, False otherwise
        """
        if not self.should_sync():
            return False

        tarball_path = f"{VOLUME_CACHE_PATH}/cache-{self._endpoint_id}.tar"
        if not os.path.exists(tarball_path):
            self.logger.debug(
                f"Tarball {tarball_path} does not exist, skipping hydration"
            )
            return False

        # Check last hydrated marker
        marker_path = f"{CACHE_DIR}/.cache-last-hydrated"
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

        self._last_hydrated_path = f"{CACHE_DIR}/.cache-last-hydrated"

        try:
            Path(self._last_hydrated_path).touch()
            self.logger.debug(
                f"Marked cache last hydrated at {self._last_hydrated_path}"
            )
        except Exception as e:
            self.logger.warning(f"Failed to mark cache last hydrated: {e}")
            self._last_hydrated_path = None

    async def hydrate_from_volume(self) -> None:
        """Extract tarball from volume to hydrate local cache."""
        if not self.should_hydrate():
            return

        try:
            tarball_path = f"{VOLUME_CACHE_PATH}/cache-{self._endpoint_id}.tar"
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
