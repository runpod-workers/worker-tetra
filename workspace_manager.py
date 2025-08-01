import os
import subprocess
import fcntl
import time
from typing import Optional

from remote_execution import FunctionResponse
from constants import (
    RUNPOD_VOLUME_PATH,
    DEFAULT_WORKSPACE_PATH,
    VENV_DIR_NAME,
    UV_CACHE_DIR_NAME,
    WORKSPACE_LOCK_FILE,
)


class WorkspaceManager:
    """Manages RunPod volume workspace initialization and configuration."""

    def __init__(self):
        self.has_runpod_volume = os.path.exists(RUNPOD_VOLUME_PATH)
        self.workspace_path = (
            RUNPOD_VOLUME_PATH if self.has_runpod_volume else DEFAULT_WORKSPACE_PATH
        )
        self.venv_path = (
            os.path.join(self.workspace_path, VENV_DIR_NAME)
            if self.has_runpod_volume
            else None
        )
        self.cache_path = (
            os.path.join(self.workspace_path, UV_CACHE_DIR_NAME)
            if self.has_runpod_volume
            else None
        )

        if self.has_runpod_volume:
            self._configure_uv_cache()
            self._configure_volume_environment()

    def _configure_uv_cache(self):
        """Configure uv to use the shared volume cache."""
        if self.cache_path:
            os.environ["UV_CACHE_DIR"] = self.cache_path

    def _configure_volume_environment(self):
        """Configure environment variables for volume usage."""
        if self.venv_path:
            os.environ["VIRTUAL_ENV"] = self.venv_path
            venv_bin = os.path.join(self.venv_path, "bin")
            current_path = os.environ.get("PATH", "")
            os.environ["PATH"] = f"{venv_bin}:{current_path}"

    def initialize_workspace(self, timeout: int = 30) -> FunctionResponse:
        """
        Initialize the RunPod volume workspace with virtual environment.

        Args:
            timeout: Maximum time to wait for workspace initialization

        Returns:
            FunctionResponse: Success or failure of initialization
        """
        if not self.has_runpod_volume:
            return FunctionResponse(
                success=True, stdout="No volume available, using container workspace"
            )

        # Check if workspace is already initialized
        if self.venv_path and os.path.exists(self.venv_path):
            return FunctionResponse(
                success=True, stdout="Workspace already initialized"
            )

        # Use file-based locking for concurrent initialization
        lock_file = os.path.join(self.workspace_path, WORKSPACE_LOCK_FILE)

        try:
            # Ensure workspace directory exists
            os.makedirs(self.workspace_path, exist_ok=True)

            with open(lock_file, "w") as lock:
                try:
                    # Try to acquire exclusive lock with timeout
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except (BlockingIOError, OSError):
                    # Lock not available, wait for initialization by another worker
                    start_time = time.time()
                    while time.time() - start_time < timeout:
                        if self.venv_path and os.path.exists(self.venv_path):
                            return FunctionResponse(
                                success=True,
                                stdout="Workspace initialized by another worker",
                            )
                        time.sleep(0.5)

                    return FunctionResponse(
                        success=False, error="Workspace initialization timeout"
                    )

                # We have the lock, initialize the workspace
                return self._create_virtual_environment()

        except Exception as e:
            return FunctionResponse(
                success=False, error=f"Failed to initialize workspace: {str(e)}"
            )
        finally:
            # Clean up lock file
            try:
                if os.path.exists(lock_file):
                    os.remove(lock_file)
            except OSError:
                pass

    def _create_virtual_environment(self) -> FunctionResponse:
        """Create virtual environment in the volume."""
        if not self.venv_path:
            return FunctionResponse(
                success=False, error="Virtual environment path not configured"
            )

        try:
            process = subprocess.Popen(
                ["uv", "venv", self.venv_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            stdout, stderr = process.communicate()

            if process.returncode != 0:
                return FunctionResponse(
                    success=False,
                    error="Failed to create virtual environment",
                    stdout=stderr.decode(),
                )
            else:
                return FunctionResponse(success=True, stdout=stdout.decode())
        except Exception as e:
            return FunctionResponse(
                success=False, error=f"Exception creating virtual environment: {str(e)}"
            )

    def change_to_workspace(self) -> Optional[str]:
        """
        Change to workspace directory and return original working directory.

        Returns:
            Original working directory path if changed, None otherwise
        """
        if self.has_runpod_volume:
            original_cwd = os.getcwd()
            os.chdir(self.workspace_path)
            return original_cwd
        return None

    def setup_python_path(self):
        """Add virtual environment packages to Python path if available."""
        if self.has_runpod_volume and self.venv_path and os.path.exists(self.venv_path):
            import glob
            import sys

            site_packages = glob.glob(
                os.path.join(self.venv_path, "lib", "python*", "site-packages")
            )
            for site_package_path in site_packages:
                if site_package_path not in sys.path:
                    sys.path.insert(0, site_package_path)
