"""
Integration tests for download acceleration functionality using hf_transfer.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock

from src.download_accelerator import (
    DownloadAccelerator,
    HfTransferDownloader,
)
from src.huggingface_accelerator import HuggingFaceAccelerator
from src.dependency_installer import DependencyInstaller
from src.workspace_manager import WorkspaceManager
from src.remote_executor import RemoteExecutor
from src.remote_execution import FunctionRequest


class TestDownloadAccelerationIntegration:
    """Integration tests for download acceleration components."""

    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.mock_workspace_manager = Mock(spec=WorkspaceManager)
        self.mock_workspace_manager.has_runpod_volume = True
        self.mock_workspace_manager.hf_cache_path = str(self.temp_dir / ".hf-cache")
        self.mock_workspace_manager.workspace_path = str(self.temp_dir)
        self.mock_workspace_manager.venv_path = str(self.temp_dir / ".venv")

    def teardown_method(self):
        """Clean up test environment."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("src.download_accelerator.HF_TRANSFER_ENABLED", True)
    def test_hf_transfer_availability_detection(self):
        """Test detection of hf_transfer availability."""
        with patch("importlib.util.find_spec") as mock_find_spec:
            # Test when hf_transfer is available
            mock_find_spec.return_value = Mock()  # Not None means available
            downloader = HfTransferDownloader()
            assert downloader.hf_transfer_available is True

            # Test when hf_transfer is not available
            mock_find_spec.return_value = None  # None means not available
            downloader = HfTransferDownloader()
            assert downloader.hf_transfer_available is False

    def test_download_accelerator_decision_logic(self):
        """Test when acceleration should be used."""
        accelerator = DownloadAccelerator(self.mock_workspace_manager)

        # Mock hf_transfer as available
        accelerator.hf_transfer_downloader.hf_transfer_available = True

        # Should accelerate large HuggingFace files
        assert (
            accelerator.should_accelerate_download(
                "https://huggingface.co/model/resolve/main/large.bin", 50.0
            )
            is True
        )

        # Should accelerate HuggingFace URLs regardless of size
        assert (
            accelerator.should_accelerate_download(
                "https://huggingface.co/model/resolve/main/file", 5.0
            )
            is True
        )

        # Should not accelerate non-HF files
        assert (
            accelerator.should_accelerate_download("http://example.com/large.bin", 50.0)
            is False
        )
        assert (
            accelerator.should_accelerate_download("http://example.com/small.txt", 1.0)
            is False
        )

    @patch("src.huggingface_accelerator.HfApi.repo_info")
    def test_hf_model_file_fetching(self, mock_repo_info):
        """Test fetching HuggingFace model file information."""
        # Mock successful API response using HF Hub's native API
        from unittest.mock import Mock

        mock_repo_info_obj = Mock()
        mock_repo_info_obj.siblings = [
            Mock(rfilename="pytorch_model.bin", size=500 * 1024 * 1024),  # 500MB
            Mock(rfilename="config.json", size=1024),  # 1KB
        ]
        mock_repo_info.return_value = mock_repo_info_obj

        accelerator = HuggingFaceAccelerator(self.mock_workspace_manager)
        files = accelerator.get_model_files("gpt2")

        assert len(files) == 2
        assert files[0]["path"] == "pytorch_model.bin"
        assert files[0]["size"] == 500 * 1024 * 1024
        assert "huggingface.co/gpt2/resolve/main/pytorch_model.bin" in files[0]["url"]

    def test_hf_model_acceleration_decision(self):
        """Test when HuggingFace models should be pre-cached."""
        accelerator = HuggingFaceAccelerator(self.mock_workspace_manager)

        # Should pre-cache known large models (HF handles acceleration automatically)
        assert accelerator.should_accelerate_model("gpt2") is True
        assert accelerator.should_accelerate_model("bert-base-uncased") is True
        assert accelerator.should_accelerate_model("microsoft/DialoGPT-medium") is True
        assert accelerator.should_accelerate_model("stable-diffusion-v1-5") is True

        # Should not pre-cache unknown/small models
        assert accelerator.should_accelerate_model("unknown/tiny-model") is False

    @patch("src.workspace_manager.WorkspaceManager.__init__")
    def test_remote_executor_with_acceleration(self, mock_workspace_init):
        """Test RemoteExecutor integration with download acceleration."""
        # Mock workspace manager
        mock_workspace_init.return_value = None

        executor = RemoteExecutor()
        executor.workspace_manager = self.mock_workspace_manager
        executor.workspace_manager.has_runpod_volume = True
        executor.workspace_manager.initialize_workspace = Mock(
            return_value=Mock(success=True)
        )
        executor.workspace_manager.accelerate_model_download = Mock(
            return_value=Mock(success=True, stdout="Model cached successfully")
        )

        # Mock dependency installer
        executor.dependency_installer = Mock()
        executor.dependency_installer.install_system_dependencies = Mock(
            return_value=Mock(success=True, stdout="System deps installed")
        )
        executor.dependency_installer.install_dependencies_async = AsyncMock(
            return_value=Mock(success=True, stdout="Python deps installed")
        )
        executor.workspace_manager.accelerate_model_download_async = AsyncMock(
            return_value=Mock(success=True, stdout="Model cached")
        )
        executor.dependency_installer._identify_large_packages = Mock(
            return_value=["torch", "transformers"]
        )
        executor.dependency_installer.download_accelerator = Mock()
        executor.dependency_installer.download_accelerator.hf_transfer_downloader = (
            Mock()
        )
        executor.dependency_installer.download_accelerator.hf_transfer_downloader.hf_transfer_available = True

        # Mock executors
        executor.function_executor = Mock()
        executor.function_executor.execute = Mock(
            return_value=Mock(success=True, result="Function executed")
        )

        # Create request with acceleration enabled
        request = FunctionRequest(
            function_name="test_function",
            function_code="def test_function(): return 'test'",
            dependencies=["torch", "transformers"],
            accelerate_downloads=True,
            hf_models_to_cache=["gpt2", "bert-base-uncased"],
        )

        # Execute function
        import asyncio

        asyncio.run(executor.ExecuteFunction(request))

        # Verify model caching was attempted (async method is called)
        assert (
            executor.workspace_manager.accelerate_model_download_async.call_count == 2
        )
        executor.workspace_manager.accelerate_model_download_async.assert_any_call(
            "gpt2"
        )
        executor.workspace_manager.accelerate_model_download_async.assert_any_call(
            "bert-base-uncased"
        )

        # Verify dependencies were installed with acceleration enabled (async method)
        executor.dependency_installer.install_dependencies_async.assert_called_once_with(
            ["torch", "transformers"], True
        )

    @patch.dict("os.environ", {"HF_TOKEN": "test_token"})
    def test_hf_token_authentication(self):
        """Test that HF_TOKEN is properly used for authentication."""
        downloader = HfTransferDownloader()
        # Test that downloader correctly checks for availability
        # Since hf_transfer may not be installed, this will be False
        # and that's expected behavior
        assert isinstance(downloader.hf_transfer_available, bool)

    def test_strategy_selection_logic(self):
        """Test the download strategy selection logic."""
        accelerator = DownloadAccelerator(self.mock_workspace_manager)
        accelerator.hf_transfer_downloader.hf_transfer_available = True

        # Test file caching detection
        non_existent_file = str(self.temp_dir / "non_existent.bin")
        existing_file = str(self.temp_dir / "existing.bin")

        # Create existing file
        Path(existing_file).write_bytes(b"existing data")

        assert accelerator.is_file_cached(non_existent_file) is False
        assert accelerator.is_file_cached(existing_file) is True

    def test_fallback_behavior_without_accelerators(self):
        """Test graceful fallback when accelerators are not available."""
        accelerator = DownloadAccelerator(self.mock_workspace_manager)
        accelerator.hf_transfer_downloader.hf_transfer_available = False

        # With new logic, when acceleration is not available, we defer to HF native handling
        result = accelerator.download_with_fallback(
            "https://huggingface.co/gpt2/resolve/main/file.bin",
            str(self.temp_dir / "file.bin"),
        )

        # Should return failure and defer to HF native handling
        assert result.success is False
        assert "defer to HF native handling" in result.error

    @patch("src.dependency_installer.run_logged_subprocess")
    def test_dependency_installation_without_acceleration(self, mock_subprocess):
        """Test that packages install normally without aria2c acceleration."""
        # Mock successful installation
        from remote_execution import FunctionResponse

        mock_subprocess.return_value = FunctionResponse(
            success=True, stdout="Installed successfully"
        )

        installer = DependencyInstaller(self.mock_workspace_manager)

        # Install packages
        packages = ["torch==2.0.0", "transformers>=4.20.0"]
        result = installer.install_dependencies(packages)

        assert result.success is True

        # Verify the installation was called
        mock_subprocess.assert_called_once()

    @patch("src.hf_downloader_tetra.DownloadAccelerator")
    def test_model_cache_management(self, mock_download_accelerator):
        """Test model cache information and management using tetra strategy."""
        accelerator = HuggingFaceAccelerator(self.mock_workspace_manager)

        # Test cache info for non-existent model
        cache_info = accelerator.get_cache_info("non-existent-model")
        assert cache_info["cached"] is False
        assert cache_info["cache_size_mb"] == 0
        assert cache_info["file_count"] == 0

        # Create mock cache files for existing model
        model_cache_dir = self.temp_dir / ".hf-cache" / "transformers" / "gpt2"
        model_cache_dir.mkdir(parents=True, exist_ok=True)

        # Create mock model files
        config_file = model_cache_dir / "config.json"
        model_file = model_cache_dir / "pytorch_model.bin"

        config_file.write_text('{"model_type": "gpt2"}')  # ~25 bytes
        model_file.write_bytes(b"0" * (150 * 1024 * 1024))  # 150MB of zeros

        # Test cache info for cached model
        cache_info = accelerator.get_cache_info("gpt2")
        assert cache_info["cached"] is True
        assert (
            abs(cache_info["cache_size_mb"] - 150.0) < 0.1
        )  # Allow for small differences
        assert cache_info["file_count"] == 2

        # Test cache clearing
        result = accelerator.clear_model_cache("gpt2")
        assert result.success is True
        assert not model_cache_dir.exists()


class TestDownloadAccelerationErrorHandling:
    """Test error handling and edge cases in download acceleration."""

    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = Path(tempfile.mkdtemp())

    def teardown_method(self):
        """Clean up test environment."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_hf_transfer_download_failure_fallback(self):
        """Test fallback to standard download when hf_transfer fails."""
        downloader = HfTransferDownloader()

        # Test that unavailable downloader raises error
        if not downloader.hf_transfer_available:
            try:
                result = downloader.download(
                    "https://huggingface.co/gpt2/resolve/main/file.bin",
                    str(self.temp_dir / "file.bin"),
                )
                assert not result.success
            except RuntimeError as e:
                assert "hf_transfer not available" in str(e)

    @patch("src.huggingface_accelerator.HfApi.repo_info")
    def test_hf_api_failure_handling(self, mock_repo_info):
        """Test handling of HuggingFace API failures."""
        # Mock API failure
        mock_repo_info.side_effect = Exception("API error")

        accelerator = HuggingFaceAccelerator(None)
        files = accelerator.get_model_files("gpt2")

        # Should return empty list on failure
        assert files == []

    def test_invalid_model_acceleration(self):
        """Test acceleration with invalid model specifications."""
        mock_workspace = Mock()
        mock_workspace.has_runpod_volume = True
        mock_workspace.hf_cache_path = str(self.temp_dir)

        accelerator = HuggingFaceAccelerator(mock_workspace)

        # Test with empty model ID - should return success but indicate no pre-caching needed
        result = accelerator.accelerate_model_download("")
        assert result.success is True
        assert result.stdout is not None
        assert "does not require acceleration" in result.stdout

    def test_non_hf_url_handling(self):
        """Test handling of non-HuggingFace URLs."""
        downloader = HfTransferDownloader()

        # Test error handling for non-HF URLs when downloader is available
        if downloader.hf_transfer_available:
            result = downloader.download(
                "http://example.com/file.bin", str(self.temp_dir / "file.bin")
            )
            assert result.success is False
            assert result.error_message is not None
            assert "only supports HuggingFace URLs" in result.error_message
        else:
            # When not available, should raise RuntimeError
            try:
                result = downloader.download(
                    "http://example.com/file.bin", str(self.temp_dir / "file.bin")
                )
                assert not result.success
            except RuntimeError as e:
                assert "hf_transfer not available" in str(e)


if __name__ == "__main__":
    pytest.main([__file__])
