"""
HuggingFace model download acceleration.

This module provides accelerated downloads for HuggingFace models and datasets,
integrating with the existing volume workspace caching system using pluggable
download strategies.
"""

import logging
from typing import Dict, List, Any

from huggingface_hub import HfApi
from remote_execution import FunctionResponse
from hf_strategy_factory import HFStrategyFactory
from hf_download_strategy import HFDownloadStrategy


class HuggingFaceAccelerator:
    """Accelerated downloads for HuggingFace models and files using pluggable strategies."""

    def __init__(self, workspace_manager):
        self.workspace_manager = workspace_manager
        self.logger = logging.getLogger(__name__)
        self.api = HfApi()

        # Create the configured download strategy
        self.strategy: HFDownloadStrategy = HFStrategyFactory.create_strategy(
            workspace_manager
        )

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
        Determine if model should be pre-cached using the configured strategy.

        Args:
            model_id: HuggingFace model identifier

        Returns:
            True if model should be pre-cached
        """
        return self.strategy.should_accelerate(model_id)

    def accelerate_model_download(
        self, model_id: str, revision: str = "main"
    ) -> FunctionResponse:
        """
        Pre-download HuggingFace model using the configured download strategy.

        Args:
            model_id: HuggingFace model identifier
            revision: Model revision/branch

        Returns:
            FunctionResponse with download results
        """
        return self.strategy.download_model(model_id, revision)

    def is_model_cached(self, model_id: str, revision: str = "main") -> bool:
        """
        Check if model is already cached using the configured strategy.

        Args:
            model_id: HuggingFace model identifier
            revision: Model revision/branch

        Returns:
            True if model appears to be cached
        """
        return self.strategy.is_model_cached(model_id, revision)

    def get_cache_info(self, model_id: str) -> Dict[str, Any]:
        """
        Get cache information for a model using the configured strategy.

        Args:
            model_id: HuggingFace model identifier

        Returns:
            Dictionary with cache information
        """
        return self.strategy.get_cache_info(model_id)

    def clear_model_cache(self, model_id: str) -> FunctionResponse:
        """
        Clear cache for a specific model using the configured strategy.

        Args:
            model_id: HuggingFace model identifier

        Returns:
            FunctionResponse with clearing result
        """
        return self.strategy.clear_model_cache(model_id)

    def get_strategy_info(self) -> Dict[str, Any]:
        """
        Get information about the current download strategy.

        Returns:
            Dictionary with strategy information
        """
        strategy_info = HFStrategyFactory.get_strategy_info()
        strategy_info["strategy_instance"] = type(self.strategy).__name__
        return strategy_info

    def set_strategy(self, strategy: str) -> None:
        """
        Change the download strategy (creates new strategy instance).

        Args:
            strategy: Strategy name ("tetra" or "native")
        """
        HFStrategyFactory.set_strategy(strategy)
        self.strategy = HFStrategyFactory.create_strategy(self.workspace_manager)
        self.logger.info(f"Switched to {strategy} download strategy")
