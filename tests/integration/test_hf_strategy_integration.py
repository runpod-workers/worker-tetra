"""
Integration tests for HuggingFace download strategy system.
"""

import os
import pytest
from unittest.mock import Mock, patch

from src.huggingface_accelerator import HuggingFaceAccelerator
from src.hf_strategy_factory import HFStrategyFactory
from hf_downloader_tetra import TetraHFDownloader
from hf_downloader_native import NativeHFDownloader


@pytest.fixture
def mock_workspace_manager():
    """Mock workspace manager for integration tests."""
    workspace_manager = Mock()
    workspace_manager.hf_cache_path = "/tmp/test_cache"
    return workspace_manager


class TestHuggingFaceAcceleratorIntegration:
    """Integration tests for HuggingFaceAccelerator with strategy pattern."""

    def test_accelerator_uses_configured_strategy(self, mock_workspace_manager):
        """Test that accelerator uses the configured strategy."""
        # Set environment to use tetra strategy
        os.environ[HFStrategyFactory.STRATEGY_ENV_VAR] = "tetra"

        with patch("src.hf_downloader_tetra.DownloadAccelerator"):
            accelerator = HuggingFaceAccelerator(mock_workspace_manager)
            assert isinstance(accelerator.strategy, TetraHFDownloader)

    def test_accelerator_strategy_delegation(self, mock_workspace_manager):
        """Test that accelerator properly delegates to strategy methods."""
        # Set to native strategy for simpler testing
        os.environ[HFStrategyFactory.STRATEGY_ENV_VAR] = "native"

        accelerator = HuggingFaceAccelerator(mock_workspace_manager)

        # Mock the strategy methods
        accelerator.strategy.should_accelerate = Mock(return_value=True)
        accelerator.strategy.download_model = Mock(return_value=Mock(success=True))
        accelerator.strategy.is_model_cached = Mock(return_value=False)
        accelerator.strategy.get_cache_info = Mock(return_value={"cached": False})
        accelerator.strategy.clear_model_cache = Mock(return_value=Mock(success=True))

        # Test delegation
        assert accelerator.should_accelerate_model("gpt2")
        accelerator.strategy.should_accelerate.assert_called_once_with("gpt2")

        accelerator.accelerate_model_download("gpt2", "main")
        accelerator.strategy.download_model.assert_called_once_with("gpt2", "main")

        assert not accelerator.is_model_cached("gpt2", "main")
        accelerator.strategy.is_model_cached.assert_called_once_with("gpt2", "main")

        cache_info = accelerator.get_cache_info("gpt2")
        assert cache_info == {"cached": False}
        accelerator.strategy.get_cache_info.assert_called_once_with("gpt2")

        accelerator.clear_model_cache("gpt2")
        accelerator.strategy.clear_model_cache.assert_called_once_with("gpt2")

    def test_accelerator_strategy_switching(self, mock_workspace_manager):
        """Test runtime strategy switching."""
        # Start with native strategy
        os.environ[HFStrategyFactory.STRATEGY_ENV_VAR] = "native"

        accelerator = HuggingFaceAccelerator(mock_workspace_manager)
        assert isinstance(accelerator.strategy, NativeHFDownloader)

        # Switch to tetra strategy
        with patch("src.hf_downloader_tetra.DownloadAccelerator"):
            accelerator.set_strategy("tetra")
            assert isinstance(accelerator.strategy, TetraHFDownloader)

        # Check environment was updated
        assert os.environ[HFStrategyFactory.STRATEGY_ENV_VAR] == "tetra"

    def test_accelerator_get_strategy_info(self, mock_workspace_manager):
        """Test getting strategy information from accelerator."""
        os.environ[HFStrategyFactory.STRATEGY_ENV_VAR] = "native"

        accelerator = HuggingFaceAccelerator(mock_workspace_manager)
        info = accelerator.get_strategy_info()

        assert info["current_strategy"] == "native"
        assert info["strategy_instance"] == "NativeHFDownloader"
        assert info["environment_variable"] == HFStrategyFactory.STRATEGY_ENV_VAR


class TestStrategyEnvironmentIntegration:
    """Test environment variable integration across the system."""

    def test_strategy_persistence_across_instances(self, mock_workspace_manager):
        """Test that strategy setting persists across new instances."""
        # Set strategy
        HFStrategyFactory.set_strategy("tetra")

        # Create first instance
        with patch("src.hf_downloader_tetra.DownloadAccelerator"):
            accelerator1 = HuggingFaceAccelerator(mock_workspace_manager)
            assert isinstance(accelerator1.strategy, TetraHFDownloader)

        # Create second instance - should use same strategy
        with patch("src.hf_downloader_tetra.DownloadAccelerator"):
            accelerator2 = HuggingFaceAccelerator(mock_workspace_manager)
            assert isinstance(accelerator2.strategy, TetraHFDownloader)

    def test_invalid_strategy_fallback(self, mock_workspace_manager):
        """Test fallback behavior with invalid strategy."""
        # Set invalid strategy
        os.environ[HFStrategyFactory.STRATEGY_ENV_VAR] = "invalid_strategy"

        with patch("src.hf_downloader_tetra.DownloadAccelerator"):
            accelerator = HuggingFaceAccelerator(mock_workspace_manager)
            # Should fallback to tetra (default)
            assert isinstance(accelerator.strategy, TetraHFDownloader)

    def test_no_env_var_uses_default(self, mock_workspace_manager):
        """Test default strategy when no environment variable is set."""
        # Clear environment variable
        if HFStrategyFactory.STRATEGY_ENV_VAR in os.environ:
            del os.environ[HFStrategyFactory.STRATEGY_ENV_VAR]

        with patch("src.hf_downloader_tetra.DownloadAccelerator"):
            accelerator = HuggingFaceAccelerator(mock_workspace_manager)
            # Should use default (tetra)
            assert isinstance(accelerator.strategy, TetraHFDownloader)


class TestWorkspaceManagerIntegration:
    """Test integration with workspace manager."""

    def test_strategy_uses_standard_cache_path(self):
        """Test that strategies use standard HF cache path."""
        workspace_manager = Mock()

        # Test tetra strategy - now uses standard HF cache location
        with patch("src.hf_downloader_tetra.DownloadAccelerator"):
            tetra_strategy = TetraHFDownloader(workspace_manager)
            # Should use standard HF cache location
            assert "huggingface" in str(tetra_strategy.cache_dir)

        # Test native strategy (doesn't use cache_dir directly but should store workspace_manager)
        native_strategy = NativeHFDownloader(workspace_manager)
        assert native_strategy.workspace_manager == workspace_manager

    def test_strategy_with_no_cache_path(self):
        """Test strategy behavior when workspace manager has no cache path."""
        workspace_manager = Mock()
        workspace_manager.hf_cache_path = None

        with patch("src.hf_downloader_tetra.DownloadAccelerator"):
            tetra_strategy = TetraHFDownloader(workspace_manager)
            # Should fall back to default cache location
            assert "huggingface" in str(tetra_strategy.cache_dir)
