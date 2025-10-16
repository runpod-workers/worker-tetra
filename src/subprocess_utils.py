"""
Universal subprocess utilities with automatic logging integration.

This module provides a centralized way to execute subprocess operations with
consistent logging through the log streamer system. All subprocess output
is automatically captured and logged at DEBUG level for visibility.
"""

import subprocess
import logging
import inspect
from typing import List, Optional, Any

from live_serverless.remote_execution import FunctionResponse


def run_logged_subprocess(
    command: List[str],
    logger: Optional[logging.Logger] = None,
    operation_name: str = "",
    timeout: int = 300,
    capture_output: bool = True,
    text: bool = True,
    env: Optional[dict[str, str]] = None,
    suppress_output: bool = False,
    **popen_kwargs,
) -> FunctionResponse:
    """
    Execute subprocess with automatic logging of command and output.

    This function provides a standardized way to run subprocess operations
    with consistent logging integration. All command execution and output
    is logged at DEBUG level for visibility in the log streamer.

    Args:
        command: Command and arguments to execute
        logger: Logger instance (auto-detected if None)
        operation_name: Description of operation for log messages
        timeout: Timeout in seconds for subprocess execution
        capture_output: Whether to capture stdout/stderr
        text: Whether to return strings instead of bytes
        env: Environment variables to pass to subprocess
        suppress_output: If True, only log command execution, not output
        **popen_kwargs: Additional arguments passed to subprocess.Popen

    Returns:
        FunctionResponse with success status, stdout, and error details
    """
    # Auto-detect logger if not provided
    if logger is None:
        logger = _get_logger_from_context()

    # Prepare log prefix
    log_prefix = f"{operation_name}: " if operation_name else ""

    # Log the command being executed
    logger.debug(f"{log_prefix}Executing: {' '.join(command)}")

    try:
        # Set default capture settings
        if capture_output:
            popen_kwargs.setdefault("stdout", subprocess.PIPE)
            popen_kwargs.setdefault("stderr", subprocess.PIPE)
        if text:
            popen_kwargs["text"] = True
        if env:
            popen_kwargs["env"] = env

        # Execute subprocess
        process = subprocess.Popen(command, **popen_kwargs)

        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            error_msg = f"Command timed out after {timeout} seconds"
            logger.debug(f"{log_prefix}Error: {error_msg}")
            return FunctionResponse(success=False, error=error_msg)

        # Log subprocess output (unless suppressed)
        if not suppress_output:
            if stdout:
                logger.debug(f"{log_prefix}Output: {stdout.strip()}")
            if stderr:
                if process.returncode == 0:
                    logger.debug(f"{log_prefix}Warnings: {stderr.strip()}")
                else:
                    logger.debug(f"{log_prefix}Errors: {stderr.strip()}")

        # Return appropriate response based on exit code
        if process.returncode == 0:
            return FunctionResponse(success=True, stdout=stdout)
        else:
            return FunctionResponse(success=False, error=stderr)

    except Exception as e:
        error_msg = str(e)
        logger.debug(f"{log_prefix}Exception: {error_msg}")
        return FunctionResponse(success=False, error=error_msg)


def run_logged_subprocess_simple(
    command: List[str],
    logger: Optional[logging.Logger] = None,
    operation_name: str = "",
    timeout: int = 300,
    **popen_kwargs,
) -> subprocess.Popen[Any]:
    """
    Execute subprocess with logging but return the Popen object directly.

    This is useful when you need direct access to the subprocess object
    but still want consistent logging of the command execution.

    Args:
        command: Command and arguments to execute
        logger: Logger instance (auto-detected if None)
        operation_name: Description of operation for log messages
        timeout: Timeout in seconds (not enforced, just for logging)
        **popen_kwargs: Arguments passed to subprocess.Popen

    Returns:
        subprocess.Popen object
    """
    # Auto-detect logger if not provided
    if logger is None:
        logger = _get_logger_from_context()

    # Prepare log prefix
    log_prefix = f"{operation_name}: " if operation_name else ""

    # Log the command being executed
    logger.debug(f"{log_prefix}Executing: {' '.join(command)}")

    return subprocess.Popen(command, **popen_kwargs)


def _get_logger_from_context(default_name: str = "subprocess_utils") -> logging.Logger:
    """
    Auto-detect logger from calling context.

    Attempts to find a logger in the calling frame, falling back to
    a default logger if none is found.

    Args:
        default_name: Default logger name if auto-detection fails

    Returns:
        Logger instance
    """
    try:
        # Walk up the call stack to find a logger
        frame = inspect.currentframe()
        while frame:
            frame = frame.f_back
            if frame is None:
                break

            # Check if the calling frame has 'self' with a logger
            if "self" in frame.f_locals:
                obj = frame.f_locals["self"]
                if hasattr(obj, "logger") and isinstance(obj.logger, logging.Logger):
                    return obj.logger

            # Check for local logger variable
            if "logger" in frame.f_locals:
                logger = frame.f_locals["logger"]
                if isinstance(logger, logging.Logger):
                    return logger

    except Exception:
        # If auto-detection fails, fall back to default
        pass

    # Return default logger
    return logging.getLogger(default_name)
