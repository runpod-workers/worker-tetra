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

# Size Conversion Constants
BYTES_PER_MB = 1024 * 1024
"""Number of bytes in a megabyte."""

MB_SIZE_THRESHOLD = 1 * BYTES_PER_MB
"""Minimum file size threshold for considering acceleration (1MB)."""

# HuggingFace Model Patterns
LARGE_HF_MODEL_PATTERNS = [
    "albert",
    "bart",
    "bert",
    "codegen",
    "diffusion",
    "distilbert",
    "falcon",
    "gpt",
    "hubert",
    "llama",
    "mistral",
    "mpt",
    "pegasus",
    "roberta",
    "santacoder",
    "stable-diffusion",
    "t5",
    "vae",
    "wav2vec",
    "whisper",
    "xlm",
    "xlnet",
]
"""List of HuggingFace model patterns that benefit from download acceleration."""

# System Package Acceleration with Nala
LARGE_SYSTEM_PACKAGES = [
    "build-essential",
    "cmake",
    "cuda-toolkit",
    "curl",
    "g++",
    "gcc",
    "git",
    "libssl-dev",
    "nvidia-cuda-dev",
    "python3-dev",
    "wget",
]
"""List of system packages that benefit from nala's accelerated installation."""

NALA_CHECK_CMD = ["which", "nala"]
"""Command to check if nala is available."""

# Logging Configuration
LOG_FORMAT = "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
"""Standard log format string used across the application."""
