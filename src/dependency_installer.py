import os
import subprocess
import importlib
import logging
from typing import List, Dict

from remote_execution import FunctionResponse
from download_accelerator import DownloadAccelerator


class DependencyInstaller:
    """Handles installation of system and Python dependencies."""

    def __init__(self, workspace_manager):
        self.workspace_manager = workspace_manager
        self.logger = logging.getLogger(__name__)
        self.download_accelerator = DownloadAccelerator(workspace_manager)

    def install_system_dependencies(self, packages: List[str]) -> FunctionResponse:
        """
        Install system packages using apt-get.
        """
        if not packages:
            return FunctionResponse(
                success=True, stdout="No system packages to install"
            )

        self.logger.info(f"Installing system dependencies: {packages}")

        try:
            # Update package list first
            update_process = subprocess.Popen(
                ["apt-get", "update"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            update_stdout, update_stderr = update_process.communicate()

            if update_process.returncode != 0:
                return FunctionResponse(
                    success=False,
                    error="Error updating package list",
                    stdout=update_stderr.decode(),
                )

            # Install the packages
            process = subprocess.Popen(
                ["apt-get", "install", "-y", "--no-install-recommends"] + packages,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={
                    **os.environ,
                    "DEBIAN_FRONTEND": "noninteractive",
                },
            )

            stdout, stderr = process.communicate()

            if process.returncode != 0:
                return FunctionResponse(
                    success=False,
                    error="Error installing system packages",
                    stdout=stderr.decode(),
                )
            else:
                self.logger.info(f"Successfully installed system packages: {packages}")
                return FunctionResponse(
                    success=True,
                    stdout=stdout.decode(),
                )
        except Exception as e:
            return FunctionResponse(
                success=False,
                error=f"Exception during system package installation: {e}",
            )

    def install_dependencies(
        self, packages: List[str], accelerate_downloads: bool = True
    ) -> FunctionResponse:
        """
        Install Python packages using uv with differential installation support.
        Uses accelerated downloads for large packages when beneficial.

        Args:
            packages: List of package names or package specifications
            accelerate_downloads: Whether to use accelerated downloads for large packages
        Returns:
            FunctionResponse: Object indicating success or failure with details
        """
        if not packages:
            return FunctionResponse(success=True, stdout="No packages to install")

        self.logger.info(f"Installing dependencies: {packages}")

        # If using volume, check which packages are already installed
        if (
            self.workspace_manager.has_runpod_volume
            and self.workspace_manager.venv_path
            and os.path.exists(self.workspace_manager.venv_path)
        ):
            # Validate virtual environment before using it
            validation_result = self.workspace_manager._validate_virtual_environment()
            if not validation_result.success:
                self.logger.warning(
                    f"Virtual environment is invalid: {validation_result.error}"
                )
                self.logger.info("Reinitializing workspace...")
                init_result = self.workspace_manager.initialize_workspace()
                if not init_result.success:
                    return FunctionResponse(
                        success=False,
                        error=f"Failed to reinitialize workspace: {init_result.error}",
                    )
            installed_packages = self._get_installed_packages()
            packages_to_install = self._filter_packages_to_install(
                packages, installed_packages
            )

            if not packages_to_install:
                return FunctionResponse(
                    success=True, stdout="All packages already installed"
                )

            packages = packages_to_install

        # Check if we should use accelerated downloads for large packages
        large_packages = self._identify_large_packages(packages)

        if (
            accelerate_downloads
            and large_packages
            and self.download_accelerator.aria2_downloader.aria2c_available
        ):
            self.logger.info(
                f"Using accelerated downloads for large packages: {large_packages}"
            )
            return self._install_with_acceleration(packages, large_packages)
        else:
            return self._install_standard(packages)

    def _identify_large_packages(self, packages: List[str]) -> List[str]:
        """
        Identify packages that are likely to be large and benefit from acceleration.

        Args:
            packages: List of package specifications

        Returns:
            List of package names that are likely large
        """
        # Known large packages that benefit from acceleration
        large_package_patterns = [
            "torch",
            "pytorch",
            "tensorflow",
            "tf-nightly",
            "transformers",
            "diffusers",
            "datasets",
            "numpy",
            "scipy",
            "pandas",
            "matplotlib",
            "opencv",
            "cv2",
            "pillow",
            "scikit-learn",
            "huggingface-hub",
            "safetensors",
        ]

        large_packages = []
        for package in packages:
            package_name = package.split("==")[0].split(">=")[0].split("<=")[0].lower()
            if any(pattern in package_name for pattern in large_package_patterns):
                large_packages.append(package)

        return large_packages

    def _install_with_acceleration(
        self, packages: List[str], large_packages: List[str]
    ) -> FunctionResponse:
        """
        Install packages with acceleration for large ones.

        Args:
            packages: All packages to install
            large_packages: Packages that should use acceleration

        Returns:
            FunctionResponse with installation result
        """
        try:
            # Prepare environment for virtual environment usage
            env = os.environ.copy()
            if (
                self.workspace_manager.has_runpod_volume
                and self.workspace_manager.venv_path
            ):
                env["VIRTUAL_ENV"] = self.workspace_manager.venv_path

            # For now, we'll enhance UV's download behavior by setting optimal configurations
            # UV internally uses efficient downloaders, but we can optimize the environment

            # Set aria2c as a potential downloader for UV if it supports it
            env["UV_CONCURRENT_DOWNLOADS"] = "8"  # Increase concurrent downloads

            self.logger.info("Installing with optimized concurrent downloads")

            # Use uv pip to install the packages with optimizations
            command = ["uv", "pip", "install", "--no-cache-dir"] + packages
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )

            stdout, stderr = process.communicate()
            importlib.invalidate_caches()

            if process.returncode != 0:
                return FunctionResponse(
                    success=False,
                    error="Error installing packages with acceleration",
                    stdout=stderr.decode(),
                )
            else:
                self.logger.info(
                    f"Successfully installed packages with acceleration: {packages}"
                )
                return FunctionResponse(
                    success=True,
                    stdout=f"Installed with acceleration: {stdout.decode()}",
                )
        except Exception as e:
            self.logger.warning(
                f"Accelerated installation failed, falling back to standard: {e}"
            )
            return self._install_standard(packages)

    def _install_standard(self, packages: List[str]) -> FunctionResponse:
        """
        Install packages using standard UV method.

        Args:
            packages: Packages to install

        Returns:
            FunctionResponse with installation result
        """
        try:
            # Prepare environment for virtual environment usage
            env = os.environ.copy()
            if (
                self.workspace_manager.has_runpod_volume
                and self.workspace_manager.venv_path
            ):
                env["VIRTUAL_ENV"] = self.workspace_manager.venv_path

            # Use uv pip to install the packages
            command = ["uv", "pip", "install", "--no-cache-dir"] + packages
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )

            stdout, stderr = process.communicate()
            importlib.invalidate_caches()

            if process.returncode != 0:
                return FunctionResponse(
                    success=False,
                    error="Error installing packages",
                    stdout=stderr.decode(),
                )
            else:
                self.logger.info(f"Successfully installed packages: {packages}")
                return FunctionResponse(
                    success=True,
                    stdout=stdout.decode(),
                )
        except Exception as e:
            return FunctionResponse(
                success=False,
                error=f"Exception during package installation: {e}",
            )

    def _get_installed_packages(self) -> Dict[str, str]:
        """Get list of currently installed packages in the virtual environment."""
        if (
            not self.workspace_manager.has_runpod_volume
            or not self.workspace_manager.venv_path
            or not os.path.exists(self.workspace_manager.venv_path)
        ):
            return {}

        try:
            env = os.environ.copy()
            env["VIRTUAL_ENV"] = self.workspace_manager.venv_path

            process = subprocess.Popen(
                ["uv", "pip", "list", "--format=freeze"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )

            stdout, stderr = process.communicate()

            if process.returncode != 0:
                return {}

            packages = {}
            for line in stdout.decode().strip().split("\n"):
                if "==" in line:
                    name, version = line.split("==", 1)
                    packages[name] = version

            return packages
        except Exception:
            return {}

    def _filter_packages_to_install(
        self, packages: List[str], installed_packages: Dict[str, str]
    ) -> List[str]:
        """Filter packages to only include those that need installation."""
        packages_to_install = []

        for package in packages:
            # Parse package specification (e.g., "numpy==1.21.0" -> "numpy", "1.21.0")
            if "==" in package:
                name, version = package.split("==", 1)
                if (
                    name not in installed_packages
                    or installed_packages[name] != version
                ):
                    packages_to_install.append(package)
            else:
                # For packages without version specification, always install
                packages_to_install.append(package)

        return packages_to_install
