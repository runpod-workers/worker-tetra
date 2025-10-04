"""
HuggingFace model download caching.

This module provides cache-ahead downloads for HuggingFace models and datasets.
"""

import os
import asyncio
import logging

from huggingface_hub import snapshot_download, scan_cache_dir
from huggingface_hub.errors import CacheNotFound
from remote_execution import FunctionResponse


class HuggingFaceCacheAhead:
    """Cache-ahead downloads for HuggingFace models and files."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    async def cache_model_download_async(
        self, model_id: str, revision: str = "main"
    ) -> FunctionResponse:
        """
        Async wrapper for pre-downloading HuggingFace models.

        Args:
            model_id: HuggingFace model identifier
            revision: Model revision/branch

        Returns:
            FunctionResponse with download results
        """
        return await asyncio.to_thread(self.cache_model_download, model_id, revision)

    def cache_model_download(
        self, model_id: str, revision: str = "main"
    ) -> FunctionResponse:
        """
        Pre-download HuggingFace model using HF Hub's native caching.

        This method downloads the complete model snapshot to HF's standard cache
        location. HF Hub automatically uses hf_transfer/hf_xet acceleration when
        HF_HUB_ENABLE_HF_TRANSFER=1 is set in the environment.

        Args:
            model_id: HuggingFace model identifier
            revision: Model revision/branch

        Returns:
            FunctionResponse with download results
        """
        try:
            # Check if model is already cached
            cache_hit = self._is_model_cached(model_id, revision)
            if cache_hit:
                self.logger.info(f"Model {model_id} already cached, skipping download")
                return FunctionResponse(
                    success=True,
                    stdout=f"Model {model_id} already cached (cache hit)",
                )

            self.logger.info(f"Started downloading model {model_id}")

            # Get HF authentication token if available
            hf_token = os.environ.get("HF_TOKEN")

            # Use HF Hub's native snapshot download with acceleration
            snapshot_path = snapshot_download(
                repo_id=model_id,
                revision=revision,
                token=hf_token,
                # HF automatically uses HF_HOME/HF_HUB_CACHE from environment
                # and applies hf_transfer acceleration when available
            )

            success_message = f"Successfully cached model {model_id} to {snapshot_path}"
            self.logger.info(success_message)

            return FunctionResponse(
                success=True,
                stdout=success_message,
            )

        except Exception as e:
            return FunctionResponse(
                success=False,
                error=f"Failed to cache-ahead model {model_id}: {str(e)}",
            )

    def _is_model_cached(self, model_id: str, revision: str = "main") -> bool:
        """
        Check if a model is already cached locally.

        Args:
            model_id: HuggingFace model identifier
            revision: Model revision/branch/commit hash

        Returns:
            True if model is cached, False otherwise
        """
        try:
            cache_info = scan_cache_dir()
            for repo in cache_info.repos:
                if repo.repo_id == model_id:
                    # If revision is "main", accept any cached version of the model
                    if revision == "main":
                        return len(repo.revisions) > 0

                    # Check for specific revision by commit hash
                    for rev in repo.revisions:
                        if rev.commit_hash.startswith(revision) or revision.startswith(
                            rev.commit_hash
                        ):
                            return True
            return False
        except CacheNotFound:
            # Cache directory doesn't exist yet - this is expected on first use
            self.logger.debug(
                f"Cache directory not found for {model_id}, will be created on download"
            )
            return False
        except Exception as e:
            self.logger.debug(f"Cache check failed for {model_id}: {e}")
            return False
