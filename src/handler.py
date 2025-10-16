import runpod
from logger import setup_logging
from live_serverless import handler


# Initialize logging configuration
setup_logging()


# Start the RunPod serverless handler
if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
