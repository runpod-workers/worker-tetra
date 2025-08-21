"""
Tetra HuggingFace downloader strategy.

This strategy implements a custom acceleration logic with
manual file enumeration and file-by-file downloads using
hf_transfer and custom acceleration methods.
"""

import logging
from typing import Dict, List, Any
from pathlib import Path

from huggingface_hub import HfApi
from remote_execution import FunctionResponse
from hf_download_strategy import HFDownloadStrategy
from download_accelerator import DownloadAccelerator
from constants import LARGE_HF_MODEL_PATTERNS, BYTES_PER_MB, MB_SIZE_THRESHOLD


class TetraHFDownloader(HFDownloadStrategy):
    """Custom Tetra HuggingFace downloader with manual acceleration logic."""

    def __init__(self, workspace_manager):
        self.workspace_manager = workspace_manager
        self.logger = logging.getLogger(__name__)
        self.download_accelerator = DownloadAccelerator(workspace_manager)
        self.api = HfApi()

        # Use workspace manager's HF cache if available
        if workspace_manager and workspace_manager.hf_cache_path:
            self.cache_dir = Path(workspace_manager.hf_cache_path)
        else:
            self.cache_dir = Path.home() / ".cache" / "huggingface"

        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_model_files(
        self, model_id: str, revision: str = "main"
    ) -> List[Dict[str, Any]]:
        """
        Get list of files for a HuggingFace model using the HF Hub API.

        Args:
            model_id: HuggingFace model identifier (e.g., 'gpt2', 'microsoft/DialoGPT-medium')
            revision: Model revision/branch (default: 'main')

        Returns:
            List of file information dictionaries
        """
        try:
            # Use HF Hub's native API instead of manual requests
            repo_info = self.api.repo_info(model_id, revision=revision)

            files = []
            if repo_info.siblings:
                for sibling in repo_info.siblings:
                    if sibling.rfilename:  # Only include actual files
                        files.append(
                            {
                                "path": sibling.rfilename,
                                "size": getattr(sibling, "size", 0) or 0,
                                "url": f"https://huggingface.co/{model_id}/resolve/{revision}/{sibling.rfilename}",
                            }
                        )

            return files

        except Exception as e:
            self.logger.warning(f"Could not fetch model file list for {model_id}: {e}")
            return []

    def should_accelerate(self, model_id: str) -> bool:
        """
        Determine if model downloads should be accelerated.

        Args:
            model_id: HuggingFace model identifier

        Returns:
            True if acceleration should be used
        """
        # Check if hf_transfer is available
        has_hf_transfer = (
            self.download_accelerator.hf_transfer_downloader.hf_transfer_available
        )

        if not has_hf_transfer:
            return False

        model_lower = model_id.lower()
        return any(pattern in model_lower for pattern in LARGE_HF_MODEL_PATTERNS)

    def download_model(self, model_id: str, revision: str = "main") -> FunctionResponse:
        """
        Download HuggingFace model files using Tetra's custom acceleration.

        This method downloads model files to the cache before transformers tries to access them,
        using hf_transfer or custom acceleration for optimized downloads.

        Args:
            model_id: HuggingFace model identifier
            revision: Model revision/branch

        Returns:
            FunctionResponse with download results
        """
        if not self.should_accelerate(model_id):
            return FunctionResponse(
                success=True, stdout=f"Model {model_id} does not require acceleration"
            )

        self.logger.info(f"Accelerating model download: {model_id}")

        # Get model file list
        files = self.get_model_files(model_id, revision)
        if not files:
            return FunctionResponse(
                success=False, error=f"Could not get file list for model {model_id}"
            )

        # Filter for main model files (ignore small config files)
        large_files = [f for f in files if f["size"] > MB_SIZE_THRESHOLD]

        if not large_files:
            return FunctionResponse(
                success=True, stdout=f"No large files found for model {model_id}"
            )

        self.logger.info(
            f"Found {len(large_files)} large files to download for {model_id}"
        )

        # Create model-specific cache directory
        model_cache_dir = self.cache_dir / "transformers" / model_id.replace("/", "--")
        model_cache_dir.mkdir(parents=True, exist_ok=True)

        successful_downloads = 0
        total_size = sum(f["size"] for f in large_files)

        for file_info in large_files:
            file_path = model_cache_dir / file_info["path"]
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # Skip if file already exists and is correct size
            if file_path.exists() and file_path.stat().st_size == file_info["size"]:
                self.logger.info(f"✓ {file_info['path']} (cached)")
                successful_downloads += 1
                continue

            try:
                file_size_mb = file_info["size"] / BYTES_PER_MB
                self.logger.info(
                    f"Downloading {file_info['path']} ({file_size_mb:.1f}MB)..."
                )

                # Use download accelerator
                result = self.download_accelerator.download_with_fallback(
                    file_info["url"],
                    str(file_path),
                    estimated_size_mb=file_size_mb,
                    show_progress=True,
                )

                if result.success:
                    successful_downloads += 1
                    self.logger.info(f"✓ {file_info['path']} downloaded successfully")
                else:
                    self.logger.error(f"✗ {file_info['path']} failed: {result.error}")

            except Exception as e:
                self.logger.error(
                    f"✗ {file_info['path']} failed with exception: {str(e)}"
                )

        success = successful_downloads == len(large_files)

        if success:
            return FunctionResponse(
                success=True,
                stdout=f"Successfully pre-downloaded {successful_downloads} files "
                f"({total_size / BYTES_PER_MB:.1f}MB) for model {model_id}",
            )
        else:
            return FunctionResponse(
                success=False,
                error=f"Failed to download {len(large_files) - successful_downloads} files for {model_id}",
                stdout=f"Downloaded {successful_downloads}/{len(large_files)} files",
            )

    def is_model_cached(self, model_id: str, revision: str = "main") -> bool:
        """
        Check if model is already cached.

        Args:
            model_id: HuggingFace model identifier
            revision: Model revision/branch

        Returns:
            True if model appears to be cached
        """
        model_cache_dir = self.cache_dir / "transformers" / model_id.replace("/", "--")

        if not model_cache_dir.exists():
            return False

        # Check if there are any model files
        model_files = list(model_cache_dir.glob("**/*.bin")) + list(
            model_cache_dir.glob("**/*.safetensors")
        )
        return len(model_files) > 0

    def get_cache_info(self, model_id: str) -> Dict[str, Any]:
        """
        Get cache information for a model.

        Args:
            model_id: HuggingFace model identifier

        Returns:
            Dictionary with cache information
        """
        model_cache_dir = self.cache_dir / "transformers" / model_id.replace("/", "--")

        if not model_cache_dir.exists():
            return {"cached": False, "cache_size_mb": 0, "file_count": 0}

        total_size = 0
        file_count = 0

        for file_path in model_cache_dir.rglob("*"):
            if file_path.is_file():
                total_size += file_path.stat().st_size
                file_count += 1

        return {
            "cached": file_count > 0,
            "cache_size_mb": total_size / BYTES_PER_MB,
            "file_count": file_count,
            "cache_path": str(model_cache_dir),
        }

    def clear_model_cache(self, model_id: str) -> FunctionResponse:
        """
        Clear cache for a specific model.

        Args:
            model_id: HuggingFace model identifier

        Returns:
            FunctionResponse with clearing result
        """
        model_cache_dir = self.cache_dir / "transformers" / model_id.replace("/", "--")

        if not model_cache_dir.exists():
            return FunctionResponse(
                success=True, stdout=f"No cache found for model {model_id}"
            )

        try:
            import shutil

            shutil.rmtree(model_cache_dir)

            return FunctionResponse(
                success=True, stdout=f"Cleared cache for model {model_id}"
            )
        except Exception as e:
            return FunctionResponse(
                success=False, error=f"Failed to clear cache for {model_id}: {str(e)}"
            )
