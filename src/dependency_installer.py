import os
import subprocess
import logging
import asyncio
import platform
from typing import List

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

    def install_dependencies(
        self, packages: List[str], accelerate_downloads: bool = True
    ) -> FunctionResponse:
        """
        Install Python packages using uv or regular pip

        Args:
            packages: List of package names or package specifications
            accelerate_downloads: Whether to use uv for accelerated downloads
        Returns:
            FunctionResponse: Object indicating success or failure with details
        """
        if not packages:
            return FunctionResponse(success=True, stdout="No packages to install")

        self.logger.info(f"Installing Python dependencies: {packages}")

        try:
            if accelerate_downloads:
                command = ["uv", "pip", "install", "--system"] + packages
            else:
                command = ["pip", "install"] + packages

            self.logger.debug(command)

            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            try:
                stdout, stderr = process.communicate(timeout=300)
            except subprocess.TimeoutExpired:
                process.kill()
                return FunctionResponse(
                    success=False,
                    error="Package installation timed out after 300 seconds",
                )

            if process.returncode != 0:
                return FunctionResponse(success=False, error=stderr)
            else:
                return FunctionResponse(success=True, stdout=stdout)
        except Exception as e:
            return FunctionResponse(success=False, error=str(e))

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
        # Check if we're running on a system without nala/apt-get (e.g., macOS for local testing)
        if platform.system().lower() == "darwin":
            self.logger.warning(
                "System package installation not supported on macOS (local testing environment)"
            )
            return FunctionResponse(
                success=True,  # Don't fail tests, just skip system packages
                stdout=f"Skipped system packages on macOS: {packages}",
            )

        if not packages:
            return FunctionResponse(
                success=True, stdout="No system packages to install"
            )

        self.logger.info(f"Installing System dependencies: {packages}")

        # Check if we should use accelerated installation with nala
        large_packages = self._identify_large_system_packages(packages)

        if accelerate_downloads and large_packages and self._check_nala_available():
            return self._install_system_with_nala(packages)
        else:
            return self._install_system_standard(packages)

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

            except Exception:
                self._nala_available = False

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
                    stdout=f"Installed with nala: {stdout.decode()}",
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
