# Logger Configuration
NAMESPACE = "tetra"
"""Application logger namespace for all components."""

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

# Cache Sync Configuration
CACHE_DIR = "/root/.cache"
"""Directory containing package and model caches."""

# Production Code Configuration
WORKERS_CODE_DIR = "/app/workers"
"""Directory where production worker code is extracted from tarball."""

VOLUME_CACHE_PATH = "/runpod-volume/.cache"
"""Network volume path for cache tarball storage."""
