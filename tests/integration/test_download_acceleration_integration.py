"""
Integration tests for download acceleration functionality.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch

from src.download_accelerator import DownloadAccelerator, Aria2Downloader
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

    @patch("src.download_accelerator.subprocess.run")
    def test_aria2_availability_detection(self, mock_subprocess):
        """Test detection of aria2c availability."""
        # Test when aria2c is available
        mock_subprocess.return_value.returncode = 0
        downloader = Aria2Downloader()
        assert downloader.aria2c_available is True

        # Test when aria2c is not available
        mock_subprocess.side_effect = FileNotFoundError()
        downloader = Aria2Downloader()
        assert downloader.aria2c_available is False

    def test_download_accelerator_decision_logic(self):
        """Test when acceleration should be used."""
        accelerator = DownloadAccelerator(self.mock_workspace_manager)

        # Mock aria2c as available
        accelerator.aria2_downloader.aria2c_available = True

        # Should accelerate large files
        assert (
            accelerator.should_accelerate_download("http://example.com/large.bin", 50.0)
            is True
        )

        # Should accelerate HuggingFace URLs regardless of size
        assert (
            accelerator.should_accelerate_download(
                "https://huggingface.co/model/file", 5.0
            )
            is True
        )

        # Should not accelerate small non-HF files
        assert (
            accelerator.should_accelerate_download("http://example.com/small.txt", 1.0)
            is False
        )

        # Mock aria2c as unavailable
        accelerator.aria2_downloader.aria2c_available = False
        assert (
            accelerator.should_accelerate_download("http://example.com/large.bin", 50.0)
            is False
        )

    def test_large_package_identification(self):
        """Test identification of large packages that benefit from acceleration."""
        installer = DependencyInstaller(self.mock_workspace_manager)

        packages = [
            "torch==2.0.0",
            "transformers>=4.20.0",
            "small-package==1.0.0",
            "numpy",
            "scipy==1.9.0",
        ]

        large_packages = installer._identify_large_packages(packages)

        expected_large = [
            "torch==2.0.0",
            "transformers>=4.20.0",
            "numpy",
            "scipy==1.9.0",
        ]
        assert set(large_packages) == set(expected_large)

    @patch("src.huggingface_accelerator.requests.get")
    def test_hf_model_file_fetching(self, mock_requests):
        """Test fetching HuggingFace model file information."""
        # Mock successful API response
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = [
            {
                "type": "file",
                "path": "pytorch_model.bin",
                "size": 500 * 1024 * 1024,  # 500MB
            },
            {
                "type": "file",
                "path": "config.json",
                "size": 1024,  # 1KB
            },
        ]
        mock_requests.return_value = mock_response

        accelerator = HuggingFaceAccelerator(self.mock_workspace_manager)
        files = accelerator.get_model_files("gpt2")

        assert len(files) == 2
        assert files[0]["path"] == "pytorch_model.bin"
        assert files[0]["size"] == 500 * 1024 * 1024
        assert "huggingface.co/gpt2/resolve/main/pytorch_model.bin" in files[0]["url"]

    def test_hf_model_acceleration_decision(self):
        """Test when HuggingFace models should be accelerated."""
        accelerator = HuggingFaceAccelerator(self.mock_workspace_manager)
        accelerator.download_accelerator.aria2_downloader.aria2c_available = True

        # Should accelerate known large models
        assert accelerator.should_accelerate_model("gpt2") is True
        assert accelerator.should_accelerate_model("bert-base-uncased") is True
        assert accelerator.should_accelerate_model("microsoft/DialoGPT-medium") is True
        assert accelerator.should_accelerate_model("stable-diffusion-v1-5") is True

        # Should not accelerate unknown/small models without aria2c
        accelerator.download_accelerator.aria2_downloader.aria2c_available = False
        assert accelerator.should_accelerate_model("gpt2") is False

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
        executor.dependency_installer.install_dependencies = Mock(
            return_value=Mock(success=True, stdout="Python deps installed")
        )
        executor.dependency_installer._identify_large_packages = Mock(
            return_value=["torch", "transformers"]
        )
        executor.dependency_installer.download_accelerator = Mock()
        executor.dependency_installer.download_accelerator.aria2_downloader = Mock()
        executor.dependency_installer.download_accelerator.aria2_downloader.aria2c_available = True

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

        # Verify model caching was attempted
        assert executor.workspace_manager.accelerate_model_download.call_count == 2
        executor.workspace_manager.accelerate_model_download.assert_any_call("gpt2")
        executor.workspace_manager.accelerate_model_download.assert_any_call(
            "bert-base-uncased"
        )

        # Verify dependencies were installed
        executor.dependency_installer.install_dependencies.assert_called_once_with(
            ["torch", "transformers"], True
        )

    @patch.dict("os.environ", {"HF_TOKEN": "test_token"})
    @patch("src.download_accelerator.subprocess.run")
    @patch("src.download_accelerator.subprocess.Popen")
    def test_hf_token_authentication(self, mock_popen, mock_run):
        """Test that HF_TOKEN is properly used for authentication."""
        # Mock aria2c availability check
        mock_run.return_value.returncode = 0

        # Mock successful aria2c process
        mock_process = Mock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = ("Success", "")
        mock_process.poll.return_value = 0
        mock_process.stdout = Mock()
        mock_process.stdout.readline.return_value = ""
        mock_popen.return_value = mock_process

        downloader = Aria2Downloader()
        downloader.aria2c_available = True

        # Create temporary file for output
        output_file = self.temp_dir / "test_file"

        # Mock file size
        with patch("os.path.getsize", return_value=1024):
            downloader.download(
                "https://huggingface.co/gpt2/resolve/main/pytorch_model.bin",
                str(output_file),
            )

        # Verify aria2c was called with authentication header
        args, kwargs = mock_popen.call_args
        command = args[0]
        assert "--header" in command
        auth_index = command.index("--header")
        assert "Authorization: Bearer test_token" in command[auth_index + 1]

    def test_fallback_behavior_without_aria2(self):
        """Test graceful fallback when aria2c is not available."""
        accelerator = DownloadAccelerator(self.mock_workspace_manager)
        accelerator.aria2_downloader.aria2c_available = False

        with patch("src.download_accelerator.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stderr = ""
            mock_run.return_value.stdout = ""

            # Mock file size
            with patch("os.path.getsize", return_value=1024):
                result = accelerator.download_with_fallback(
                    "http://example.com/file.bin", str(self.temp_dir / "file.bin")
                )

            assert result.success is True
            # Should have used curl as fallback
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert args[0] == "curl"

    @patch("src.dependency_installer.subprocess.Popen")
    def test_accelerated_dependency_installation(self, mock_popen):
        """Test that large packages trigger accelerated installation."""
        # Mock successful installation
        mock_process = Mock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (b"Installed successfully", b"")
        # Add context manager support
        mock_process.__enter__ = Mock(return_value=mock_process)
        mock_process.__exit__ = Mock(return_value=None)
        mock_popen.return_value = mock_process

        installer = DependencyInstaller(self.mock_workspace_manager)
        installer.download_accelerator.aria2_downloader.aria2c_available = True

        # Install large packages
        packages = ["torch==2.0.0", "transformers>=4.20.0"]
        result = installer.install_dependencies(packages)

        assert result.success is True

        # Verify the installation was called (should be called twice - once for aria2c check, once for installation)
        assert mock_popen.call_count == 2

        # Get the installation call (second call)
        install_call = mock_popen.call_args_list[1]
        args, kwargs = install_call

        # Check that UV_CONCURRENT_DOWNLOADS was set in environment
        env = kwargs.get("env", {})
        assert "UV_CONCURRENT_DOWNLOADS" in env
        assert env["UV_CONCURRENT_DOWNLOADS"] == "8"

    def test_model_cache_management(self):
        """Test model cache information and management."""
        accelerator = HuggingFaceAccelerator(self.mock_workspace_manager)

        # Test cache info for non-existent model
        cache_info = accelerator.get_cache_info("non-existent-model")
        assert cache_info["cached"] is False
        assert cache_info["cache_size_mb"] == 0
        assert cache_info["file_count"] == 0

        # Create fake model cache
        model_cache_dir = Path(accelerator.cache_dir) / "transformers" / "gpt2"
        model_cache_dir.mkdir(parents=True, exist_ok=True)

        # Create fake model file
        model_file = model_cache_dir / "pytorch_model.bin"
        model_file.write_bytes(b"fake_model_data" * 1000)  # ~15KB

        # Test cache info for cached model
        cache_info = accelerator.get_cache_info("gpt2")
        assert cache_info["cached"] is True
        assert cache_info["cache_size_mb"] > 0
        assert cache_info["file_count"] == 1

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

    @patch("src.download_accelerator.subprocess.run")
    @patch("src.download_accelerator.subprocess.Popen")
    def test_aria2_download_failure_fallback(self, mock_popen, mock_run):
        """Test fallback to standard download when aria2c fails."""
        # Mock aria2c availability check
        mock_run.return_value.returncode = 0

        # Mock aria2c failure
        mock_process = Mock()
        mock_process.returncode = 1
        mock_process.communicate.return_value = ("", "Download failed")
        mock_process.stdout = Mock()
        mock_process.stdout.readline.return_value = ""
        mock_process.poll.return_value = 1
        mock_popen.return_value = mock_process

        downloader = Aria2Downloader()
        downloader.aria2c_available = True

        with pytest.raises(RuntimeError, match="aria2c failed"):
            downloader.download(
                "http://example.com/file.bin", str(self.temp_dir / "file.bin")
            )

    @patch("src.huggingface_accelerator.requests.get")
    def test_hf_api_failure_handling(self, mock_requests):
        """Test handling of HuggingFace API failures."""
        # Mock API failure
        mock_requests.side_effect = Exception("API error")

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

        # Test with empty model ID - should return success but indicate no acceleration needed
        result = accelerator.accelerate_model_download("")
        assert result.success is True
        assert "does not require acceleration" in result.stdout

        # Test with invalid characters
        result = accelerator.accelerate_model_download("invalid/model/../name")
        # Should handle gracefully without crashing


if __name__ == "__main__":
    pytest.main([__file__])
