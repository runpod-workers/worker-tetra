import logging
import os
from unittest.mock import patch

import pytest

from remote_execution import FunctionRequest, FunctionResponse
from remote_executor import RemoteExecutor


class TestLogCaptureIntegration:
    """Integration tests for log capture functionality with RemoteExecutor."""

    @pytest.fixture
    def function_request(self):
        """Create a basic function request for testing."""
        return FunctionRequest(
            function_name="test_logging",
            function_code="""
def test_logging():
    import logging
    logger = logging.getLogger(__name__)
    logger.debug("DEBUG: This is a debug message")
    logger.info("INFO: This is an info message") 
    logger.warning("WARNING: This is a warning message")
    print("Standard print output")
    return "Test completed"
""",
            args=[],
            kwargs={},
        )

    @pytest.fixture
    def function_request_with_dependencies(self):
        """Create a function request with dependencies to test orchestration logging."""
        return FunctionRequest(
            function_name="test_with_deps",
            function_code="""
def test_with_deps():
    import logging
    logger = logging.getLogger(__name__)
    logger.info("Function executed successfully")
    return "Dependencies test completed"
""",
            args=[],
            kwargs={},
            dependencies=["requests"],  # Small package for testing
        )

    @pytest.mark.asyncio
    async def test_log_capture_integration_debug_level(self, function_request):
        """Test that DEBUG level logs are captured when LOG_LEVEL=DEBUG."""
        # Mock environment to force DEBUG level
        with patch.dict(os.environ, {"LOG_LEVEL": "DEBUG"}):
            # Re-configure logging to pick up environment variable
            log_level_mapping = {
                "DEBUG": logging.DEBUG,
                "INFO": logging.INFO,
                "WARNING": logging.WARNING,
                "ERROR": logging.ERROR,
                "CRITICAL": logging.CRITICAL,
            }
            log_level = os.getenv("LOG_LEVEL", "DEBUG").upper()
            numeric_level = log_level_mapping.get(log_level, logging.DEBUG)

            # Configure root logger for test
            logging.getLogger().setLevel(numeric_level)

            executor = RemoteExecutor()
            response = await executor.ExecuteFunction(function_request)

            assert response.success is True
            assert response.stdout is not None

            # Should contain DEBUG logs from both orchestration and function
            assert "DEBUG" in response.stdout
            assert "DEBUG: This is a debug message" in response.stdout
            assert "LogCapture initialized with level" in response.stdout
            assert "Starting remote function execution" in response.stdout

            # Should also contain other log levels
            assert "INFO: This is an info message" in response.stdout
            assert "WARNING: This is a warning message" in response.stdout

            # Should contain print output
            assert "Standard print output" in response.stdout

    @pytest.mark.asyncio
    async def test_log_capture_integration_info_level(self, function_request):
        """Test that only INFO and above are captured when LOG_LEVEL=INFO."""
        # Mock environment to force INFO level
        with patch.dict(os.environ, {"LOG_LEVEL": "INFO"}):
            # Re-configure logging
            log_level_mapping = {
                "DEBUG": logging.DEBUG,
                "INFO": logging.INFO,
                "WARNING": logging.WARNING,
                "ERROR": logging.ERROR,
                "CRITICAL": logging.CRITICAL,
            }
            log_level = os.getenv("LOG_LEVEL", "INFO").upper()
            numeric_level = log_level_mapping.get(log_level, logging.INFO)

            # Configure root logger for test
            logging.getLogger().setLevel(numeric_level)

            executor = RemoteExecutor()
            response = await executor.ExecuteFunction(function_request)

            assert response.success is True
            assert response.stdout is not None

            # Should NOT contain DEBUG logs from orchestration
            assert "LogCapture initialized with level" not in response.stdout
            assert "Starting remote function execution" not in response.stdout

            # Should NOT contain DEBUG logs from function (filtered out)
            assert "DEBUG: This is a debug message" not in response.stdout

            # Should contain INFO and above from function
            assert "INFO: This is an info message" in response.stdout
            assert "WARNING: This is a warning message" in response.stdout

            # Should contain print output
            assert "Standard print output" in response.stdout

    @pytest.mark.asyncio
    async def test_orchestration_logging_captured(
        self, function_request_with_dependencies
    ):
        """Test that orchestration logs from dependency installation are captured."""
        with patch.dict(os.environ, {"LOG_LEVEL": "DEBUG"}):
            # Configure logging for test
            logging.getLogger().setLevel(logging.DEBUG)

            executor = RemoteExecutor()

            # Mock dependency installer to avoid actual package installation
            with patch.object(
                executor.dependency_installer, "install_dependencies"
            ) as mock_install:
                mock_response = FunctionResponse(
                    success=True, stdout="Mocked dependency installation completed"
                )
                mock_install.return_value = mock_response

                response = await executor.ExecuteFunction(
                    function_request_with_dependencies
                )

                assert response.success is True
                assert response.stdout is not None

                # Should contain orchestration DEBUG logs
                assert "LogCapture initialized with level" in response.stdout
                assert "Installing Python dependencies" in response.stdout

                # Should contain function logs
                assert "Function executed successfully" in response.stdout

    @pytest.mark.asyncio
    async def test_acceleration_summary_debug_only(
        self, function_request_with_dependencies
    ):
        """Test that acceleration summary only appears at DEBUG level."""
        # Test with INFO level - should not show acceleration summary
        with patch.dict(os.environ, {"LOG_LEVEL": "INFO"}):
            logging.getLogger().setLevel(logging.INFO)

            executor = RemoteExecutor()

            # Mock to avoid actual dependency installation
            with patch.object(
                executor.dependency_installer, "install_dependencies"
            ) as mock_install:
                mock_response = FunctionResponse(success=True, stdout="")
                mock_install.return_value = mock_response

                response = await executor.ExecuteFunction(
                    function_request_with_dependencies
                )

                assert response.success is True

                # Should NOT contain acceleration summary (DEBUG level only)
                assert "DOWNLOAD ACCELERATION SUMMARY" not in response.stdout

        # Test with DEBUG level - should show acceleration summary
        with patch.dict(os.environ, {"LOG_LEVEL": "DEBUG"}):
            logging.getLogger().setLevel(logging.DEBUG)

            executor = RemoteExecutor()

            with patch.object(
                executor.dependency_installer, "install_dependencies"
            ) as mock_install:
                mock_response = FunctionResponse(success=True, stdout="")
                mock_install.return_value = mock_response

                response = await executor.ExecuteFunction(
                    function_request_with_dependencies
                )

                assert response.success is True

                # Should contain acceleration summary (DEBUG level)
                assert "=== DOWNLOAD ACCELERATION SUMMARY ===" in response.stdout

    @pytest.mark.asyncio
    async def test_log_capture_performance_optimization(self, function_request):
        """Test that expensive log operations are skipped when not at DEBUG level."""
        with patch.dict(os.environ, {"LOG_LEVEL": "WARNING"}):
            logging.getLogger().setLevel(logging.WARNING)

            executor = RemoteExecutor()

            # Mock _log_acceleration_summary to verify it's called but returns early
            original_method = executor._log_acceleration_summary
            call_count = 0
            early_return_count = 0

            def mock_summary(request, result):
                nonlocal call_count, early_return_count
                call_count += 1
                # Check if it would return early
                if not executor.logger.isEnabledFor(logging.DEBUG):
                    early_return_count += 1
                return original_method(request, result)

            executor._log_acceleration_summary = mock_summary

            response = await executor.ExecuteFunction(function_request)

            assert response.success is True
            # Verify the optimization worked
            assert call_count == 1
            assert early_return_count == 1

            # Should not contain any acceleration logs
            assert "DOWNLOAD ACCELERATION SUMMARY" not in response.stdout

    @pytest.mark.asyncio
    async def test_error_handling_with_log_capture(self):
        """Test that log capture works correctly during error scenarios."""
        with patch.dict(os.environ, {"LOG_LEVEL": "DEBUG"}):
            logging.getLogger().setLevel(logging.DEBUG)

            # Create a request that will fail
            bad_request = FunctionRequest(
                function_name="nonexistent_function",
                function_code="# This code doesn't define the requested function",
                args=[],
                kwargs={},
            )

            executor = RemoteExecutor()
            response = await executor.ExecuteFunction(bad_request)

            assert response.success is False
            assert response.stdout is not None

            # Should contain orchestration logs even during errors
            assert "LogCapture initialized with level" in response.stdout
            assert "Starting remote function execution" in response.stdout

            # Should contain error information (in result field for function not found)
            assert "nonexistent_function" in response.result
