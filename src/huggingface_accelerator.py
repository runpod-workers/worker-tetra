"""
HuggingFace model download acceleration.

This module provides accelerated downloads for HuggingFace models and datasets,
integrating with the existing volume workspace caching system.
"""

import os
import requests
import logging
from typing import Dict, List, Any
from pathlib import Path

from remote_execution import FunctionResponse
from download_accelerator import DownloadAccelerator


class HuggingFaceAccelerator:
    """Accelerated downloads for HuggingFace models and files."""

    def __init__(self, workspace_manager):
        self.workspace_manager = workspace_manager
        self.logger = logging.getLogger(__name__)
        self.download_accelerator = DownloadAccelerator(workspace_manager)

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
        Get list of files for a HuggingFace model using the Hub API.

        Args:
            model_id: HuggingFace model identifier (e.g., 'gpt2', 'microsoft/DialoGPT-medium')
            revision: Model revision/branch (default: 'main')

        Returns:
            List of file information dictionaries
        """
        api_url = f"https://huggingface.co/api/models/{model_id}/tree/{revision}"

        headers = {}
        hf_token = os.environ.get("HF_TOKEN")
        if hf_token:
            headers["Authorization"] = f"Bearer {hf_token}"

        try:
            response = requests.get(api_url, headers=headers, timeout=30)
            response.raise_for_status()

            files = []
            for item in response.json():
                if item["type"] == "file":
                    files.append(
                        {
                            "path": item["path"],
                            "size": item.get("size", 0),
                            "url": f"https://huggingface.co/{model_id}/resolve/{revision}/{item['path']}",
                        }
                    )

            return files

        except Exception as e:
            self.logger.warning(f"Could not fetch model file list for {model_id}: {e}")
            return []

    def should_accelerate_model(self, model_id: str) -> bool:
        """
        Determine if model downloads should be accelerated.

        Args:
            model_id: HuggingFace model identifier

        Returns:
            True if acceleration should be used
        """
        if not self.download_accelerator.aria2_downloader.aria2c_available:
            return False

        # Always accelerate known model repositories
        large_model_patterns = [
            "gpt",
            "bert",
            "roberta",
            "distilbert",
            "albert",
            "xlnet",
            "xlm",
            "t5",
            "bart",
            "pegasus",
            "stable-diffusion",
            "diffusion",
            "vae",
            "whisper",
            "wav2vec",
            "hubert",
            "llama",
            "mistral",
            "falcon",
            "mpt",
            "codegen",
            "santacoder",
        ]

        model_lower = model_id.lower()
        return any(pattern in model_lower for pattern in large_model_patterns)

    def accelerate_model_download(
        self, model_id: str, revision: str = "main"
    ) -> FunctionResponse:
        """
        Pre-download HuggingFace model files using acceleration.

        This method downloads model files to the cache before transformers tries to access them,
        using aria2c for faster parallel downloads.

        Args:
            model_id: HuggingFace model identifier
            revision: Model revision/branch

        Returns:
            FunctionResponse with download results
        """
        if not self.should_accelerate_model(model_id):
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
        large_files = [f for f in files if f["size"] > 1024 * 1024]  # > 1MB

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
                file_size_mb = file_info["size"] / (1024 * 1024)
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
                f"({total_size / (1024 * 1024):.1f}MB) for model {model_id}",
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
            "cache_size_mb": total_size / (1024 * 1024),
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
