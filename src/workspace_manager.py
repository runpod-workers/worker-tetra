import os
import subprocess
import fcntl
import time
import logging
from typing import Optional, TYPE_CHECKING, Any, Dict

if TYPE_CHECKING:
    from huggingface_accelerator import HuggingFaceAccelerator

from remote_execution import FunctionResponse
from constants import (
    RUNPOD_VOLUME_PATH,
    DEFAULT_WORKSPACE_PATH,
    VENV_DIR_NAME,
    UV_CACHE_DIR_NAME,
    HF_CACHE_DIR_NAME,
    WORKSPACE_LOCK_FILE,
    RUNTIMES_DIR_NAME,
)


class WorkspaceManager:
    """Manages RunPod volume workspace initialization and configuration."""

    venv_path: Optional[str]
    cache_path: Optional[str]
    hf_cache_path: Optional[str]

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)
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

        # Initialize HuggingFace accelerator after paths are set
        self._hf_accelerator: Optional[HuggingFaceAccelerator] = None

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

            # Additional environment variables that may help with subprocess execution
            venv_lib_python = os.path.join(
                self.venv_path, "lib", "python*", "site-packages"
            )
            import glob

            site_packages_dirs = glob.glob(venv_lib_python)
            if site_packages_dirs:
                # Set PYTHONPATH to include volume site-packages
                current_pythonpath = os.environ.get("PYTHONPATH", "")
                new_pythonpath = ":".join(site_packages_dirs)
                if current_pythonpath:
                    os.environ["PYTHONPATH"] = f"{new_pythonpath}:{current_pythonpath}"
                else:
                    os.environ["PYTHONPATH"] = new_pythonpath
                self.logger.info(
                    f"Set PYTHONPATH to include volume packages: {new_pythonpath}"
                )

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

        # Check if workspace is already initialized and functional
        if self.venv_path and os.path.exists(self.venv_path):
            validation_result = self._validate_virtual_environment()
            if validation_result.success:
                return FunctionResponse(
                    success=True, stdout="Workspace already initialized"
                )
            else:
                # Virtual environment exists but is broken, recreate it
                self.logger.warning(
                    f"Virtual environment validation failed: {validation_result.error}"
                )
                self.logger.info("Recreating virtual environment...")
                self._remove_broken_virtual_environment()

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
                            validation_result = self._validate_virtual_environment()
                            if validation_result.success:
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
                # Create symlink from /app/.venv to volume venv for libraries that hardcode /app/.venv
                self._create_app_venv_symlink()
                return FunctionResponse(success=True, stdout=stdout.decode())
        except Exception as e:
            return FunctionResponse(
                success=False, error=f"Exception creating virtual environment: {str(e)}"
            )

    def _create_app_venv_symlink(self):
        """
        Create symlink from /app/.venv to volume virtual environment.

        This ensures libraries that hardcode /app/.venv (like vLLM) use the volume's venv
        instead of the container's default venv.
        """
        if not self.venv_path:
            return

        app_venv_path = "/app/.venv"

        try:
            # Remove existing /app/.venv if it exists (file, dir, or broken symlink)
            if os.path.exists(app_venv_path) or os.path.islink(app_venv_path):
                if os.path.isdir(app_venv_path) and not os.path.islink(app_venv_path):
                    # It's a real directory, remove recursively
                    import shutil

                    shutil.rmtree(app_venv_path)
                else:
                    # It's a file or symlink, remove it
                    os.remove(app_venv_path)

            # Create symlink to volume venv
            os.symlink(self.venv_path, app_venv_path)
            self.logger.info(f"Created symlink: {app_venv_path} -> {self.venv_path}")

        except Exception as e:
            # Log error but don't fail workspace initialization
            self.logger.warning(f"Failed to create /app/.venv symlink: {str(e)}")

    def _remove_app_venv_symlink(self):
        """
        Remove /app/.venv symlink if it points to our virtual environment.
        """
        app_venv_path = "/app/.venv"

        try:
            if os.path.islink(app_venv_path):
                # Check if it points to our venv
                link_target = os.readlink(app_venv_path)
                if link_target == self.venv_path:
                    os.remove(app_venv_path)
                    self.logger.info(f"Removed symlink: {app_venv_path}")
        except Exception as e:
            self.logger.warning(f"Failed to remove /app/.venv symlink: {str(e)}")

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
                self.logger.warning(
                    f"Virtual environment is invalid: {validation_result.error}"
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
        """Remove broken virtual environment directory and associated symlink."""
        if self.venv_path and os.path.exists(self.venv_path):
            import shutil

            try:
                shutil.rmtree(self.venv_path)
                self.logger.info(
                    f"Removed broken virtual environment at {self.venv_path}"
                )

                # Also remove the /app/.venv symlink if it points to this venv
                self._remove_app_venv_symlink()

            except Exception as e:
                self.logger.error(
                    f"Error removing broken virtual environment: {str(e)}"
                )

    @property
    def hf_accelerator(self) -> "HuggingFaceAccelerator":
        """Lazy-loaded HuggingFace accelerator."""
        if self._hf_accelerator is None:
            from huggingface_accelerator import HuggingFaceAccelerator

            self._hf_accelerator = HuggingFaceAccelerator(self)
        return self._hf_accelerator

    def accelerate_model_download(
        self, model_id: str, revision: str = "main"
    ) -> FunctionResponse:
        """
        Pre-download HuggingFace model using acceleration if beneficial.

        Args:
            model_id: HuggingFace model identifier
            revision: Model revision/branch

        Returns:
            FunctionResponse with download result
        """
        return self.hf_accelerator.accelerate_model_download(model_id, revision)

    def is_model_cached(self, model_id: str, revision: str = "main") -> bool:
        """
        Check if a HuggingFace model is cached.

        Args:
            model_id: HuggingFace model identifier
            revision: Model revision/branch

        Returns:
            True if model is cached
        """
        return self.hf_accelerator.is_model_cached(model_id, revision)

    def get_model_cache_info(self, model_id: str) -> Dict[str, Any]:
        """
        Get cache information for a HuggingFace model.

        Args:
            model_id: HuggingFace model identifier

        Returns:
            Dictionary with cache information
        """
        return self.hf_accelerator.get_cache_info(model_id)
