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
    HF_CACHE_DIR_NAME,
    WORKSPACE_LOCK_FILE,
    RUNTIMES_DIR_NAME,
    WORKSPACE_INIT_TIMEOUT,
    WORKSPACE_LOCK_POLL_INTERVAL,
)


class WorkspaceManager:
    """Manages RunPod volume workspace initialization and configuration."""

    venv_path: Optional[str]
    cache_path: Optional[str]
    hf_cache_path: Optional[str]

    def __init__(self) -> None:
        self.has_runpod_volume = os.path.exists(RUNPOD_VOLUME_PATH)
        self.endpoint_id = os.environ.get("RUNPOD_ENDPOINT_ID", "default")

        # Set up workspace paths
        if self.has_runpod_volume:
            # Endpoint-specific workspace: /runpod-volume/runtimes/{endpoint_id}
            self.workspace_path = os.path.join(
                RUNPOD_VOLUME_PATH, RUNTIMES_DIR_NAME, self.endpoint_id
            )
            self.venv_path = os.path.join(self.workspace_path, VENV_DIR_NAME)
            # Shared caches at volume root for all endpoints
            self.cache_path = os.path.join(RUNPOD_VOLUME_PATH, UV_CACHE_DIR_NAME)
            self.hf_cache_path = os.path.join(RUNPOD_VOLUME_PATH, HF_CACHE_DIR_NAME)
        else:
            # Fallback to container workspace
            self.workspace_path = DEFAULT_WORKSPACE_PATH
            self.venv_path = None
            self.cache_path = None
            self.hf_cache_path = None

        if self.has_runpod_volume:
            self._configure_uv_cache()
            self._configure_huggingface_cache()
            self._configure_volume_environment()

    def _configure_uv_cache(self):
        """Configure uv to use the shared volume cache."""
        if self.cache_path:
            os.environ["UV_CACHE_DIR"] = self.cache_path

    def _configure_huggingface_cache(self):
        """Configure Hugging Face to use the shared volume cache."""
        if self.hf_cache_path:
            # Ensure HF cache directory exists
            os.makedirs(self.hf_cache_path, exist_ok=True)

            # Set main HF cache directory
            os.environ["HF_HOME"] = self.hf_cache_path

            # Set specific cache paths for different HF components
            os.environ["TRANSFORMERS_CACHE"] = os.path.join(
                self.hf_cache_path, "transformers"
            )
            os.environ["HF_DATASETS_CACHE"] = os.path.join(
                self.hf_cache_path, "datasets"
            )
            os.environ["HUGGINGFACE_HUB_CACHE"] = os.path.join(
                self.hf_cache_path, "hub"
            )

    def _configure_volume_environment(self):
        """Configure environment variables for volume usage."""
        if self.venv_path:
            os.environ["VIRTUAL_ENV"] = self.venv_path
            venv_bin = os.path.join(self.venv_path, "bin")
            current_path = os.environ.get("PATH", "")
            os.environ["PATH"] = f"{venv_bin}:{current_path}"

    def initialize_workspace(
        self, timeout: int = WORKSPACE_INIT_TIMEOUT
    ) -> FunctionResponse:
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

        # Atomic check: workspace exists and is functional
        if self._is_workspace_functional():
            return FunctionResponse(
                success=True, stdout="Workspace already initialized"
            )

        # Validate workspace directory is accessible
        workspace_validation = self._validate_workspace_directory()
        if not workspace_validation.success:
            return workspace_validation

        # Use file-based locking for concurrent initialization
        lock_file_path = os.path.join(self.workspace_path, WORKSPACE_LOCK_FILE)

        try:
            return self._initialize_with_lock(lock_file_path, timeout)
        except Exception as e:
            return FunctionResponse(
                success=False, error=f"Failed to initialize workspace: {str(e)}"
            )

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
            # Validate venv before using it
            validation_result = self._validate_virtual_environment()
            if not validation_result.success:
                print(
                    f"Warning: Virtual environment is invalid: {validation_result.error}"
                )
                return
            import glob
            import sys

            site_packages = glob.glob(
                os.path.join(self.venv_path, "lib", "python*", "site-packages")
            )
            for site_package_path in site_packages:
                if site_package_path not in sys.path:
                    sys.path.insert(0, site_package_path)

    def _validate_virtual_environment(self) -> FunctionResponse:
        """
        Validate that the virtual environment is functional.

        Returns:
            FunctionResponse indicating if the venv is valid
        """
        if not self.venv_path or not os.path.exists(self.venv_path):
            return FunctionResponse(
                success=False, error="Virtual environment does not exist"
            )

        python_exe = os.path.join(self.venv_path, "bin", "python3")

        # Check if Python executable exists and is not a broken symlink
        if not os.path.exists(python_exe):
            return FunctionResponse(
                success=False, error=f"Python executable not found at {python_exe}"
            )

        # Check if it's a broken symlink (need to resolve the full path)
        if os.path.islink(python_exe):
            try:
                # Use os.path.realpath to resolve the full symlink chain
                resolved_path = os.path.realpath(python_exe)
                if not os.path.exists(resolved_path):
                    return FunctionResponse(
                        success=False,
                        error=f"Broken symlink at {python_exe}, underlying Python interpreter removed",
                    )
            except (OSError, ValueError) as e:
                return FunctionResponse(
                    success=False,
                    error=f"Error resolving symlink at {python_exe}: {str(e)}",
                )

        # Try to execute a simple Python command to verify functionality
        try:
            process = subprocess.Popen(
                [python_exe, "-c", "import sys; print(sys.version)"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            try:
                stdout, stderr = process.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                return FunctionResponse(
                    success=False, error="Python interpreter validation timed out"
                )

            if process.returncode != 0:
                return FunctionResponse(
                    success=False,
                    error=f"Python interpreter failed to execute: {stderr.decode()}",
                )

            return FunctionResponse(
                success=True, stdout="Virtual environment is functional"
            )
        except Exception as e:
            return FunctionResponse(
                success=False, error=f"Error validating virtual environment: {str(e)}"
            )

    def _remove_broken_virtual_environment(self):
        """Remove broken virtual environment directory."""
        if self.venv_path and os.path.exists(self.venv_path):
            import shutil

            try:
                shutil.rmtree(self.venv_path)
                print(f"Removed broken virtual environment at {self.venv_path}")
            except Exception as e:
                print(f"Error removing broken virtual environment: {str(e)}")

    def _is_workspace_functional(self) -> bool:
        """
        Atomically check if workspace exists and is functional.

        Returns:
            bool: True if workspace is ready to use
        """
        if not self.venv_path or not os.path.exists(self.venv_path):
            return False

        validation_result = self._validate_virtual_environment()
        if not validation_result.success:
            # Virtual environment exists but is broken, recreate it
            print(f"Virtual environment validation failed: {validation_result.error}")
            print("Recreating virtual environment...")
            self._remove_broken_virtual_environment()
            return False

        return True

    def _validate_workspace_directory(self) -> FunctionResponse:
        """
        Validate that workspace directory can be created and is writable.

        Returns:
            FunctionResponse: Success if directory is accessible
        """
        try:
            # Ensure workspace directory exists and is writable
            os.makedirs(self.workspace_path, exist_ok=True)

            # Test write access
            test_file = os.path.join(self.workspace_path, ".write_test")
            try:
                with open(test_file, "w") as f:
                    f.write("test")
                os.remove(test_file)
            except (OSError, IOError) as e:
                return FunctionResponse(
                    success=False, error=f"Workspace directory not writable: {str(e)}"
                )

            return FunctionResponse(success=True)

        except (OSError, IOError) as e:
            return FunctionResponse(
                success=False, error=f"Cannot create workspace directory: {str(e)}"
            )

    def _initialize_with_lock(
        self, lock_file_path: str, timeout: int
    ) -> FunctionResponse:
        """
        Initialize workspace using file locking with enhanced error handling.

        Args:
            lock_file_path: Path to the lock file
            timeout: Maximum time to wait for initialization

        Returns:
            FunctionResponse: Result of initialization
        """
        lock_fd = None

        try:
            # Open lock file with proper file descriptor management
            lock_fd = os.open(
                lock_file_path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o644
            )

            try:
                # Try to acquire exclusive lock without blocking
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

                # We have the lock, double-check workspace isn't already initialized
                if self._is_workspace_functional():
                    return FunctionResponse(
                        success=True, stdout="Workspace already initialized"
                    )

                # Initialize the workspace
                return self._create_virtual_environment()

            except (BlockingIOError, OSError):
                # Lock not available, wait for initialization by another worker
                return self._wait_for_workspace_initialization(timeout)

        finally:
            # Ensure lock file descriptor is properly closed and cleaned up
            if lock_fd is not None:
                try:
                    # Release the lock if we held it
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                except (OSError, IOError):
                    pass  # Lock may have been released already

                try:
                    os.close(lock_fd)
                except (OSError, IOError):
                    pass  # File descriptor may have been closed already

            # Clean up lock file
            self._cleanup_lock_file(lock_file_path)

    def _wait_for_workspace_initialization(self, timeout: int) -> FunctionResponse:
        """
        Wait for another worker to complete workspace initialization.

        Args:
            timeout: Maximum time to wait

        Returns:
            FunctionResponse: Result of waiting
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            if self._is_workspace_functional():
                return FunctionResponse(
                    success=True,
                    stdout="Workspace initialized by another worker",
                )
            time.sleep(WORKSPACE_LOCK_POLL_INTERVAL)

        return FunctionResponse(success=False, error="Workspace initialization timeout")

    def _cleanup_lock_file(self, lock_file_path: str) -> None:
        """
        Safely clean up lock file with comprehensive error handling.

        Args:
            lock_file_path: Path to the lock file to remove
        """
        try:
            if os.path.exists(lock_file_path):
                os.remove(lock_file_path)
        except (OSError, IOError) as e:
            # Log the error but don't fail the operation
            print(f"Warning: Could not remove lock file {lock_file_path}: {str(e)}")
        except Exception as e:
            # Catch any unexpected errors during cleanup
            print(f"Unexpected error removing lock file {lock_file_path}: {str(e)}")
