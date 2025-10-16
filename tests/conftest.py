import pytest
import base64
import cloudpickle
from unittest.mock import MagicMock
from live_serverless.remote_execution import FunctionRequest
from live_serverless.remote_executor import RemoteExecutor


@pytest.fixture
def sample_function_code():
    """Simple test function code."""
    return """
def hello_world():
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    logger.info("hello from the log")
    print("going to say hello")
    return "hello world"
"""


@pytest.fixture
def sample_function_with_args():
    """Test function that takes arguments."""
    return """
def add_numbers(a, b):
    print(f"Adding {a} + {b}")
    return a + b
"""


@pytest.fixture
def sample_function_with_error():
    """Test function that raises an error."""
    return """
def error_function():
    raise ValueError("Test error")
"""


@pytest.fixture
def mock_subprocess():
    """Mock subprocess for dependency installation tests."""
    mock = MagicMock()
    mock.returncode = 0
    mock.communicate.return_value = (b"success output", b"")
    return mock


@pytest.fixture
def function_request_basic(sample_function_code):
    """Basic function request fixture."""
    return FunctionRequest(
        function_name="hello_world",
        function_code=sample_function_code,
        args=[],
        kwargs={},
    )


@pytest.fixture
def function_request_with_args(sample_function_with_args):
    """Function request with arguments."""
    args = [
        base64.b64encode(cloudpickle.dumps(5)).decode("utf-8"),
        base64.b64encode(cloudpickle.dumps(3)).decode("utf-8"),
    ]

    return FunctionRequest(
        function_name="add_numbers",
        function_code=sample_function_with_args,
        args=args,
        kwargs={},
    )


@pytest.fixture
def function_request_with_dependencies():
    """Function request with Python dependencies."""
    return FunctionRequest(
        function_name="hello_world",
        function_code="def hello_world(): import requests; return 'hello'",
        args=[],
        kwargs={},
        dependencies=["requests"],
    )


@pytest.fixture
def function_request_with_system_deps():
    """Function request with system dependencies."""
    return FunctionRequest(
        function_name="hello_world",
        function_code="def hello_world(): return 'hello'",
        args=[],
        kwargs={},
        system_dependencies=["curl", "wget"],
    )


@pytest.fixture
def remote_executor():
    """RemoteExecutor instance for testing."""
    return RemoteExecutor()


@pytest.fixture
def mock_runpod_event():
    """Mock RunPod event structure."""
    return {
        "input": {
            "function_name": "hello_world",
            "function_code": "def hello_world(): return 'hello world'",
            "args": [],
            "kwargs": {},
        }
    }
