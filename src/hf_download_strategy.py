"""
HuggingFace download strategy interface.

Provides pluggable download strategies for HuggingFace models to allow
switching between different acceleration methods and benchmarking performance.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any
from remote_execution import FunctionResponse


class HFDownloadStrategy(ABC):
    """Abstract base class for HuggingFace download strategies."""

    @abstractmethod
    def download_model(self, model_id: str, revision: str = "main") -> FunctionResponse:
        """
        Download a HuggingFace model.

        Args:
            model_id: HuggingFace model identifier
            revision: Model revision/branch

        Returns:
            FunctionResponse with download results
        """
        pass

    @abstractmethod
    def is_model_cached(self, model_id: str, revision: str = "main") -> bool:
        """
        Check if model is already cached.

        Args:
            model_id: HuggingFace model identifier
            revision: Model revision/branch

        Returns:
            True if model appears to be cached
        """
        pass

    @abstractmethod
    def get_cache_info(self, model_id: str) -> Dict[str, Any]:
        """
        Get cache information for a model.

        Args:
            model_id: HuggingFace model identifier

        Returns:
            Dictionary with cache information
        """
        pass

    @abstractmethod
    def should_accelerate(self, model_id: str) -> bool:
        """
        Determine if model should use acceleration.

        Args:
            model_id: HuggingFace model identifier

        Returns:
            True if acceleration should be used
        """
        pass

    @abstractmethod
    def clear_model_cache(self, model_id: str) -> FunctionResponse:
        """
        Clear cache for a specific model.

        Args:
            model_id: HuggingFace model identifier

        Returns:
            FunctionResponse with clearing result
        """
        pass
