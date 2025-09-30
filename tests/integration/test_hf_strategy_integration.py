"""
Integration tests for HuggingFace download strategy system.
"""

import os
from unittest.mock import Mock, patch

from src.huggingface_accelerator import HuggingFaceAccelerator
from src.hf_strategy_factory import HFStrategyFactory
from hf_downloader_tetra import TetraHFDownloader
from hf_downloader_native import NativeHFDownloader


class TestHuggingFaceAcceleratorIntegration:
    """Integration tests for HuggingFaceAccelerator with strategy pattern."""

    def test_accelerator_uses_configured_strategy(self):
        """Test that accelerator uses the configured strategy."""
        # Set environment to use tetra strategy
        os.environ[HFStrategyFactory.STRATEGY_ENV_VAR] = "tetra"

        with patch("src.hf_downloader_tetra.DownloadAccelerator"):
            accelerator = HuggingFaceAccelerator()
            assert isinstance(accelerator.strategy, TetraHFDownloader)

    def test_accelerator_strategy_delegation(self):
        """Test that accelerator properly delegates to strategy methods."""
        # Set to native strategy for simpler testing
        os.environ[HFStrategyFactory.STRATEGY_ENV_VAR] = "native"

        accelerator = HuggingFaceAccelerator()

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

    def test_accelerator_strategy_switching(self):
        """Test runtime strategy switching."""
        # Start with native strategy
        os.environ[HFStrategyFactory.STRATEGY_ENV_VAR] = "native"

        accelerator = HuggingFaceAccelerator()
        assert isinstance(accelerator.strategy, NativeHFDownloader)

        # Switch to tetra strategy
        with patch("src.hf_downloader_tetra.DownloadAccelerator"):
            accelerator.set_strategy("tetra")
            assert isinstance(accelerator.strategy, TetraHFDownloader)

        # Check environment was updated
        assert os.environ[HFStrategyFactory.STRATEGY_ENV_VAR] == "tetra"

    def test_accelerator_get_strategy_info(self):
        """Test getting strategy information from accelerator."""
        os.environ[HFStrategyFactory.STRATEGY_ENV_VAR] = "native"

        accelerator = HuggingFaceAccelerator()
        info = accelerator.get_strategy_info()

        assert info["current_strategy"] == "native"
        assert info["strategy_instance"] == "NativeHFDownloader"
        assert info["environment_variable"] == HFStrategyFactory.STRATEGY_ENV_VAR


class TestStrategyEnvironmentIntegration:
    """Test environment variable integration across the system."""

    def test_strategy_persistence_across_instances(self):
        """Test that strategy setting persists across new instances."""
        # Set strategy
        HFStrategyFactory.set_strategy("tetra")

        # Create first instance
        with patch("src.hf_downloader_tetra.DownloadAccelerator"):
            accelerator1 = HuggingFaceAccelerator()
            assert isinstance(accelerator1.strategy, TetraHFDownloader)

        # Create second instance - should use same strategy
        with patch("src.hf_downloader_tetra.DownloadAccelerator"):
            accelerator2 = HuggingFaceAccelerator()
            assert isinstance(accelerator2.strategy, TetraHFDownloader)

    def test_invalid_strategy_fallback(self):
        """Test fallback behavior with invalid strategy."""
        # Set invalid strategy
        os.environ[HFStrategyFactory.STRATEGY_ENV_VAR] = "invalid_strategy"

        accelerator = HuggingFaceAccelerator()
        # Should fallback to native (new default)
        assert isinstance(accelerator.strategy, NativeHFDownloader)

    def test_no_env_var_uses_default(self):
        """Test default strategy when no environment variable is set."""
        # Clear environment variable
        if HFStrategyFactory.STRATEGY_ENV_VAR in os.environ:
            del os.environ[HFStrategyFactory.STRATEGY_ENV_VAR]

        accelerator = HuggingFaceAccelerator()
        # Should use default (native)
        assert isinstance(accelerator.strategy, NativeHFDownloader)


class TestStrategyCacheIntegration:
    """Test strategy cache configuration."""

    def test_tetra_strategy_uses_standard_cache_path(self):
        """Test that tetra strategy uses standard HF cache path."""
        with patch("src.hf_downloader_tetra.DownloadAccelerator"):
            tetra_strategy = TetraHFDownloader()
            # Should use standard HF cache location
            assert "huggingface" in str(tetra_strategy.cache_dir)

    def test_native_strategy_uses_hf_defaults(self):
        """Test that native strategy relies on HF Hub defaults."""
        native_strategy = NativeHFDownloader()
        # Native strategy doesn't manage cache_dir directly
        assert not hasattr(native_strategy, "cache_dir")
