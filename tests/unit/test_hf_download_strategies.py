"""
Unit tests for HuggingFace download strategies.
"""

import os
import pytest
from unittest.mock import Mock, patch

from src.hf_downloader_tetra import TetraHFDownloader
from src.hf_downloader_native import NativeHFDownloader
from src.hf_strategy_factory import HFStrategyFactory
from src.remote_execution import FunctionResponse


@pytest.fixture
def mock_workspace_manager():
    """Mock workspace manager."""
    workspace_manager = Mock()
    workspace_manager.hf_cache_path = "/tmp/test_cache"
    return workspace_manager


@pytest.fixture
def mock_download_accelerator():
    """Mock download accelerator."""
    accelerator = Mock()
    accelerator.hf_transfer_downloader = Mock()
    accelerator.hf_transfer_downloader.hf_transfer_available = True
    return accelerator


class TestHFStrategyFactory:
    """Tests for HF strategy factory."""

    def test_get_available_strategies(self):
        """Test getting available strategies."""
        strategies = HFStrategyFactory.get_available_strategies()
        assert HFStrategyFactory.TETRA_STRATEGY in strategies
        assert HFStrategyFactory.NATIVE_STRATEGY in strategies

    def test_get_configured_strategy_default(self):
        """Test default strategy when no env var set."""
        # Clear environment variable
        if HFStrategyFactory.STRATEGY_ENV_VAR in os.environ:
            del os.environ[HFStrategyFactory.STRATEGY_ENV_VAR]

        strategy = HFStrategyFactory.get_configured_strategy()
        assert strategy == HFStrategyFactory.DEFAULT_STRATEGY

    def test_get_configured_strategy_from_env(self):
        """Test getting strategy from environment variable."""
        os.environ[HFStrategyFactory.STRATEGY_ENV_VAR] = "tetra"
        strategy = HFStrategyFactory.get_configured_strategy()
        assert strategy == "tetra"

    def test_get_configured_strategy_invalid_fallback(self):
        """Test fallback to default for invalid strategy."""
        os.environ[HFStrategyFactory.STRATEGY_ENV_VAR] = "invalid_strategy"
        strategy = HFStrategyFactory.get_configured_strategy()
        assert strategy == HFStrategyFactory.DEFAULT_STRATEGY

    def test_create_tetra_strategy(self, mock_workspace_manager):
        """Test creating tetra strategy."""
        with patch("src.hf_strategy_factory.TetraHFDownloader") as mock_tetra:
            mock_instance = Mock()
            mock_tetra.return_value = mock_instance

            strategy = HFStrategyFactory.create_strategy(
                mock_workspace_manager, HFStrategyFactory.TETRA_STRATEGY
            )

            mock_tetra.assert_called_once_with(mock_workspace_manager)
            assert strategy == mock_instance

    def test_create_native_strategy(self, mock_workspace_manager):
        """Test creating native strategy."""
        with patch("src.hf_strategy_factory.NativeHFDownloader") as mock_native:
            mock_instance = Mock()
            mock_native.return_value = mock_instance

            strategy = HFStrategyFactory.create_strategy(
                mock_workspace_manager, HFStrategyFactory.NATIVE_STRATEGY
            )

            mock_native.assert_called_once_with(mock_workspace_manager)
            assert strategy == mock_instance

    def test_set_strategy(self):
        """Test setting strategy environment variable."""
        HFStrategyFactory.set_strategy("tetra")
        assert os.environ[HFStrategyFactory.STRATEGY_ENV_VAR] == "tetra"

    def test_set_strategy_invalid(self):
        """Test setting invalid strategy raises error."""
        with pytest.raises(ValueError):
            HFStrategyFactory.set_strategy("invalid_strategy")

    def test_get_strategy_info(self):
        """Test getting strategy information."""
        os.environ[HFStrategyFactory.STRATEGY_ENV_VAR] = "tetra"

        info = HFStrategyFactory.get_strategy_info()

        assert info["current_strategy"] == "tetra"
        assert info["environment_variable"] == HFStrategyFactory.STRATEGY_ENV_VAR
        assert info["environment_value"] == "tetra"
        assert info["default_strategy"] == HFStrategyFactory.DEFAULT_STRATEGY
        assert "tetra" in info["available_strategies"]
        assert "native" in info["available_strategies"]


class TestTetraHFDownloader:
    """Tests for Tetra HF downloader strategy."""

    def test_init(self, mock_workspace_manager):
        """Test TetraHFDownloader initialization."""
        with patch(
            "src.hf_downloader_tetra.DownloadAccelerator"
        ) as mock_accelerator_class:
            downloader = TetraHFDownloader(mock_workspace_manager)

            assert downloader.workspace_manager == mock_workspace_manager
            mock_accelerator_class.assert_called_once_with(mock_workspace_manager)

    def test_should_accelerate_with_hf_transfer(self, mock_workspace_manager):
        """Test should_accelerate when hf_transfer is available."""
        with patch(
            "src.hf_downloader_tetra.DownloadAccelerator"
        ) as mock_accelerator_class:
            mock_accelerator = Mock()
            mock_accelerator.hf_transfer_downloader.hf_transfer_available = True
            mock_accelerator_class.return_value = mock_accelerator

            downloader = TetraHFDownloader(mock_workspace_manager)

            # Should accelerate large models
            assert downloader.should_accelerate("gpt-3.5-turbo")
            assert downloader.should_accelerate("llama")

            # Should not accelerate small models
            assert not downloader.should_accelerate("prajjwal1/bert-tiny")

    def test_should_accelerate_without_hf_transfer(self, mock_workspace_manager):
        """Test should_accelerate when hf_transfer is not available."""
        with patch(
            "src.hf_downloader_tetra.DownloadAccelerator"
        ) as mock_accelerator_class:
            mock_accelerator = Mock()
            mock_accelerator.hf_transfer_downloader.hf_transfer_available = False
            mock_accelerator_class.return_value = mock_accelerator

            downloader = TetraHFDownloader(mock_workspace_manager)

            # Should not accelerate any models without hf_transfer
            assert not downloader.should_accelerate("gpt-3.5-turbo")
            assert not downloader.should_accelerate("llama")

    @patch("src.hf_downloader_tetra.Path.mkdir")
    def test_download_model_success(self, mock_mkdir, mock_workspace_manager):
        """Test successful model download."""
        with patch(
            "src.hf_downloader_tetra.DownloadAccelerator"
        ) as mock_accelerator_class:
            mock_accelerator = Mock()
            mock_accelerator.hf_transfer_downloader.hf_transfer_available = True
            mock_accelerator_class.return_value = mock_accelerator

            downloader = TetraHFDownloader(mock_workspace_manager)

            # Mock get_model_files to return test files
            downloader.get_model_files = Mock(
                return_value=[
                    {
                        "path": "pytorch_model.bin",
                        "size": 100 * 1024 * 1024,
                        "url": "https://test.com/file",
                    }
                ]
            )

            # Mock download_with_fallback to succeed
            mock_accelerator.download_with_fallback.return_value = FunctionResponse(
                success=True
            )

            result = downloader.download_model("gpt2")

            assert result.success
            assert "Successfully pre-downloaded" in result.stdout

    def test_download_model_no_acceleration_needed(self, mock_workspace_manager):
        """Test download when no acceleration is needed."""
        with patch(
            "src.hf_downloader_tetra.DownloadAccelerator"
        ) as mock_accelerator_class:
            mock_accelerator = Mock()
            mock_accelerator.hf_transfer_downloader.hf_transfer_available = False
            mock_accelerator_class.return_value = mock_accelerator

            downloader = TetraHFDownloader(mock_workspace_manager)

            result = downloader.download_model("prajjwal1/bert-tiny")

            assert result.success
            assert "does not require acceleration" in result.stdout


class TestNativeHFDownloader:
    """Tests for Native HF downloader strategy."""

    def test_init(self, mock_workspace_manager):
        """Test NativeHFDownloader initialization."""
        downloader = NativeHFDownloader(mock_workspace_manager)
        assert downloader.workspace_manager == mock_workspace_manager

    def test_should_accelerate(self, mock_workspace_manager):
        """Test should_accelerate logic."""
        downloader = NativeHFDownloader(mock_workspace_manager)

        # Should accelerate large models
        assert downloader.should_accelerate("gpt-3.5-turbo")
        assert downloader.should_accelerate("llama")

        # Should not accelerate small models
        assert not downloader.should_accelerate("prajjwal1/bert-tiny")

    @patch("src.hf_downloader_native.snapshot_download")
    def test_download_model_success(
        self, mock_snapshot_download, mock_workspace_manager
    ):
        """Test successful model download."""
        mock_snapshot_download.return_value = "/cache/models/gpt2"

        downloader = NativeHFDownloader(mock_workspace_manager)
        result = downloader.download_model("gpt2")

        assert result.success
        assert "Successfully pre-cached model gpt2" in result.stdout
        mock_snapshot_download.assert_called_once_with(repo_id="gpt2", revision="main")

    @patch("src.hf_downloader_native.snapshot_download")
    def test_download_model_failure(
        self, mock_snapshot_download, mock_workspace_manager
    ):
        """Test failed model download."""
        mock_snapshot_download.side_effect = Exception("Download failed")

        downloader = NativeHFDownloader(mock_workspace_manager)
        result = downloader.download_model("gpt2")

        assert not result.success
        assert "Failed to pre-cache model gpt2" in result.error

    def test_download_model_no_acceleration_needed(self, mock_workspace_manager):
        """Test download when no acceleration is needed."""
        downloader = NativeHFDownloader(mock_workspace_manager)
        result = downloader.download_model("prajjwal1/bert-tiny")

        assert result.success
        assert "does not require pre-caching" in result.stdout
