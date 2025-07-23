import base64
import cloudpickle
from handler import RemoteExecutor
from remote_execution import FunctionRequest


class TestRemoteExecutor:
    def test_execute_simple_function(self):
        """Test basic function execution"""
        executor = RemoteExecutor()

        # Simple function that returns a value
        function_code = "def test_func():\n    return 'hello world'"

        request = FunctionRequest(
            function_name="test_func", function_code=function_code, args=[], kwargs={}
        )

        response = executor.execute(request)

        assert response.success is True
        assert response.error is None

        # Deserialize the result
        result = cloudpickle.loads(base64.b64decode(response.result))
        assert result == "hello world"
