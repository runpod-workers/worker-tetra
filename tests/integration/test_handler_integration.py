import pytest
from handler import handler


class TestHandlerIntegration:
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
