import os
import logging
import asyncio
import platform
from typing import List

from remote_execution import FunctionResponse
from constants import LARGE_SYSTEM_PACKAGES, NAMESPACE
from subprocess_utils import run_logged_subprocess


class DependencyInstaller:
    """Handles installation of system and Python dependencies."""

    def __init__(self):
        self.logger = logging.getLogger(f"{NAMESPACE}.{__name__.split('.')[-1]}")
        self._nala_available = None  # Cache nala availability check
        self._is_docker = None  # Cache Docker environment detection

    def install_dependencies(
        self, packages: List[str], accelerate_downloads: bool = True
    ) -> FunctionResponse:
        """
        Install Python packages using uv or regular pip.
        Automatically installs build-essential if compilation is required.

        Args:
            packages: List of package names or package specifications
            accelerate_downloads: Whether to use uv for accelerated downloads
        Returns:
            FunctionResponse: Object indicating success or failure with details
        """
        if not packages:
            return FunctionResponse(success=True, stdout="No packages to install")

        self.logger.info(f"Installing Python dependencies: {packages}")

        if self._is_docker_environment():
            if accelerate_downloads:
                # Packages are installed to the system location where they can be imported
                command = ["uv", "pip", "install", "--system"] + packages
            else:
                # Use full path to system python
                command = ["pip", "install"] + packages
        else:
            # Local: Always use uv with current python for consistency
            command = ["uv", "pip", "install", "--python", "python"] + packages

        operation_name = f"Installing Python packages ({'accelerated' if accelerate_downloads else 'standard'})"

        try:
            result = run_logged_subprocess(
                command=command,
                logger=self.logger,
                operation_name=operation_name,
                timeout=300,
                env=os.environ.copy(),
            )

            # Check if installation failed due to missing compiler
            if not result.success and self._needs_compilation(result):
                self.logger.info(
                    "Package compilation required but build tools missing. "
                    "Auto-installing build-essential..."
                )

                # Install build-essential
                build_result = self.install_system_dependencies(
                    ["build-essential"], accelerate_downloads
                )

                if not build_result.success:
                    return FunctionResponse(
                        success=False,
                        error=f"Failed to install build tools: {build_result.error}",
                        stdout=result.stdout,
                    )

                # Retry package installation
                self.logger.info("Retrying package installation with build tools...")
                result = run_logged_subprocess(
                    command=command,
                    logger=self.logger,
                    operation_name=f"{operation_name} (retry with build tools)",
                    timeout=300,
                    env=os.environ.copy(),
                )

            return result

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
                result = run_logged_subprocess(
                    command=["which", "nala"],
                    logger=self.logger,
                    operation_name="Checking nala availability",
                )
                self._nala_available = result.success
            except Exception:
                # If subprocess utility fails, assume nala is not available
                self._nala_available = False

        return self._nala_available

    def _needs_compilation(self, result: FunctionResponse) -> bool:
        """
        Detect if a package installation failure was due to missing compilation tools.

        Args:
            result: FunctionResponse from failed pip installation

        Returns:
            True if the error indicates missing compiler/build tools, False otherwise
        """
        # Common error patterns indicating missing compiler
        error_indicators = [
            "gcc",
            "g++",
            "command 'cc' failed",
            "command 'c++' failed",
            "unable to execute 'gcc'",
            "unable to execute 'cc'",
            "unable to execute 'c++'",
            "error: command 'gcc' failed",
            "error: command 'cc' failed",
            "No such file or directory: 'gcc'",
            "No such file or directory: 'cc'",
            "_distutils_hack",
            "distutils.errors.CompileError",
            "distutils.errors.DistutilsExecError",
        ]

        error_text = (result.error or "") + (result.stdout or "")
        error_text_lower = error_text.lower()

        return any(
            indicator.lower() in error_text_lower for indicator in error_indicators
        )

    def _is_docker_environment(self) -> bool:
        """
        Detect if we're running in a Docker container.

        Returns:
            True if running in Docker, False otherwise
        """
        if self._is_docker is None:
            try:
                # Check for .dockerenv file (most reliable indicator)
                if os.path.exists("/.dockerenv"):
                    self._is_docker = True
                # Check if we're in a container via cgroup
                elif os.path.exists("/proc/1/cgroup"):
                    with open("/proc/1/cgroup", "r") as f:
                        content = f.read()
                        self._is_docker = "docker" in content or "containerd" in content
                else:
                    self._is_docker = False
            except Exception:
                # If detection fails, assume not Docker
                self._is_docker = False

        return self._is_docker

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
        # Update package list first with nala
        update_result = run_logged_subprocess(
            command=["nala", "update"],
            logger=self.logger,
            operation_name="Updating package list with nala",
        )

        if not update_result.success:
            self.logger.warning(
                "nala update failed, falling back to standard installation"
            )
            return self._install_system_standard(packages)

        # Install packages with nala
        install_result = run_logged_subprocess(
            command=["nala", "install", "-y"] + packages,
            logger=self.logger,
            operation_name="Installing system packages with nala",
            env={
                **os.environ,
                "DEBIAN_FRONTEND": "noninteractive",
            },
        )

        if not install_result.success:
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
                stdout=f"Installed with nala: {install_result.stdout}",
            )

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
            update_result = run_logged_subprocess(
                command=["apt-get", "update"],
                logger=self.logger,
                operation_name="Updating package list with apt-get",
            )

            if not update_result.success:
                return FunctionResponse(
                    success=False,
                    error="Error updating package list",
                    stdout=update_result.error,
                )

            # Install the packages
            install_result = run_logged_subprocess(
                command=["apt-get", "install", "-y", "--no-install-recommends"]
                + packages,
                logger=self.logger,
                operation_name="Installing system packages with apt-get",
                env={
                    **os.environ,
                    "DEBIAN_FRONTEND": "noninteractive",
                },
            )

            if not install_result.success:
                return FunctionResponse(
                    success=False,
                    error="Error installing system packages",
                    stdout=install_result.error,
                )
            else:
                self.logger.info(f"Successfully installed system packages: {packages}")
                return FunctionResponse(
                    success=True,
                    stdout=install_result.stdout,
                )
        except Exception as e:
            return FunctionResponse(success=False, error=str(e))

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
