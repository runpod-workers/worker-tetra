"""Tests for the universal handler protocol."""

import pytest
from pydantic import ValidationError


class TestHandlerEvent:
    """Test HandlerEvent model validation and behavior."""

    def test_handler_event_with_valid_input(self):
        """Test creating HandlerEvent with valid input."""
        from handler_protocol import HandlerEvent

        event_data = {"input": {"function_name": "test", "args": []}}
        event = HandlerEvent(**event_data)

        assert event.input == {"function_name": "test", "args": []}
        assert isinstance(event.input, dict)

    def test_handler_event_with_complex_input(self):
        """Test HandlerEvent with complex nested input."""
        from handler_protocol import HandlerEvent

        event_data = {
            "input": {
                "function_name": "process",
                "args": [1, 2, 3],
                "kwargs": {"key": "value"},
                "nested": {"deep": {"data": "test"}},
            }
        }
        event = HandlerEvent(**event_data)

        assert event.input["function_name"] == "process"
        assert event.input["nested"]["deep"]["data"] == "test"

    def test_handler_event_missing_input_field(self):
        """Test that HandlerEvent requires input field."""
        from handler_protocol import HandlerEvent

        event_data = {"wrong_field": "data"}

        with pytest.raises(ValidationError) as exc_info:
            HandlerEvent(**event_data)

        assert "input" in str(exc_info.value)

    def test_handler_event_with_empty_input(self):
        """Test HandlerEvent with empty input dict."""
        from handler_protocol import HandlerEvent

        event_data = {"input": {}}
        event = HandlerEvent(**event_data)

        assert event.input == {}

    def test_handler_event_with_extra_fields(self):
        """Test that HandlerEvent allows extra fields (RunPod metadata)."""
        from handler_protocol import HandlerEvent

        event_data = {
            "input": {"data": "test"},
            "id": "job-123",
            "job_id": "runpod-job-456",
        }
        event = HandlerEvent(**event_data)

        assert event.input == {"data": "test"}
        # Extra fields should be accessible
        assert hasattr(event, "id")
        assert event.id == "job-123"

    def test_handler_event_serialization(self):
        """Test HandlerEvent can be serialized to dict."""
        from handler_protocol import HandlerEvent

        event_data = {"input": {"key": "value"}, "job_id": "123"}
        event = HandlerEvent(**event_data)

        serialized = event.model_dump()
        assert serialized["input"] == {"key": "value"}
        assert serialized["job_id"] == "123"

    def test_handler_event_deserialization(self):
        """Test HandlerEvent can be created from dict."""
        from handler_protocol import HandlerEvent

        event_dict = {"input": {"function": "test"}}
        event = HandlerEvent.model_validate(event_dict)

        assert event.input["function"] == "test"

    def test_handler_event_json_serialization(self):
        """Test HandlerEvent can be serialized to/from JSON."""
        from handler_protocol import HandlerEvent
        import json

        event_data = {"input": {"data": [1, 2, 3]}}
        event = HandlerEvent(**event_data)

        # Serialize to JSON
        json_str = event.model_dump_json()
        parsed = json.loads(json_str)

        assert parsed["input"]["data"] == [1, 2, 3]

        # Deserialize from JSON
        event2 = HandlerEvent.model_validate_json(json_str)
        assert event2.input == event.input

    def test_handler_event_dict_coercion(self):
        """Test that plain dict can be coerced to HandlerEvent (backward compat)."""
        from handler_protocol import HandlerEvent

        # This simulates what happens when a function expecting HandlerEvent
        # receives a plain dict (Pydantic will coerce it)
        plain_dict = {"input": {"test": "data"}}

        # Direct instantiation works
        event = HandlerEvent(**plain_dict)
        assert event.input == {"test": "data"}

    def test_handler_event_input_not_dict(self):
        """Test that input must be a dict."""
        from handler_protocol import HandlerEvent

        event_data = {"input": "not a dict"}

        with pytest.raises(ValidationError) as exc_info:
            HandlerEvent(**event_data)

        assert "input" in str(exc_info.value)


class TestHandlerFunctionType:
    """Test HandlerFunction type alias."""

    def test_handler_function_type_exists(self):
        """Test that HandlerFunction type alias is defined."""
        from handler_protocol import HandlerFunction
        from typing import get_origin

        # Verify it's a Callable type
        assert get_origin(HandlerFunction) is not None

    def test_handler_function_signature_validation(self):
        """Test that handler functions can be type-checked against HandlerFunction."""
        from handler_protocol import HandlerEvent
        from typing import Dict, Any

        # Define a valid handler function
        async def valid_handler(event: HandlerEvent) -> Dict[str, Any]:
            return {"success": True}

        # This is a compile-time check, but we can verify the signature exists
        assert callable(valid_handler)
        assert valid_handler.__annotations__["event"] == HandlerEvent
        assert valid_handler.__annotations__["return"] == Dict[str, Any]


class TestHandlerEventUsagePatterns:
    """Test common usage patterns with HandlerEvent."""

    def test_handler_event_with_live_serverless_input(self):
        """Test HandlerEvent with live_serverless-style input."""
        from handler_protocol import HandlerEvent

        event_data = {
            "input": {
                "function_name": "hello_world",
                "function_code": "def hello_world(): return 'hello'",
                "args": [],
                "kwargs": {},
            }
        }
        event = HandlerEvent(**event_data)

        assert event.input["function_name"] == "hello_world"
        assert event.input["function_code"] is not None

    def test_handler_event_with_inference_input(self):
        """Test HandlerEvent with inference-style input."""
        from handler_protocol import HandlerEvent

        event_data = {
            "input": {
                "prompt": "Generate a story",
                "model": "gpt-4",
                "temperature": 0.7,
                "max_tokens": 100,
            }
        }
        event = HandlerEvent(**event_data)

        assert event.input["prompt"] == "Generate a story"
        assert event.input["model"] == "gpt-4"
        assert event.input["temperature"] == 0.7

    def test_handler_event_with_training_input(self):
        """Test HandlerEvent with training-style input."""
        from handler_protocol import HandlerEvent

        event_data = {
            "input": {
                "dataset_uri": "s3://bucket/dataset.csv",
                "model_config": {"learning_rate": 0.001, "epochs": 10},
                "output_uri": "s3://bucket/model/",
            }
        }
        event = HandlerEvent(**event_data)

        assert event.input["dataset_uri"].startswith("s3://")
        assert event.input["model_config"]["epochs"] == 10

    def test_handler_event_access_patterns(self):
        """Test different ways to access HandlerEvent data."""
        from handler_protocol import HandlerEvent

        event_data = {"input": {"key1": "value1", "key2": "value2"}}
        event = HandlerEvent(**event_data)

        # Dict-style access on input
        assert event.input["key1"] == "value1"
        assert event.input.get("key2") == "value2"
        assert event.input.get("missing", "default") == "default"

        # Iteration
        assert list(event.input.keys()) == ["key1", "key2"]
        assert "key1" in event.input
