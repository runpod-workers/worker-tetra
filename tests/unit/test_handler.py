"""Tests for the RunPod handler function."""

import pytest
import base64
import cloudpickle
from unittest.mock import patch, AsyncMock
from handler import handler
from tetra_rp.protos.remote_execution import FunctionResponse


class TestHandler:
    """Test cases for the RunPod handler function."""

    @pytest.mark.asyncio
    async def test_handler_success(self):
        """Test successful handler execution."""
        event = {
            "input": {
                "function_name": "test_func",
                "function_code": "def test_func(): return 'success'",
                "args": [],
                "kwargs": {},
            }
        }

        with patch("handler.RemoteExecutor") as mock_executor_class:
            mock_executor = AsyncMock()
            mock_executor_class.return_value = mock_executor
            mock_executor.ExecuteFunction.return_value = FunctionResponse(
                success=True,
                result=base64.b64encode(cloudpickle.dumps("success")).decode("utf-8"),
                stdout="Function executed successfully",
            )

            result = await handler(event)

            assert result["success"] is True
            assert "result" in result

    @pytest.mark.asyncio
    async def test_handler_invalid_input(self):
        """Test handler with invalid input data."""
        event = {
            "input": {
                # Missing required fields
                "args": [],
                "kwargs": {},
            }
        }

        result = await handler(event)

        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_handler_missing_input(self):
        """Test handler with missing input key."""
        event = {}  # No input key

        result = await handler(event)

        # Should handle missing input gracefully
        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_handler_executor_exception(self):
        """Test handler when RemoteExecutor raises exception."""
        event = {
            "input": {
                "function_name": "test_func",
                "function_code": "def test_func(): return 'test'",
                "args": [],
                "kwargs": {},
            }
        }

        with patch("handler.RemoteExecutor") as mock_executor_class:
            mock_executor_class.side_effect = Exception("Executor initialization failed")

            result = await handler(event)

            assert result["success"] is False
            assert "Error in handler" in result["error"]
            assert "Executor initialization failed" in result["error"]

    @pytest.mark.asyncio
    async def test_handler_response_serialization(self):
        """Test that handler properly serializes FunctionResponse to dict."""
        event = {
            "input": {
                "function_name": "test_func",
                "function_code": "def test_func(): return {'data': 'test'}",
                "args": [],
                "kwargs": {},
            }
        }

        test_data = {"data": "test"}
        with patch("handler.RemoteExecutor") as mock_executor_class:
            mock_executor = AsyncMock()
            mock_executor_class.return_value = mock_executor
            mock_executor.ExecuteFunction.return_value = FunctionResponse(
                success=True,
                result=base64.b64encode(cloudpickle.dumps(test_data)).decode("utf-8"),
                stdout="Test output",
            )

            result = await handler(event)

            # Verify the response is properly serialized
            assert isinstance(result, dict)
            assert result["success"] is True
            assert "result" in result
            assert result["stdout"] == "Test output"

    @pytest.mark.asyncio
    async def test_handler_class_execution(self):
        """Test handler with class execution request."""
        event = {
            "input": {
                "execution_type": "class",
                "class_name": "TestClass",
                "class_code": "class TestClass:\n    def __call__(self): return 'class result'",
                "args": [],
                "kwargs": {},
            }
        }

        with patch("handler.RemoteExecutor") as mock_executor_class:
            mock_executor = AsyncMock()
            mock_executor_class.return_value = mock_executor
            mock_executor.ExecuteFunction.return_value = FunctionResponse(
                success=True,
                result=base64.b64encode(cloudpickle.dumps("class result")).decode("utf-8"),
                instance_id="TestClass_12345678",
                instance_info={"class_name": "TestClass", "method_calls": 1},
            )

            result = await handler(event)

            assert result["success"] is True
            assert "instance_id" in result
            assert "instance_info" in result
