"""Integration tests for Flash deployed app functionality.

Tests the dual-mode runtime capability where the same handler can serve
both Live Serverless and Flash Deployed Apps.
"""

import pytest
from unittest.mock import patch

from remote_executor import RemoteExecutor
from tetra_rp.protos.remote_execution import FunctionRequest


class TestFlashIntegration:
    """Integration tests for Flash deployment execution."""

    def setup_method(self):
        """Setup for each test method."""
        self.executor = RemoteExecutor()

    @pytest.mark.asyncio
    async def test_dual_mode_coexistence(self):
        """Test that same executor handles both Live Serverless and Flash requests."""
        # First, test Live Serverless request
        live_request = FunctionRequest(
            function_name="live_func",
            function_code="def live_func(): return 'live_result'",
            args=[],
            kwargs={},
        )

        live_response = await self.executor.ExecuteFunction(live_request)
        assert live_response.success is True

        # Now test Flash request (without function_code)
        flash_request = FunctionRequest(
            function_name="flash_func",
            args=[],
            kwargs={},
        )

        # Mock the Flash execution path
        mock_manifest = {
            "function_registry": {"flash_func": "resource_01"},
            "resources": {
                "resource_01": {
                    "functions": [
                        {
                            "name": "flash_func",
                            "module": "test_module",
                            "is_async": False,
                        }
                    ]
                }
            },
        }

        with (
            patch.object(self.executor, "_load_flash_manifest", return_value=mock_manifest),
            patch("importlib.import_module") as mock_import,
            patch("asyncio.to_thread") as mock_to_thread,
        ):
            from unittest.mock import Mock

            mock_func = Mock(return_value="flash_result")
            mock_module = Mock()
            mock_module.flash_func = mock_func
            mock_import.return_value = mock_module
            mock_to_thread.return_value = "flash_result"

            flash_response = await self.executor.ExecuteFunction(flash_request)

        assert flash_response.success is True
        # Both modes work in same executor instance
        assert live_response.success is True
        assert flash_response.success is True

    @pytest.mark.asyncio
    async def test_flash_execution_end_to_end_with_manifest(self):
        """Test Flash execution with mock manifest and function import."""
        mock_manifest = {
            "version": "1.0",
            "function_registry": {"test_function": "resource_01"},
            "resources": {
                "resource_01": {
                    "resource_type": "LiveServerless",
                    "functions": [
                        {
                            "name": "test_function",
                            "module": "my_module",
                            "is_async": False,
                        }
                    ],
                }
            },
        }

        request = FunctionRequest(
            function_name="test_function",
            args=[],
            kwargs={},
        )

        with (
            patch.object(self.executor, "_load_flash_manifest", return_value=mock_manifest),
            patch("importlib.import_module") as mock_import,
            patch("asyncio.to_thread") as mock_to_thread,
        ):
            from unittest.mock import Mock

            mock_func = Mock(return_value={"status": "success"})
            mock_module = Mock()
            mock_module.test_function = mock_func
            mock_import.return_value = mock_module
            mock_to_thread.return_value = {"status": "success"}

            response = await self.executor.ExecuteFunction(request)

        assert response.success is True
        assert response.result is not None
        mock_import.assert_any_call("my_module")

    @pytest.mark.asyncio
    async def test_flash_execution_with_async_function(self):
        """Test Flash execution handles async functions correctly."""
        mock_manifest = {
            "function_registry": {"async_func": "resource_01"},
            "resources": {
                "resource_01": {
                    "functions": [
                        {
                            "name": "async_func",
                            "module": "async_module",
                            "is_async": True,
                        }
                    ]
                }
            },
        }

        async def mock_async_function():
            return "async_result"

        request = FunctionRequest(
            function_name="async_func",
            args=[],
            kwargs={},
        )

        with (
            patch.object(self.executor, "_load_flash_manifest", return_value=mock_manifest),
            patch("importlib.import_module") as mock_import,
        ):
            from unittest.mock import Mock

            mock_module = Mock()
            mock_module.async_func = mock_async_function
            mock_import.return_value = mock_module

            response = await self.executor.ExecuteFunction(request)

        assert response.success is True
        assert response.result is not None

    @pytest.mark.asyncio
    async def test_flash_manifest_missing_function(self):
        """Test error handling when function not found in manifest."""
        mock_manifest = {
            "function_registry": {},
            "resources": {},
        }

        request = FunctionRequest(
            function_name="nonexistent_function",
            args=[],
            kwargs={},
        )

        with patch.object(self.executor, "_load_flash_manifest", return_value=mock_manifest):
            response = await self.executor.ExecuteFunction(request)

        assert response.success is False
        assert "not found in flash_manifest.json" in response.error

    @pytest.mark.asyncio
    async def test_flash_manifest_file_not_found(self):
        """Test error handling when manifest file doesn't exist."""
        request = FunctionRequest(
            function_name="test_func",
            args=[],
            kwargs={},
        )

        # Mock Path.exists to return False
        with patch("pathlib.Path.exists", return_value=False):
            response = await self.executor.ExecuteFunction(request)

        assert response.success is False
        assert "flash_manifest.json not found" in response.error

    @pytest.mark.asyncio
    async def test_flash_function_import_failure(self):
        """Test error handling when function import fails."""
        mock_manifest = {
            "function_registry": {"failing_func": "resource_01"},
            "resources": {
                "resource_01": {
                    "functions": [
                        {
                            "name": "failing_func",
                            "module": "nonexistent_module",
                            "is_async": False,
                        }
                    ]
                }
            },
        }

        request = FunctionRequest(
            function_name="failing_func",
            args=[],
            kwargs={},
        )

        with (
            patch.object(self.executor, "_load_flash_manifest", return_value=mock_manifest),
            patch("importlib.import_module") as mock_import,
        ):
            mock_import.side_effect = ModuleNotFoundError("No module named 'nonexistent_module'")

            response = await self.executor.ExecuteFunction(request)

        assert response.success is False
        assert "Failed to execute Flash function" in response.error
        assert "nonexistent_module" in response.error

    @pytest.mark.asyncio
    async def test_live_serverless_backward_compatibility(self):
        """Test that existing Live Serverless requests still work after Flash integration."""
        # Test function execution
        function_request = FunctionRequest(
            function_name="my_function",
            function_code="def my_function(): return 'result'",
            args=[],
            kwargs={},
        )

        response = await self.executor.ExecuteFunction(function_request)
        assert response.success is True

        # Test class execution
        class_request = FunctionRequest(
            execution_type="class",
            class_name="MyClass",
            class_code="class MyClass:\n    def __call__(self): return 'result'",
            args=[],
            kwargs={},
        )

        response = await self.executor.ExecuteFunction(class_request)
        assert response.success is True
