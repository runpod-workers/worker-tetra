import os
import pytest
import json
import base64
import cloudpickle
from pathlib import Path
from unittest.mock import patch

from handler import handler, RemoteExecutor
from remote_execution import FunctionRequest


class TestHandlerIntegration:
    """Integration tests using test_input.json and test_class_input.json."""

    def setup_method(self):
        """Setup for each test method."""
        self.test_data_dir = Path(__file__).parent.parent.parent / "src" / "tests"
        self.test_input_file = self.test_data_dir / "test_input.json"
        self.test_class_input_file = self.test_data_dir / "test_class_input.json"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_end_to_end_simple_function(self):
        """Test complete end-to-end execution of a simple function."""
        event = {
            "input": {
                "function_name": "hello_world",
                "function_code": """
def hello_world():
    print("Hello from integration test")
    return "integration success"
""",
                "args": [],
                "kwargs": {},
            }
        }

        result = await handler(event)

        assert result["success"] is True
        deserialized_result = cloudpickle.loads(base64.b64decode(result["result"]))
        assert deserialized_result == "integration success"
        assert "Hello from integration test" in result["stdout"]

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_end_to_end_function_with_args(self):
        """Test complete execution with function arguments."""
        arg1 = base64.b64encode(cloudpickle.dumps(10)).decode("utf-8")
        arg2 = base64.b64encode(cloudpickle.dumps(5)).decode("utf-8")

        event = {
            "input": {
                "function_name": "calculate",
                "function_code": """
def calculate(a, b):
    print(f"Calculating {a} * {b}")
    result = a * b
    print(f"Result: {result}")
    return result
""",
                "args": [arg1, arg2],
                "kwargs": {},
            }
        }

        result = await handler(event)

        assert result["success"] is True
        deserialized_result = cloudpickle.loads(base64.b64decode(result["result"]))
        assert deserialized_result == 50
        assert "Calculating 10 * 5" in result["stdout"]
        assert "Result: 50" in result["stdout"]

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_end_to_end_function_with_kwargs(self):
        """Test complete execution with keyword arguments."""
        kwarg_value = base64.b64encode(cloudpickle.dumps("integration")).decode("utf-8")

        event = {
            "input": {
                "function_name": "greet",
                "function_code": """
def greet(name="world"):
    message = f"Hello, {name}!"
    print(message)
    return message
""",
                "args": [],
                "kwargs": {"name": kwarg_value},
            }
        }

        result = await handler(event)

        assert result["success"] is True
        deserialized_result = cloudpickle.loads(base64.b64decode(result["result"]))
        assert deserialized_result == "Hello, integration!"
        assert "Hello, integration!" in result["stdout"]

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_end_to_end_function_error_handling(self):
        """Test error handling in end-to-end execution."""
        event = {
            "input": {
                "function_name": "error_func",
                "function_code": """
def error_func():
    print("About to raise an error")
    raise ValueError("Integration test error")
""",
                "args": [],
                "kwargs": {},
            }
        }

        result = await handler(event)

        assert result["success"] is False
        assert "Integration test error" in result["error"]
        assert "ValueError" in result["error"]
        assert "About to raise an error" in result["stdout"]

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_end_to_end_function_with_logging(self):
        """Test function execution with logging output."""
        event = {
            "input": {
                "function_name": "log_test",
                "function_code": """
def log_test():
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    logger.info("This is an info message")
    logger.warning("This is a warning message")
    print("This is a print statement")
    
    return "logging complete"
""",
                "args": [],
                "kwargs": {},
            }
        }

        result = await handler(event)

        assert result["success"] is True
        deserialized_result = cloudpickle.loads(base64.b64decode(result["result"]))
        assert deserialized_result == "logging complete"

        # Should capture both print and log output
        output = result["stdout"]
        assert "This is a print statement" in output
        # Note: logging output might be captured depending on handler setup

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

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_end_to_end_complex_data_types(self):
        """Test serialization/deserialization of complex data types."""
        complex_input = {
            "list": [1, 2, 3],
            "dict": {"nested": {"deep": "value"}},
            "tuple": (4, 5, 6),
        }

        serialized_input = base64.b64encode(cloudpickle.dumps(complex_input)).decode(
            "utf-8"
        )

        event = {
            "input": {
                "function_name": "process_data",
                "function_code": """
def process_data(data):
    result = {
        "received_list": data["list"],
        "received_dict": data["dict"],
        "received_tuple": list(data["tuple"]),
        "total_count": len(data["list"]) + len(data["tuple"])
    }
    return result
""",
                "args": [serialized_input],
                "kwargs": {},
            }
        }

        result = await handler(event)

        assert result["success"] is True
        deserialized_result = cloudpickle.loads(base64.b64decode(result["result"]))

        assert deserialized_result["received_list"] == [1, 2, 3]
        assert deserialized_result["received_dict"] == {"nested": {"deep": "value"}}
        assert deserialized_result["received_tuple"] == [4, 5, 6]
        assert deserialized_result["total_count"] == 6

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_end_to_end_function_not_found(self):
        """Test error when function name doesn't exist in code."""
        event = {
            "input": {
                "function_name": "nonexistent_function",
                "function_code": """
def some_other_function():
    return "wrong function"
""",
                "args": [],
                "kwargs": {},
            }
        }

        result = await handler(event)

        assert result["success"] is False
        assert "Function 'nonexistent_function' not found" in result["result"]

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_end_to_end_invalid_python_code(self):
        """Test error handling with invalid Python code."""
        event = {
            "input": {
                "function_name": "bad_function",
                "function_code": """
def bad_function(:
    return "this is invalid syntax"
""",
                "args": [],
                "kwargs": {},
            }
        }

        result = await handler(event)

        assert result["success"] is False
        assert "SyntaxError" in result["error"] or "invalid syntax" in result["error"]

    @pytest.mark.integration
    def test_remote_executor_direct_execution(self):
        """Test RemoteExecutor direct method calls."""
        executor = RemoteExecutor()

        request = FunctionRequest(
            function_name="direct_test",
            function_code="""
def direct_test():
    return "direct execution success"
""",
            args=[],
            kwargs={},
        )

        result = executor.function_executor.execute(request)

        assert result.success is True
        deserialized_result = cloudpickle.loads(base64.b64decode(result.result))
        assert deserialized_result == "direct execution success"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_malformed_input_handling(self):
        """Test handling of various malformed inputs."""
        test_cases = [
            {},  # Empty event
            {"input": {}},  # Missing required fields
            {"input": {"function_name": "test"}},  # Missing function_code
            {"input": {"function_code": "def test(): pass"}},  # Missing function_name
        ]

        for malformed_event in test_cases:
            result = await handler(malformed_event)
            assert result["success"] is False
            assert "error" in result

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_real_world_scenario(self):
        """Test a realistic function execution scenario."""
        event = {
            "input": {
                "function_name": "data_processor",
                "function_code": """
def data_processor():
    import json
    import datetime
    
    # Simulate some data processing
    data = {
        "timestamp": str(datetime.datetime.now()),
        "processed_items": [i**2 for i in range(5)],
        "status": "completed"
    }
    
    print(f"Processed {len(data['processed_items'])} items")
    return data
""",
                "args": [],
                "kwargs": {},
            }
        }

        result = await handler(event)

        assert result["success"] is True
        deserialized_result = cloudpickle.loads(base64.b64decode(result["result"]))

        assert "timestamp" in deserialized_result
        assert deserialized_result["processed_items"] == [0, 1, 4, 9, 16]
        assert deserialized_result["status"] == "completed"
        assert "Processed 5 items" in result["stdout"]

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

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_hf_cache_ahead_basic(self):
        """Test basic HuggingFace model cache-ahead functionality."""
        event = {
            "input": {
                "function_name": "test_model_usage",
                "function_code": """
def test_model_usage():
    from transformers import AutoTokenizer

    # Use the pre-cached model
    tokenizer = AutoTokenizer.from_pretrained("gpt2")
    result = tokenizer("Hello world")

    return {
        "tokens": len(result["input_ids"]),
        "model": "gpt2"
    }
""",
                "dependencies": ["transformers"],
                "hf_models_to_cache": ["gpt2"],
                "accelerate_downloads": True,
                "args": [],
                "kwargs": {},
            }
        }

        result = await handler(event)

        assert result["success"] is True
        decoded_result = cloudpickle.loads(base64.b64decode(result["result"]))
        assert decoded_result["model"] == "gpt2"
        assert decoded_result["tokens"] > 0

    @pytest.mark.integration
    @pytest.mark.asyncio
    @patch("huggingface_cache.HuggingFaceCacheAhead._is_model_cached")
    async def test_hf_cache_hit_scenario(self, mock_is_cached):
        """Test cache hit detection prevents redundant downloads."""
        # First call: simulate cache miss
        mock_is_cached.return_value = False

        event = {
            "input": {
                "function_name": "first_call",
                "function_code": """
def first_call():
    return "first"
""",
                "hf_models_to_cache": ["gpt2"],
                "accelerate_downloads": True,
                "args": [],
                "kwargs": {},
            }
        }

        result1 = await handler(event)
        assert result1["success"] is True

        # Second call: simulate cache hit
        mock_is_cached.return_value = True

        result2 = await handler(event)
        assert result2["success"] is True
        # Verify cache hit message in stdout
        assert "already cached" in result2["stdout"] or "cache hit" in result2["stdout"]

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_hf_multiple_models_parallel(self):
        """Test downloading multiple HF models in parallel."""
        event = {
            "input": {
                "function_name": "multi_model_test",
                "function_code": """
def multi_model_test():
    return "models cached"
""",
                "hf_models_to_cache": ["gpt2", "distilbert-base-uncased"],
                "accelerate_downloads": True,
                "args": [],
                "kwargs": {},
            }
        }

        result = await handler(event)

        assert result["success"] is True
        # Both models should be mentioned in stdout
        stdout_lower = result["stdout"].lower()
        assert "gpt2" in stdout_lower or "model" in stdout_lower

    @pytest.mark.integration
    @pytest.mark.asyncio
    @patch.dict(os.environ, {"HF_TOKEN": "test_token_value"})
    @patch("huggingface_cache.snapshot_download")
    @patch("huggingface_cache.HuggingFaceCacheAhead._is_model_cached")
    async def test_hf_authentication_with_token(
        self, mock_is_cached, mock_snapshot_download
    ):
        """Test HF_TOKEN is used for authentication."""
        mock_is_cached.return_value = False
        mock_snapshot_download.return_value = "/cache/path/private-model"

        event = {
            "input": {
                "function_name": "private_model_test",
                "function_code": """
def private_model_test():
    return "authenticated"
""",
                "hf_models_to_cache": ["private/model"],
                "accelerate_downloads": True,
                "args": [],
                "kwargs": {},
            }
        }

        result = await handler(event)

        assert result["success"] is True
        # Verify token was passed to snapshot_download
        mock_snapshot_download.assert_called()
        call_kwargs = mock_snapshot_download.call_args.kwargs
        assert call_kwargs["token"] == "test_token_value"

    @pytest.mark.integration
    @pytest.mark.asyncio
    @patch("huggingface_cache.snapshot_download")
    @patch("huggingface_cache.HuggingFaceCacheAhead._is_model_cached")
    async def test_hf_cache_failure_continues_execution(
        self, mock_is_cached, mock_snapshot_download
    ):
        """Test that cache failures don't block function execution."""
        mock_is_cached.return_value = False
        mock_snapshot_download.side_effect = Exception("Network error")

        event = {
            "input": {
                "function_name": "resilient_test",
                "function_code": """
def resilient_test():
    return "execution continues despite cache failure"
""",
                "hf_models_to_cache": ["invalid-model"],
                "accelerate_downloads": True,
                "args": [],
                "kwargs": {},
            }
        }

        result = await handler(event)

        # Execution should fail at dependency installation stage
        # since cache-ahead failed
        assert result["success"] is False
        assert (
            "Network error" in result["error"] or "Failed to cache" in result["error"]
        )

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_hf_cache_with_custom_revision(self):
        """Test caching specific model revisions."""
        event = {
            "input": {
                "function_name": "revision_test",
                "function_code": """
def revision_test():
    return "revision cached"
""",
                "hf_models_to_cache": ["gpt2"],  # Default revision (main)
                "accelerate_downloads": True,
                "args": [],
                "kwargs": {},
            }
        }

        result = await handler(event)

        assert result["success"] is True

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_hf_cache_ahead_prevents_redownload(self):
        """
        Test that cache-ahead prevents re-downloads when user code references the model.

        This is the critical test: User's code doesn't know model was pre-cached,
        but should use cached version instead of downloading from network.
        """
        import time

        # Step 1: Cache-ahead the model WITHOUT using it
        cache_event = {
            "input": {
                "function_name": "just_cache",
                "function_code": """
def just_cache():
    return "model should be cached now"
""",
                "hf_models_to_cache": ["gpt2"],
                "accelerate_downloads": True,
                "args": [],
                "kwargs": {},
            }
        }

        cache_result = await handler(cache_event)
        assert cache_result["success"] is True

        # Step 2: User code loads the model (doesn't know it's cached)
        # If cache works, this should be FAST (< 1 second)
        # If cache fails, this downloads from network (> 5 seconds)
        use_event = {
            "input": {
                "function_name": "use_cached_model",
                "function_code": """
def use_cached_model():
    import time
    from transformers import AutoTokenizer

    start = time.time()

    # User code doesn't know model was pre-cached
    tokenizer = AutoTokenizer.from_pretrained("gpt2")

    load_time = time.time() - start

    return {
        "load_time_seconds": round(load_time, 2),
        "vocab_size": tokenizer.vocab_size,
        "cache_was_used": load_time < 5.0  # Cache hit should be < 5s
    }
""",
                "dependencies": ["transformers"],
                "accelerate_downloads": True,
                "args": [],
                "kwargs": {},
            }
        }

        start_time = time.time()
        use_result = await handler(use_event)
        total_time = time.time() - start_time

        assert use_result["success"] is True
        decoded_result = cloudpickle.loads(base64.b64decode(use_result["result"]))

        # Verify model loaded successfully
        assert decoded_result["vocab_size"] == 50257  # GPT2 vocab size

        # Critical assertion: model load was fast (cache hit)
        assert decoded_result["cache_was_used"] is True, (
            f"Model took {decoded_result['load_time_seconds']}s to load. "
            f"Expected < 5s (cache hit), suggesting re-download occurred."
        )

        # Total execution should also be fast
        assert total_time < 30, (
            f"Total execution took {total_time:.2f}s. "
            f"Should be < 30s with cached model."
        )
