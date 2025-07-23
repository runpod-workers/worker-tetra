import pytest
import json
import base64
import cloudpickle
from pathlib import Path

from handler import handler, RemoteExecutor
from remote_execution import FunctionRequest


class TestHandlerIntegration:
    """Integration tests using test_input.json and test_class_input.json."""

    def setup_method(self):
        """Setup for each test method."""
        self.test_data_dir = Path(__file__).parent.parent.parent
        self.test_input_file = self.test_data_dir / "test_input.json"
        self.test_class_input_file = self.test_data_dir / "test_class_input.json"

    @pytest.mark.asyncio
    async def test_handler_end_to_end(self):
        """Test complete handler workflow with simple function"""
        event = {
            "input": {
                "function_name": "hello_world",
                "function_code": "def hello_world():\n    return 'hello world'",
                "args": [],
                "kwargs": {},
            }
        }

        result = await handler(event)

        assert result["success"] is True
        assert result["error"] is None
        assert result["result"] is not None

    @pytest.mark.asyncio
    async def test_handler_with_test_input_json(self):
        """Test handler using test_input.json."""
        # Load the test input data
        with open(self.test_input_file, "r") as f:
            test_data = json.load(f)

        # Execute through the handler
        result = await handler(test_data)

        # Verify the response
        assert result["success"] is True
        assert "result" in result
        assert result["error"] is None

        # Decode and verify the actual result
        decoded_result = cloudpickle.loads(base64.b64decode(result["result"]))
        assert decoded_result == "hello world"

        # Check that stdout was captured
        assert "going to say hello" in result["stdout"]

    @pytest.mark.asyncio
    async def test_handler_with_test_class_input_json(self):
        """Test handler using test_class_input.json."""
        # Load the test class input data
        with open(self.test_class_input_file, "r") as f:
            test_data = json.load(f)

        # Execute through the handler
        result = await handler(test_data)

        # Verify the response
        assert result["success"] is True
        assert "result" in result
        assert result["error"] is None
        assert "instance_id" in result

        # Decode and verify the actual result
        decoded_result = cloudpickle.loads(base64.b64decode(result["result"]))
        assert decoded_result == "Value is: hello"

        # Verify instance information
        assert result["instance_id"] is not None
        assert "instance_info" in result
        assert result["instance_info"]["class_name"] == "TestClass"
        assert result["instance_info"]["method_calls"] == 1

    @pytest.mark.asyncio
    async def test_class_instance_reuse(self):
        """Test reusing class instances across multiple calls."""
        executor = RemoteExecutor()

        # First call - create instance
        request1 = FunctionRequest(
            execution_type="class",
            class_name="Counter",
            class_code="class Counter:\n    def __init__(self):\n        self.count = 0\n    def increment(self):\n        self.count += 1\n        return self.count",
            method_name="increment",
            constructor_args=[],
            constructor_kwargs={},
            args=[],
            kwargs={},
            create_new_instance=True,
        )

        response1 = await executor.ExecuteFunction(request1)
        assert response1.success is True
        instance_id = response1.instance_id

        result1 = cloudpickle.loads(base64.b64decode(response1.result))
        assert result1 == 1

        # Second call - reuse instance
        request2 = FunctionRequest(
            execution_type="class",
            class_name="Counter",
            class_code="class Counter:\n    def __init__(self):\n        self.count = 0\n    def increment(self):\n        self.count += 1\n        return self.count",
            method_name="increment",
            instance_id=instance_id,
            create_new_instance=False,
            args=[],
            kwargs={},
        )

        response2 = await executor.ExecuteFunction(request2)
        assert response2.success is True
        assert response2.instance_id == instance_id

        result2 = cloudpickle.loads(base64.b64decode(response2.result))
        assert result2 == 2  # Should increment from previous state

        # Verify metadata was updated
        assert response2.instance_info["method_calls"] == 2

    @pytest.mark.asyncio
    async def test_handler_error_scenarios(self):
        """Test handler with invalid input scenarios."""
        # Test with completely invalid event structure
        invalid_event = {"invalid": "structure"}
        result = await handler(invalid_event)
        assert result["success"] is False
        assert "Error in handler" in result["error"]

        # Test with missing required fields
        invalid_event2 = {
            "input": {
                "execution_type": "function"
                # Missing function_name and function_code
            }
        }
        result2 = await handler(invalid_event2)
        assert result2["success"] is False

    @pytest.mark.asyncio
    async def test_complex_data_serialization(self):
        """Test handling complex data types through the full pipeline."""
        test_data = {
            "numbers": [1, 2, 3, 4, 5],
            "metadata": {"name": "test", "version": 1.0},
        }

        event = {
            "input": {
                "function_name": "process_data",
                "function_code": """
def process_data(data):
    return {
        'sum': sum(data['numbers']),
        'name': data['metadata']['name'],
        'processed': True
    }
""",
                "args": [
                    base64.b64encode(cloudpickle.dumps(test_data)).decode("utf-8")
                ],
                "kwargs": {},
            }
        }

        result = await handler(event)
        assert result["success"] is True

        decoded_result = cloudpickle.loads(base64.b64decode(result["result"]))
        assert decoded_result["sum"] == 15
        assert decoded_result["name"] == "test"
        assert decoded_result["processed"] is True
