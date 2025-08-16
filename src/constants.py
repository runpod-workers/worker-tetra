# RunPod Volume Paths
RUNPOD_VOLUME_PATH = "/runpod-volume"
"""Path to the RunPod persistent volume mount point."""

DEFAULT_WORKSPACE_PATH = "/app"
"""Default workspace path when no persistent volume is available."""

# Directory Names
VENV_DIR_NAME = ".venv"
"""Name of the virtual environment directory."""

UV_CACHE_DIR_NAME = ".uv-cache"
"""Name of the UV package cache directory."""

HF_CACHE_DIR_NAME = ".hf-cache"
"""Name of the Hugging Face cache directory."""

WORKSPACE_LOCK_FILE = ".initialization.lock"
"""Name of the workspace initialization lock file."""

RUNTIMES_DIR_NAME = "runtimes"
"""Name of the runtimes directory containing per-endpoint workspaces."""

# Download Acceleration Settings
DEFAULT_DOWNLOAD_CONNECTIONS = 8
"""Default number of parallel connections for accelerated downloads."""

MIN_SIZE_FOR_ACCELERATION_MB = 10
"""Minimum file size in MB to trigger download acceleration."""

MAX_DOWNLOAD_CONNECTIONS = 16
"""Maximum number of parallel connections for downloads."""

DOWNLOAD_TIMEOUT_SECONDS = 600
"""Default timeout for download operations in seconds."""

DOWNLOAD_PROGRESS_UPDATE_INTERVAL = 1.0
"""Interval in seconds for download progress updates."""
