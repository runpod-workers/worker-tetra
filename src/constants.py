# Logger Configuration
NAMESPACE = "tetra"
"""Application logger namespace for all components."""

# RunPod Volume Paths
RUNPOD_VOLUME_PATH = "/runpod-volume"
"""Path to the RunPod persistent volume mount point."""

DEFAULT_WORKSPACE_PATH = "/app"
"""Default workspace path when no persistent volume is available."""

RUNTIMES_DIR_NAME = "runtimes"
"""Name of the runtimes directory containing per-endpoint workspaces."""

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
