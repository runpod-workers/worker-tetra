import os
import subprocess
import importlib
import logging
import asyncio
from typing import List, Dict

from remote_execution import FunctionResponse
from download_accelerator import DownloadAccelerator
from constants import LARGE_SYSTEM_PACKAGES, NALA_CHECK_CMD


class DependencyInstaller:
    """Handles installation of system and Python dependencies."""

    def __init__(self, workspace_manager):
        self.workspace_manager = workspace_manager
        self.logger = logging.getLogger(f"worker_tetra.{__name__.split('.')[-1]}")
        self.download_accelerator = DownloadAccelerator(workspace_manager)
        self._nala_available = None  # Cache nala availability check

    def install_system_dependencies(
        self, packages: List[str], accelerate_downloads: bool = True
    ) -> FunctionResponse:
        """
        Install system packages using nala (accelerated) or apt-get (standard).

        Args:
            packages: List of system package names
            accelerate_downloads: Whether to use nala for accelerated downloads

        Returns:
            FunctionResponse: Object indicating success or failure with details
        """
        if not packages:
            return FunctionResponse(
                success=True, stdout="No system packages to install"
            )

        self.logger.info(f"Installing system dependencies: {packages}")

        # Check if we should use accelerated installation with nala
        large_packages = self._identify_large_system_packages(packages)

        if accelerate_downloads and large_packages and self._check_nala_available():
            self.logger.info(
                f"Using nala for accelerated installation of system packages: {large_packages}"
            )
            return self._install_system_with_nala(packages)
        else:
            return self._install_system_standard(packages)

    def install_dependencies(
        self, packages: List[str], accelerate_downloads: bool = True
    ) -> FunctionResponse:
        """
        Install Python packages using uv (accelerated) or pip (standard).

        Args:
            packages: List of package names or package specifications
            accelerate_downloads: Whether to use uv for accelerated downloads
        Returns:
            FunctionResponse: Object indicating success or failure with details
        """
        if not packages:
            return FunctionResponse(success=True, stdout="No packages to install")

        self.logger.info(f"Installing dependencies: {packages}")
        self.logger.debug(
            f"Dependencies installation - accelerate_downloads: {accelerate_downloads}"
        )
        self.logger.debug(
            f"Workspace manager has_runpod_volume: {self.workspace_manager.has_runpod_volume}"
        )

        # Always use UV for Python package installation (more reliable than pip)
        # When acceleration is enabled, use differential installation
        if accelerate_downloads:
            if (
                self.workspace_manager.has_runpod_volume
                and self.workspace_manager.venv_path
                and os.path.exists(self.workspace_manager.venv_path)
            ):
                # Validate virtual environment before using it
                validation_result = (
                    self.workspace_manager._validate_virtual_environment()
                )
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

        # Always use UV (works reliably with virtual environments)
        return self._install_with_uv(packages)

    def _install_with_uv(self, packages: List[str]) -> FunctionResponse:
        """
        Install packages using UV package manager

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
            command = ["uv", "pip", "install"] + packages
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

    def _check_nala_available(self) -> bool:
        """
        Check if nala is available and cache the result.

        Returns:
            True if nala is available, False otherwise
        """
        if self._nala_available is None:
            try:
                process = subprocess.Popen(
                    NALA_CHECK_CMD,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                process.communicate()
                self._nala_available = process.returncode == 0

                if self._nala_available:
                    self.logger.debug(
                        "nala is available for accelerated system package installation"
                    )
                else:
                    self.logger.debug("nala is not available, falling back to apt-get")

            except Exception:
                self._nala_available = False
                self.logger.debug(
                    "nala availability check failed, falling back to apt-get"
                )

        return self._nala_available

    def _identify_large_system_packages(self, packages: List[str]) -> List[str]:
        """
        Identify system packages that are likely to be large and benefit from acceleration.

        Args:
            packages: List of system package names

        Returns:
            List of package names that are likely large
        """
        large_packages = []
        for package in packages:
            if any(pattern in package for pattern in LARGE_SYSTEM_PACKAGES):
                large_packages.append(package)
        return large_packages

    def _install_system_with_nala(self, packages: List[str]) -> FunctionResponse:
        """
        Install system packages using nala for accelerated downloads.

        Args:
            packages: System packages to install

        Returns:
            FunctionResponse with installation result
        """
        try:
            # Update package list first with nala
            self.logger.info("Updating package list with nala")
            update_process = subprocess.Popen(
                ["nala", "update"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            update_stdout, update_stderr = update_process.communicate()

            if update_process.returncode != 0:
                self.logger.warning(
                    "nala update failed, falling back to standard installation"
                )
                return self._install_system_standard(packages)

            # Install packages with nala
            self.logger.info("Installing packages with nala acceleration")
            process = subprocess.Popen(
                ["nala", "install", "-y"] + packages,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={
                    **os.environ,
                    "DEBIAN_FRONTEND": "noninteractive",
                },
            )

            stdout, stderr = process.communicate()

            if process.returncode != 0:
                self.logger.warning(
                    "nala installation failed, falling back to standard installation"
                )
                return self._install_system_standard(packages)
            else:
                self.logger.info(
                    f"Successfully installed system packages with nala: {packages}"
                )
                return FunctionResponse(
                    success=True,
                    stdout=f"Installed with nala acceleration: {stdout.decode()}",
                )
        except Exception as e:
            self.logger.warning(
                f"nala installation failed with exception, falling back to standard: {e}"
            )
            return self._install_system_standard(packages)

    def _install_system_standard(self, packages: List[str]) -> FunctionResponse:
        """
        Install system packages using standard apt-get method.

        Args:
            packages: System packages to install

        Returns:
            FunctionResponse with installation result
        """
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

    async def install_system_dependencies_async(
        self, packages: List[str], accelerate_downloads: bool = True
    ) -> FunctionResponse:
        """
        Async wrapper for system dependency installation.

        Args:
            packages: List of system package names
            accelerate_downloads: Whether to use nala for accelerated downloads

        Returns:
            FunctionResponse: Object indicating success or failure with details
        """
        return await asyncio.to_thread(
            self.install_system_dependencies, packages, accelerate_downloads
        )

    async def install_dependencies_async(
        self, packages: List[str], accelerate_downloads: bool = True
    ) -> FunctionResponse:
        """
        Async wrapper for Python dependency installation.

        Args:
            packages: List of package names or package specifications
            accelerate_downloads: Whether to use uv for accelerated downloads

        Returns:
            FunctionResponse: Object indicating success or failure with details
        """
        return await asyncio.to_thread(
            self.install_dependencies, packages, accelerate_downloads
        )
