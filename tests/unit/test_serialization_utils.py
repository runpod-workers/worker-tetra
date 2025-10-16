"""Tests for SerializationUtils component."""

import base64
import cloudpickle
from live_serverless.serialization_utils import SerializationUtils


class TestSerializationUtils:
    """Test serialization and deserialization utilities."""

    def test_serialize_result_simple(self):
        """Test serializing simple result."""
        result = "hello world"
        serialized = SerializationUtils.serialize_result(result)

        # Should be base64 encoded cloudpickle
        deserialized = cloudpickle.loads(base64.b64decode(serialized))
        assert deserialized == "hello world"

    def test_serialize_result_complex(self):
        """Test serializing complex data structures."""
        result = {
            "numbers": [1, 2, 3],
            "nested": {"key": "value"},
            "boolean": True,
        }
        serialized = SerializationUtils.serialize_result(result)

        deserialized = cloudpickle.loads(base64.b64decode(serialized))
        assert deserialized == result

    def test_serialize_result_none(self):
        """Test serializing None result."""
        result = None
        serialized = SerializationUtils.serialize_result(result)

        deserialized = cloudpickle.loads(base64.b64decode(serialized))
        assert deserialized is None

    def test_deserialize_args_simple(self):
        """Test deserializing simple arguments."""
        args = [42, "hello", True]
        encoded_args = [
            base64.b64encode(cloudpickle.dumps(arg)).decode("utf-8") for arg in args
        ]

        deserialized = SerializationUtils.deserialize_args(encoded_args)
        assert deserialized == args

    def test_deserialize_args_empty(self):
        """Test deserializing empty argument list."""
        deserialized = SerializationUtils.deserialize_args([])
        assert deserialized == []

    def test_deserialize_args_complex(self):
        """Test deserializing complex arguments."""
        args = [{"nested": {"data": [1, 2, 3]}}, [1, 2, 3], {"key": "value"}]
        encoded_args = [
            base64.b64encode(cloudpickle.dumps(arg)).decode("utf-8") for arg in args
        ]

        deserialized = SerializationUtils.deserialize_args(encoded_args)
        assert deserialized == args

    def test_deserialize_kwargs_simple(self):
        """Test deserializing simple keyword arguments."""
        kwargs = {"name": "Alice", "age": 30, "active": True}
        encoded_kwargs = {
            k: base64.b64encode(cloudpickle.dumps(v)).decode("utf-8")
            for k, v in kwargs.items()
        }

        deserialized = SerializationUtils.deserialize_kwargs(encoded_kwargs)
        assert deserialized == kwargs

    def test_deserialize_kwargs_empty(self):
        """Test deserializing empty keyword arguments."""
        deserialized = SerializationUtils.deserialize_kwargs({})
        assert deserialized == {}

    def test_deserialize_kwargs_complex(self):
        """Test deserializing complex keyword arguments."""
        kwargs = {
            "data": {"nested": [1, 2, 3]},
            "config": {"enabled": True, "settings": {"timeout": 30}},
            "items": [{"id": 1}, {"id": 2}],
        }
        encoded_kwargs = {
            k: base64.b64encode(cloudpickle.dumps(v)).decode("utf-8")
            for k, v in kwargs.items()
        }

        deserialized = SerializationUtils.deserialize_kwargs(encoded_kwargs)
        assert deserialized == kwargs

    def test_round_trip_serialization(self):
        """Test complete round-trip serialization/deserialization."""
        # Original data
        result = {"message": "success", "data": [1, 2, 3], "count": 42}
        args = [100, "test", {"nested": True}]
        kwargs = {"timeout": 30, "config": {"debug": False}}

        # Serialize
        serialized_result = SerializationUtils.serialize_result(result)
        encoded_args = [
            base64.b64encode(cloudpickle.dumps(arg)).decode("utf-8") for arg in args
        ]
        encoded_kwargs = {
            k: base64.b64encode(cloudpickle.dumps(v)).decode("utf-8")
            for k, v in kwargs.items()
        }

        # Deserialize
        deserialized_result = cloudpickle.loads(base64.b64decode(serialized_result))
        deserialized_args = SerializationUtils.deserialize_args(encoded_args)
        deserialized_kwargs = SerializationUtils.deserialize_kwargs(encoded_kwargs)

        # Verify
        assert deserialized_result == result
        assert deserialized_args == args
        assert deserialized_kwargs == kwargs
