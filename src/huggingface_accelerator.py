"""
HuggingFace model download acceleration.

This module provides accelerated downloads for HuggingFace models and datasets,
integrating with the existing volume workspace caching system.
"""

import logging
from typing import Dict, List, Any

from huggingface_hub import HfApi, snapshot_download
from remote_execution import FunctionResponse
from constants import LARGE_HF_MODEL_PATTERNS, BYTES_PER_MB


class HuggingFaceAccelerator:
    """Accelerated downloads for HuggingFace models and files."""

    def __init__(self, workspace_manager):
        self.workspace_manager = workspace_manager
        self.logger = logging.getLogger(__name__)
        self.api = HfApi()

        # HF will automatically use HF_HOME environment variable set by workspace_manager
        # No need to manually manage cache directories

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

    def should_accelerate_model(self, model_id: str) -> bool:
        """
        Determine if model should be pre-cached.
        HF Hub automatically uses hf_transfer when available.

        Args:
            model_id: HuggingFace model identifier

        Returns:
            True if model should be pre-cached
        """
        model_lower = model_id.lower()
        return any(pattern in model_lower for pattern in LARGE_HF_MODEL_PATTERNS)

    def accelerate_model_download(
        self, model_id: str, revision: str = "main"
    ) -> FunctionResponse:
        """
        Pre-download HuggingFace model using HF Hub's native caching.

        This method downloads the complete model snapshot to HF's standard cache
        location, leveraging hf_transfer when available.

        Args:
            model_id: HuggingFace model identifier
            revision: Model revision/branch

        Returns:
            FunctionResponse with download results
        """
        if not self.should_accelerate_model(model_id):
            return FunctionResponse(
                success=True, stdout=f"Model {model_id} does not require pre-caching"
            )

        self.logger.info(f"Pre-caching model: {model_id}")

        try:
            # Use HF Hub's native snapshot download with acceleration
            snapshot_path = snapshot_download(
                repo_id=model_id,
                revision=revision,
                # HF automatically uses HF_HOME/HF_HUB_CACHE from environment
                # and applies hf_transfer acceleration when available
            )

            return FunctionResponse(
                success=True,
                stdout=f"Successfully pre-cached model {model_id} to {snapshot_path}",
            )

        except Exception as e:
            return FunctionResponse(
                success=False,
                error=f"Failed to pre-cache model {model_id}: {str(e)}",
            )

    def is_model_cached(self, model_id: str, revision: str = "main") -> bool:
        """
        Check if model is already cached using HF Hub's cache utilities.

        Args:
            model_id: HuggingFace model identifier
            revision: Model revision/branch

        Returns:
            True if model appears to be cached
        """
        try:
            from huggingface_hub import try_to_load_from_cache

            # Check for common model files that indicate a cached model
            key_files = ["config.json", "pytorch_model.bin", "model.safetensors"]

            for filename in key_files:
                cached_path = try_to_load_from_cache(
                    repo_id=model_id, filename=filename, revision=revision
                )
                if cached_path is not None:  # Found cached file
                    return True

            return False
        except Exception:
            return False

    def get_cache_info(self, model_id: str) -> Dict[str, Any]:
        """
        Get cache information for a model using HF Hub utilities.

        Args:
            model_id: HuggingFace model identifier

        Returns:
            Dictionary with cache information
        """
        try:
            from huggingface_hub import scan_cache_dir

            cache_info = scan_cache_dir()

            # Find our specific model in the cache
            for repo in cache_info.repos:
                if repo.repo_id == model_id:
                    return {
                        "cached": True,
                        "cache_size_mb": repo.size_on_disk / BYTES_PER_MB,
                        "file_count": len(list(repo.revisions)[0].files)
                        if repo.revisions
                        else 0,
                        "cache_path": str(repo.repo_path),
                    }

            return {"cached": False, "cache_size_mb": 0, "file_count": 0}

        except Exception:
            return {"cached": False, "cache_size_mb": 0, "file_count": 0}

    def clear_model_cache(self, model_id: str) -> FunctionResponse:
        """
        Clear cache for a specific model using HF Hub utilities.

        Args:
            model_id: HuggingFace model identifier

        Returns:
            FunctionResponse with clearing result
        """
        try:
            from huggingface_hub import scan_cache_dir

            cache_info = scan_cache_dir()

            # Find and delete our specific model
            for repo in cache_info.repos:
                if repo.repo_id == model_id:
                    delete_strategy = cache_info.delete_revisions(repo.repo_id)
                    delete_strategy.execute()

                    return FunctionResponse(
                        success=True, stdout=f"Cleared cache for model {model_id}"
                    )

            return FunctionResponse(
                success=True, stdout=f"No cache found for model {model_id}"
            )

        except Exception as e:
            return FunctionResponse(
                success=False, error=f"Failed to clear cache for {model_id}: {str(e)}"
            )
