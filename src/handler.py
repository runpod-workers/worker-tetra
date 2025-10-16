import os
import importlib
import sys
from typing import Callable, Dict, Any, cast

import runpod


def load_handler() -> Callable[[Dict[str, Any]], Dict[str, Any]]:
    """
    Dynamically load the handler function from the specified module.

    Returns:
        The handler function from the specified module

    Raises:
        ImportError: If the module cannot be imported
        AttributeError: If the module doesn't have a 'handler' function
    """
    handler_module_name = os.environ.get("HANDLER_MODULE", "live_serverless")

    try:
        # Dynamically import the module
        handler_module = importlib.import_module(handler_module_name)

        # Get the handler function
        if not hasattr(handler_module, "handler"):
            raise AttributeError(
                f"Module '{handler_module_name}' does not export a 'handler' function"
            )

        handler_func = getattr(handler_module, "handler")

        if not callable(handler_func):
            raise TypeError(
                f"'handler' in module '{handler_module_name}' is not callable"
            )

        print(f"Loaded handler from module: {handler_module_name}")
        return cast(Callable[[Dict[str, Any]], Dict[str, Any]], handler_func)

    except ImportError as e:
        print(
            f"Error: Failed to import module '{handler_module_name}': {e}",
            file=sys.stderr,
        )
        raise
    except (AttributeError, TypeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        raise


# Start the RunPod serverless handler
if __name__ == "__main__":
    handler = load_handler()
    runpod.serverless.start({"handler": handler})
