import logging
from unittest.mock import patch

from log_capture import LogCapture


class TestLogCapture:
    """Test suite for LogCapture utility class."""

    def test_init_with_default_level(self):
        """Test LogCapture initialization with default level."""
        with patch.object(logging, "getLogger") as mock_get_logger:
            mock_logger = mock_get_logger.return_value
            mock_logger.getEffectiveLevel.return_value = logging.INFO

            log_capture = LogCapture()

            assert log_capture.level == logging.INFO
            assert log_capture.log_buffer is None
            assert log_capture.handler is None

    def test_init_with_explicit_level(self):
        """Test LogCapture initialization with explicit level."""
        log_capture = LogCapture(level=logging.DEBUG)

        assert log_capture.level == logging.DEBUG
        assert log_capture.log_buffer is None
        assert log_capture.handler is None

    def test_start_capture(self):
        """Test starting log capture."""
        log_capture = LogCapture(level=logging.DEBUG)

        # Mock the root logger
        with patch.object(logging, "getLogger") as mock_get_logger:
            mock_root_logger = mock_get_logger.return_value

            log_capture.start_capture()

            # Verify handler was added to root logger
            mock_root_logger.addHandler.assert_called_once()

            # Verify internal state
            assert log_capture.log_buffer is not None
            assert log_capture.handler is not None
            assert log_capture.handler.level == logging.DEBUG

    def test_start_capture_already_capturing(self):
        """Test starting capture when already capturing does nothing."""
        log_capture = LogCapture(level=logging.DEBUG)

        with patch.object(logging, "getLogger"):
            log_capture.start_capture()
            original_buffer = log_capture.log_buffer
            original_handler = log_capture.handler

            # Start capture again
            log_capture.start_capture()

            # Should be the same objects
            assert log_capture.log_buffer is original_buffer
            assert log_capture.handler is original_handler

    def test_stop_capture(self):
        """Test stopping log capture."""
        log_capture = LogCapture(level=logging.DEBUG)

        with patch.object(logging, "getLogger") as mock_get_logger:
            mock_root_logger = mock_get_logger.return_value

            log_capture.start_capture()
            handler = log_capture.handler

            # Add some content to buffer
            log_capture.log_buffer.write("test content")

            result = log_capture.stop_capture()

            # Verify handler was removed
            mock_root_logger.removeHandler.assert_called_once_with(handler)

            # Verify cleanup
            assert log_capture.log_buffer is None
            assert log_capture.handler is None
            assert result == "test content"

    def test_stop_capture_not_capturing(self):
        """Test stopping capture when not capturing returns empty string."""
        log_capture = LogCapture()

        result = log_capture.stop_capture()

        assert result == ""

    def test_get_captured_logs(self):
        """Test getting captured logs without stopping."""
        log_capture = LogCapture(level=logging.DEBUG)

        with patch.object(logging, "getLogger"):
            log_capture.start_capture()

            # Add content to buffer
            log_capture.log_buffer.write("test logs")

            result = log_capture.get_captured_logs()

            assert result == "test logs"
            # Buffer should still exist
            assert log_capture.log_buffer is not None

    def test_get_captured_logs_not_capturing(self):
        """Test getting captured logs when not capturing."""
        log_capture = LogCapture()

        result = log_capture.get_captured_logs()

        assert result == ""

    def test_capture_context_manager(self):
        """Test context manager functionality."""
        log_capture = LogCapture(level=logging.DEBUG)

        with patch.object(logging, "getLogger"):
            with log_capture.capture_context():
                # Add content during context
                log_capture.log_buffer.write("context test")

            # After context, should be stopped and content stored
            assert log_capture.log_buffer is None
            assert log_capture.handler is None
            assert log_capture.get_context_logs() == "context test"

    def test_get_context_logs_no_context(self):
        """Test getting context logs when no context was used."""
        log_capture = LogCapture()

        result = log_capture.get_context_logs()

        assert result == ""

    def test_integration_with_actual_logging(self):
        """Test integration with actual Python logging."""
        log_capture = LogCapture(level=logging.DEBUG)

        # Create a test logger
        test_logger = logging.getLogger("test_logger")
        test_logger.setLevel(logging.DEBUG)

        log_capture.start_capture()

        # Log some messages
        test_logger.debug("Debug message")
        test_logger.info("Info message")

        captured = log_capture.stop_capture()

        # Should contain both messages with proper formatting
        assert "Debug message" in captured
        assert "Info message" in captured
        assert "DEBUG" in captured
        assert "INFO" in captured

    def test_level_filtering(self):
        """Test that log capture respects level filtering."""
        # Create LogCapture at INFO level
        log_capture = LogCapture(level=logging.INFO)

        test_logger = logging.getLogger("test_filter_logger")
        test_logger.setLevel(logging.DEBUG)

        log_capture.start_capture()

        # Log messages at different levels
        test_logger.debug("This should not appear")
        test_logger.info("This should appear")
        test_logger.warning("This should also appear")

        captured = log_capture.stop_capture()

        # Only INFO and above should be captured
        assert "This should not appear" not in captured
        assert "This should appear" in captured
        assert "This should also appear" in captured
