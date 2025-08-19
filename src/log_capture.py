import io
import logging
from typing import Optional
from contextlib import contextmanager


class LogCapture:
    """
    Utility class to capture all logging output during request processing.
    Provides global log capture for orchestration-level operations.
    """

    def __init__(self, level: Optional[int] = None):
        # If no level specified, inherit from root logger's effective level
        # This respects the LOG_LEVEL environment variable set in handler.py
        root_logger = logging.getLogger()
        self.level = level if level is not None else root_logger.getEffectiveLevel()
        self.log_buffer: Optional[io.StringIO] = None
        self.handler: Optional[logging.StreamHandler[io.StringIO]] = None

    def start_capture(self) -> None:
        """Start capturing all log output to internal buffer."""
        if self.log_buffer is not None:
            return  # Already capturing

        self.log_buffer = io.StringIO()
        self.handler = logging.StreamHandler(self.log_buffer)
        self.handler.setLevel(self.level)

        # Use the same format as the main handler for consistency
        formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
        )
        self.handler.setFormatter(formatter)

        # Add to root logger to capture all logs
        root_logger = logging.getLogger()
        root_logger.addHandler(self.handler)

    def stop_capture(self) -> str:
        """Stop capturing and return all captured log output."""
        if self.log_buffer is None or self.handler is None:
            return ""

        # Remove handler from root logger
        root_logger = logging.getLogger()
        root_logger.removeHandler(self.handler)

        # Get captured content
        captured_content = self.log_buffer.getvalue()

        # Clean up
        self.log_buffer.close()
        self.log_buffer = None
        self.handler = None

        return captured_content

    def get_captured_logs(self) -> str:
        """Get currently captured logs without stopping capture."""
        if self.log_buffer is None:
            return ""
        return self.log_buffer.getvalue()

    @contextmanager
    def capture_context(self):
        """Context manager for automatic log capture."""
        self.start_capture()
        try:
            yield self
        finally:
            captured = self.stop_capture()
            # Store the captured content for retrieval
            self._captured_content = captured

    def get_context_logs(self) -> str:
        """Get logs captured from context manager."""
        return getattr(self, "_captured_content", "")
