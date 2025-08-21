"""
HuggingFace download strategy factory.

Provides configuration system for switching between different HF download strategies
and creating the appropriate downloader instance based on environment variables.
"""

import os
import logging
from typing import Optional, Dict, Any

from hf_download_strategy import HFDownloadStrategy
from hf_downloader_tetra import TetraHFDownloader
from hf_downloader_native import NativeHFDownloader


class HFStrategyFactory:
    """Factory for creating HF download strategy instances."""

    # Environment variable name
    STRATEGY_ENV_VAR = "HF_DOWNLOAD_STRATEGY"

    # Available strategy names
    TETRA_STRATEGY = "tetra"
    NATIVE_STRATEGY = "native"

    # Default strategy
    DEFAULT_STRATEGY = TETRA_STRATEGY

    @classmethod
    def get_available_strategies(cls) -> list[str]:
        """Get list of available strategy names."""
        return [cls.TETRA_STRATEGY, cls.NATIVE_STRATEGY]

    @classmethod
    def get_configured_strategy(cls) -> str:
        """
        Get the configured strategy name from environment variables.

        Returns:
            Strategy name (defaults to native if not configured)
        """
        strategy = os.environ.get(cls.STRATEGY_ENV_VAR, cls.DEFAULT_STRATEGY).lower()

        # Validate strategy
        if strategy not in cls.get_available_strategies():
            logger = logging.getLogger(__name__)
            logger.warning(
                f"Unknown HF download strategy '{strategy}', falling back to '{cls.DEFAULT_STRATEGY}'"
            )
            return cls.DEFAULT_STRATEGY

        return strategy

    @classmethod
    def create_strategy(
        cls, workspace_manager, strategy: Optional[str] = None
    ) -> HFDownloadStrategy:
        """
        Create HF download strategy instance.

        Args:
            workspace_manager: Workspace manager instance
            strategy: Optional strategy override (defaults to environment configuration)

        Returns:
            HFDownloadStrategy instance
        """
        if strategy is None:
            strategy = cls.get_configured_strategy()

        logger = logging.getLogger(__name__)
        logger.debug(f"Creating HF download strategy: {strategy}")

        if strategy == cls.TETRA_STRATEGY:
            return TetraHFDownloader(workspace_manager)
        elif strategy == cls.NATIVE_STRATEGY:
            return NativeHFDownloader(workspace_manager)
        else:
            # Fallback to native
            logger.warning(f"Unknown strategy '{strategy}', using native")
            return NativeHFDownloader(workspace_manager)

    @classmethod
    def set_strategy(cls, strategy: str) -> None:
        """
        Set the HF download strategy via environment variable.

        Args:
            strategy: Strategy name to set
        """
        if strategy not in cls.get_available_strategies():
            raise ValueError(
                f"Invalid strategy '{strategy}'. Available: {cls.get_available_strategies()}"
            )

        os.environ[cls.STRATEGY_ENV_VAR] = strategy

        logger = logging.getLogger(__name__)
        logger.info(f"Set HF download strategy to: {strategy}")

    @classmethod
    def get_strategy_info(cls) -> Dict[str, Any]:
        """
        Get information about the current strategy configuration.

        Returns:
            Dictionary with strategy configuration info
        """
        current_strategy = cls.get_configured_strategy()
        env_value = os.environ.get(cls.STRATEGY_ENV_VAR, "not set")

        return {
            "current_strategy": current_strategy,
            "environment_variable": cls.STRATEGY_ENV_VAR,
            "environment_value": env_value,
            "default_strategy": cls.DEFAULT_STRATEGY,
            "available_strategies": cls.get_available_strategies(),
        }
