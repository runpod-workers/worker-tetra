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
