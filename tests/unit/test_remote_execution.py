import pytest
import base64
import cloudpickle
from pydantic import ValidationError
from live_serverless.remote_execution import FunctionRequest, FunctionResponse


class TestFunctionRequest:
    """Test cases for FunctionRequest model."""

    def test_function_request_basic(self):
        """Test basic FunctionRequest creation."""
        request = FunctionRequest(
            function_name="test_func", function_code="def test_func(): return 'test'"
        )

        assert request.function_name == "test_func"
        assert request.function_code == "def test_func(): return 'test'"
        assert request.args == []
        assert request.kwargs == {}
        assert request.dependencies is None
        assert request.system_dependencies is None

    def test_function_request_with_args(self):
        """Test FunctionRequest with serialized arguments."""
        arg1 = base64.b64encode(cloudpickle.dumps(42)).decode("utf-8")
        arg2 = base64.b64encode(cloudpickle.dumps("hello")).decode("utf-8")

        request = FunctionRequest(
            function_name="test_func",
            function_code="def test_func(a, b): return a + len(b)",
            args=[arg1, arg2],
        )

        assert len(request.args) == 2
        assert cloudpickle.loads(base64.b64decode(request.args[0])) == 42
        assert cloudpickle.loads(base64.b64decode(request.args[1])) == "hello"

    def test_function_request_with_kwargs(self):
        """Test FunctionRequest with serialized keyword arguments."""
        kwarg_value = base64.b64encode(cloudpickle.dumps({"nested": "value"})).decode(
            "utf-8"
        )

        request = FunctionRequest(
            function_name="test_func",
            function_code="def test_func(**kwargs): return kwargs",
            kwargs={"data": kwarg_value},
        )

        deserialized_kwarg = cloudpickle.loads(base64.b64decode(request.kwargs["data"]))
        assert deserialized_kwarg == {"nested": "value"}

    def test_function_request_with_dependencies(self):
        """Test FunctionRequest with Python dependencies."""
        request = FunctionRequest(
            function_name="test_func",
            function_code="def test_func(): import requests; return 'ok'",
            dependencies=["requests", "numpy>=1.20.0"],
        )

        assert request.dependencies == ["requests", "numpy>=1.20.0"]

    def test_function_request_with_system_dependencies(self):
        """Test FunctionRequest with system dependencies."""
        request = FunctionRequest(
            function_name="test_func",
            function_code="def test_func(): return 'ok'",
            system_dependencies=["curl", "wget", "git"],
        )

        assert request.system_dependencies == ["curl", "wget", "git"]

    def test_function_request_missing_required_fields(self):
        """Test FunctionRequest validation with missing required fields for function execution."""
        # Should fail when execution_type is "function" (default) but function_name/code missing
        with pytest.raises(ValidationError) as exc_info:
            FunctionRequest()

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert "function_name is required when execution_type is" in str(
            errors[0]["ctx"]["error"]
        )

        # Should also fail if only function_name is provided
        with pytest.raises(ValidationError) as exc_info:
            FunctionRequest(function_name="test_func")

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert "function_code is required when execution_type is" in str(
            errors[0]["ctx"]["error"]
        )

    def test_function_request_invalid_types(self):
        """Test FunctionRequest validation with invalid field types."""
        with pytest.raises(ValidationError):
            FunctionRequest(
                function_name=123,  # Should be string
                function_code="def test(): pass",
            )

        with pytest.raises(ValidationError):
            FunctionRequest(
                function_name="test",
                function_code="def test(): pass",
                args="not_a_list",  # Should be list
            )

    def test_function_request_serialization(self):
        """Test FunctionRequest model serialization."""
        request = FunctionRequest(
            function_name="test_func",
            function_code="def test_func(): return 'test'",
            dependencies=["requests"],
        )

        # Test model_dump
        data = request.model_dump()
        assert data["function_name"] == "test_func"
        assert data["dependencies"] == ["requests"]

        # Test round-trip
        recreated = FunctionRequest(**data)
        assert recreated.function_name == request.function_name
        assert recreated.dependencies == request.dependencies


class TestFunctionResponse:
    """Test cases for FunctionResponse model."""

    def test_function_response_success(self):
        """Test successful FunctionResponse creation."""
        result = base64.b64encode(cloudpickle.dumps("success")).decode("utf-8")

        response = FunctionResponse(
            success=True, result=result, stdout="Function executed successfully"
        )

        assert response.success is True
        assert cloudpickle.loads(base64.b64decode(response.result)) == "success"
        assert response.stdout == "Function executed successfully"
        assert response.error is None

    def test_function_response_error(self):
        """Test error FunctionResponse creation."""
        response = FunctionResponse(
            success=False,
            error="ValueError: Something went wrong",
            stdout="Some output before error",
        )

        assert response.success is False
        assert response.error == "ValueError: Something went wrong"
        assert response.stdout == "Some output before error"
        assert response.result is None

    def test_function_response_minimal(self):
        """Test minimal FunctionResponse creation."""
        response = FunctionResponse(success=True)

        assert response.success is True
        assert response.result is None
        assert response.error is None
        assert response.stdout is None

    def test_function_response_missing_success(self):
        """Test FunctionResponse validation without success field."""
        with pytest.raises(ValidationError) as exc_info:
            FunctionResponse()

        error_fields = [error["loc"][0] for error in exc_info.value.errors()]
        assert "success" in error_fields

    def test_function_response_invalid_success_type(self):
        """Test FunctionResponse validation with invalid success type."""
        with pytest.raises(ValidationError):
            FunctionResponse(success={"not": "boolean"})  # Should be boolean

    def test_function_response_serialization(self):
        """Test FunctionResponse model serialization."""
        response = FunctionResponse(
            success=True, result="base64encodedresult", stdout="output"
        )

        # Test model_dump
        data = response.model_dump()
        assert data["success"] is True
        assert data["result"] == "base64encodedresult"
        assert data["stdout"] == "output"

        # Test round-trip
        recreated = FunctionResponse(**data)
        assert recreated.success == response.success
        assert recreated.result == response.result

    def test_function_response_complex_result(self):
        """Test FunctionResponse with complex serialized result."""
        complex_data = {
            "numbers": [1, 2, 3],
            "nested": {"key": "value"},
            "boolean": True,
        }

        serialized_result = base64.b64encode(cloudpickle.dumps(complex_data)).decode(
            "utf-8"
        )

        response = FunctionResponse(success=True, result=serialized_result)

        deserialized = cloudpickle.loads(base64.b64decode(response.result))
        assert deserialized == complex_data

    def test_function_response_empty_result(self):
        """Test FunctionResponse with None result."""
        response = FunctionResponse(
            success=True,
            result=base64.b64encode(cloudpickle.dumps(None)).decode("utf-8"),
        )

        deserialized = cloudpickle.loads(base64.b64decode(response.result))
        assert deserialized is None

    def test_function_response_with_multiline_error(self):
        """Test FunctionResponse with multiline error message."""
        error_msg = """Traceback (most recent call last):
  File "test.py", line 1, in <module>
    raise ValueError("Test error")
ValueError: Test error"""

        response = FunctionResponse(success=False, error=error_msg)

        assert response.error == error_msg
        assert "Traceback" in response.error
        assert "ValueError" in response.error
