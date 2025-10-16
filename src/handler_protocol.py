"""
Universal handler protocol for RunPod serverless workers.

All handlers (live_serverless, inference, training, etc.) should follow
this protocol to ensure compatibility with the dynamic handler loader.
"""

from typing import Dict, Any, Awaitable, Callable
from pydantic import BaseModel, Field


class HandlerEvent(BaseModel):
    """
    Standard event structure for all RunPod serverless handlers.

    RunPod wraps all inputs in an 'input' field. This model enforces
    that structure while allowing each handler to define its own input schema.

    Example:
        {
            "input": {
                "prompt": "Generate text...",
                "model": "gpt-4"
            }
        }
    """

    input: Dict[str, Any] = Field(description="Handler-specific input data")

    model_config = {"extra": "allow"}  # Allow RunPod metadata fields


# Type alias for standard handler function signature
HandlerFunction = Callable[[HandlerEvent], Awaitable[Dict[str, Any]]]
