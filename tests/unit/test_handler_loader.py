"""Tests for dynamic handler loading in handler.py."""

import os
import pytest
from unittest.mock import patch

from handler import load_handler


class TestLoadHandlerDefault:
    """Test default handler loading behavior."""

    def test_load_handler_default(self, capsys):
        """Test loading the default live_serverless handler."""
        # Ensure HANDLER_MODULE is not set
        with patch.dict(os.environ, {}, clear=True):
            handler_func = load_handler()

            # Verify handler is callable
            assert callable(handler_func)

            # Verify success message
            captured = capsys.readouterr()
            assert "Loaded handler from module: live_serverless" in captured.out

    def test_load_handler_returns_correct_type(self):
        """Test that load_handler returns a callable."""
        with patch.dict(os.environ, {}, clear=True):
            handler_func = load_handler()

            # Type check
            assert callable(handler_func)
            # Handler should accept dict and return dict
            assert handler_func.__code__.co_argcount >= 1


class TestLoadHandlerCustomModule:
    """Test loading custom handler modules."""

    def test_load_handler_custom_module(self, capsys, mock_handler_module):
        """Test loading a custom handler module via environment variable."""
        with patch.dict(os.environ, {"HANDLER_MODULE": "custom_handler"}):
            with patch(
                "handler.importlib.import_module", return_value=mock_handler_module
            ):
                handler_func = load_handler()

                # Verify the correct handler was loaded
                assert callable(handler_func)
                assert handler_func == mock_handler_module.handler

                # Verify success message
                captured = capsys.readouterr()
                assert "Loaded handler from module: custom_handler" in captured.out

    def test_load_handler_nested_module_path(self, capsys, mock_handler_module):
        """Test loading handler from nested module path."""
        with patch.dict(os.environ, {"HANDLER_MODULE": "handlers.custom.my_handler"}):
            with patch(
                "handler.importlib.import_module", return_value=mock_handler_module
            ):
                handler_func = load_handler()

                # Verify handler loaded successfully
                assert callable(handler_func)

                # Verify correct module path in message
                captured = capsys.readouterr()
                assert (
                    "Loaded handler from module: handlers.custom.my_handler"
                    in captured.out
                )


class TestLoadHandlerErrorHandling:
    """Test error handling in handler loading."""

    def test_load_handler_module_not_found(self, capsys):
        """Test ImportError when module doesn't exist."""
        with patch.dict(os.environ, {"HANDLER_MODULE": "nonexistent_module"}):
            with pytest.raises(ImportError):
                load_handler()

            # Verify error message to stderr
            captured = capsys.readouterr()
            assert "Failed to import module 'nonexistent_module'" in captured.err

    def test_load_handler_missing_handler_attribute(self, capsys, mock_invalid_module):
        """Test AttributeError when module doesn't have handler function."""
        with patch.dict(os.environ, {"HANDLER_MODULE": "invalid_module"}):
            with patch(
                "handler.importlib.import_module", return_value=mock_invalid_module
            ):
                with pytest.raises(AttributeError) as exc_info:
                    load_handler()

                # Verify error message
                assert "does not export a 'handler' function" in str(exc_info.value)

                # Verify error printed to stderr
                captured = capsys.readouterr()
                assert "does not export a 'handler' function" in captured.err

    def test_load_handler_handler_not_callable(self, capsys, mock_non_callable_handler):
        """Test TypeError when handler attribute is not callable."""
        with patch.dict(os.environ, {"HANDLER_MODULE": "non_callable_module"}):
            with patch(
                "handler.importlib.import_module",
                return_value=mock_non_callable_handler,
            ):
                with pytest.raises(TypeError) as exc_info:
                    load_handler()

                # Verify error message
                assert (
                    "'handler' in module 'non_callable_module' is not callable"
                    in str(exc_info.value)
                )

                # Verify error printed to stderr
                captured = capsys.readouterr()
                assert "is not callable" in captured.err

    def test_load_handler_import_error_details(self, capsys):
        """Test that ImportError details are preserved and reported."""
        error_message = "No module named 'missing_dependency'"

        with patch.dict(os.environ, {"HANDLER_MODULE": "broken_module"}):
            with patch(
                "handler.importlib.import_module",
                side_effect=ImportError(error_message),
            ):
                with pytest.raises(ImportError) as exc_info:
                    load_handler()

                # Verify original error is preserved
                assert error_message in str(exc_info.value)

                # Verify error details in stderr
                captured = capsys.readouterr()
                assert "Failed to import module 'broken_module'" in captured.err
                assert error_message in captured.err


class TestLoadHandlerOutputVerification:
    """Test output and logging behavior."""

    def test_load_handler_prints_success_message(self, capsys, mock_handler_module):
        """Test that successful loading prints message to stdout."""
        with patch.dict(os.environ, {"HANDLER_MODULE": "test_module"}):
            with patch(
                "handler.importlib.import_module", return_value=mock_handler_module
            ):
                load_handler()

                captured = capsys.readouterr()
                assert captured.out.strip() == "Loaded handler from module: test_module"

    def test_load_handler_prints_error_to_stderr(self, capsys):
        """Test that errors are printed to stderr, not stdout."""
        with patch.dict(os.environ, {"HANDLER_MODULE": "error_module"}):
            with patch(
                "handler.importlib.import_module",
                side_effect=ImportError("test error"),
            ):
                with pytest.raises(ImportError):
                    load_handler()

                captured = capsys.readouterr()
                # stdout should be empty
                assert captured.out == ""
                # stderr should contain error
                assert "Error: Failed to import module 'error_module'" in captured.err
                assert "test error" in captured.err

    def test_load_handler_env_var_precedence(self, capsys, mock_handler_module):
        """Test that HANDLER_MODULE env var takes precedence over default."""
        # Set environment variable
        with patch.dict(os.environ, {"HANDLER_MODULE": "priority_handler"}):
            with patch(
                "handler.importlib.import_module", return_value=mock_handler_module
            ):
                load_handler()

                captured = capsys.readouterr()
                # Should NOT load live_serverless
                assert "live_serverless" not in captured.out
                # Should load priority_handler
                assert "priority_handler" in captured.out
