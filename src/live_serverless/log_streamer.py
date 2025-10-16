"""
Centralized log streaming system for capturing and streaming logs to FunctionResponse.stdout.

This module provides thread-safe log buffering and streaming capabilities to ensure
all system logs (dependency installation, workspace setup, etc.) are visible in the
remote execution response.
"""

import logging
import threading
from collections import deque
from typing import Optional, Deque, Callable

from .logger import get_log_format


class LogStreamer:
    """
    Thread-safe log streaming system that captures logs and makes them available
    for streaming to FunctionResponse.stdout.
    """

    def __init__(self, max_buffer_size: int = 1000):
        """
        Initialize the log streamer.

        Args:
            max_buffer_size: Maximum number of log entries to keep in buffer
        """
        self._buffer: Deque[str] = deque(maxlen=max_buffer_size)
        self._lock = threading.Lock()
        self._handler: Optional[StreamingHandler] = None
        self._original_level: Optional[int] = None
        self._callback: Optional[Callable[[str], None]] = None

    def start_streaming(
        self,
        level: int = logging.INFO,
        callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        """
        Start capturing logs and streaming them to buffer.

        Args:
            level: Minimum log level to capture (DEBUG, INFO, WARNING, ERROR)
            callback: Optional callback function called for each log entry
        """
        with self._lock:
            if self._handler is not None:
                return  # Already streaming

            self._callback = callback

            # Create and configure streaming handler
            self._handler = StreamingHandler(self)
            self._handler.setLevel(level)

            # Use same format as main logging
            formatter = logging.Formatter(get_log_format(level))
            self._handler.setFormatter(formatter)

            # Add to root logger
            root_logger = logging.getLogger()
            self._original_level = root_logger.level
            root_logger.addHandler(self._handler)

            # Ensure we capture logs at the requested level
            if root_logger.level > level:
                root_logger.setLevel(level)

    def stop_streaming(self) -> None:
        """Stop capturing logs and clean up handler."""
        with self._lock:
            if self._handler is None:
                return  # Not streaming

            # Remove handler from root logger
            root_logger = logging.getLogger()
            root_logger.removeHandler(self._handler)

            # Restore original log level
            if self._original_level is not None:
                root_logger.setLevel(self._original_level)

            self._handler = None
            self._original_level = None
            self._callback = None

    def add_log_entry(self, log_entry: str) -> None:
        """
        Add a log entry to the buffer.

        Args:
            log_entry: Formatted log entry to add
        """
        with self._lock:
            self._buffer.append(log_entry)

            # Call callback if provided
            if self._callback:
                try:
                    self._callback(log_entry)
                except Exception:
                    # Don't let callback errors break logging
                    pass

    def get_logs(self, clear_buffer: bool = False) -> str:
        """
        Get all buffered log entries as a single string.

        Args:
            clear_buffer: If True, clear the buffer after getting logs

        Returns:
            All log entries joined with newlines
        """
        with self._lock:
            if not self._buffer:
                return ""

            logs = "\n".join(self._buffer)

            if clear_buffer:
                self._buffer.clear()

            return logs

    def get_new_logs(self) -> str:
        """
        Get all buffered logs and clear the buffer.
        Convenience method equivalent to get_logs(clear_buffer=True).

        Returns:
            All log entries joined with newlines
        """
        return self.get_logs(clear_buffer=True)

    def has_logs(self) -> bool:
        """Check if there are any logs in the buffer."""
        with self._lock:
            return len(self._buffer) > 0


class StreamingHandler(logging.Handler):
    """
    Custom logging handler that streams log records to a LogStreamer.
    """

    def __init__(self, log_streamer: LogStreamer):
        """
        Initialize the streaming handler.

        Args:
            log_streamer: LogStreamer instance to send logs to
        """
        super().__init__()
        self.log_streamer = log_streamer

    def emit(self, record: logging.LogRecord) -> None:
        """
        Emit a log record to the log streamer.

        Args:
            record: The log record to emit
        """
        try:
            # Format the log record
            log_entry = self.format(record)

            # Add to log streamer buffer
            self.log_streamer.add_log_entry(log_entry)

        except Exception:
            # Don't let logging errors break the application
            # This follows Python logging best practices
            self.handleError(record)


# Global log streamer instance for convenience
_global_streamer: Optional[LogStreamer] = None
_streamer_lock = threading.Lock()


def get_global_log_streamer() -> LogStreamer:
    """
    Get or create the global log streamer instance.

    Returns:
        Global LogStreamer instance
    """
    global _global_streamer

    with _streamer_lock:
        if _global_streamer is None:
            _global_streamer = LogStreamer()
        return _global_streamer


def start_log_streaming(
    level: int = logging.INFO, callback: Optional[Callable[[str], None]] = None
) -> LogStreamer:
    """
    Convenience function to start log streaming with the global streamer.

    Args:
        level: Minimum log level to capture
        callback: Optional callback for each log entry

    Returns:
        The global LogStreamer instance
    """
    streamer = get_global_log_streamer()
    streamer.start_streaming(level=level, callback=callback)
    return streamer


def stop_log_streaming() -> None:
    """Convenience function to stop log streaming with the global streamer."""
    if _global_streamer is not None:
        _global_streamer.stop_streaming()


def get_streamed_logs(clear_buffer: bool = False) -> str:
    """
    Convenience function to get logs from the global streamer.

    Args:
        clear_buffer: If True, clear the buffer after getting logs

    Returns:
        All buffered log entries as a string
    """
    if _global_streamer is None:
        return ""
    return _global_streamer.get_logs(clear_buffer=clear_buffer)
