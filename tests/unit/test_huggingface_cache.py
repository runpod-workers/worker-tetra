"""Tests for HuggingFaceCacheAhead component."""

import os
from unittest.mock import patch, Mock
import pytest

from huggingface_cache import HuggingFaceCacheAhead
from remote_execution import FunctionResponse


class TestHuggingFaceCacheAhead:
    """Test HuggingFace cache-ahead functionality."""

    def setup_method(self):
        """Setup for each test method."""
        self.hf_cache = HuggingFaceCacheAhead()

    @patch("huggingface_cache.scan_cache_dir")
    def test_is_model_cached_returns_true_when_cached(self, mock_scan):
        """Test cache detection returns True when model is cached."""
        # Mock cache info with our model present
        mock_repo = Mock()
        mock_repo.repo_id = "gpt2"
        mock_rev = Mock()
        mock_rev.commit_hash = "main"
        mock_repo.revisions = [mock_rev]

        mock_cache_info = Mock()
        mock_cache_info.repos = [mock_repo]
        mock_scan.return_value = mock_cache_info

        result = self.hf_cache._is_model_cached("gpt2", "main")
        assert result is True

    @patch("huggingface_cache.scan_cache_dir")
    def test_is_model_cached_returns_false_when_not_cached(self, mock_scan):
        """Test cache detection returns False when model is not cached."""
        # Mock empty cache
        mock_cache_info = Mock()
        mock_cache_info.repos = []
        mock_scan.return_value = mock_cache_info

        result = self.hf_cache._is_model_cached("gpt2", "main")
        assert result is False

    @patch("huggingface_cache.scan_cache_dir")
    def test_is_model_cached_returns_false_on_error(self, mock_scan):
        """Test cache detection returns False when cache check fails."""
        mock_scan.side_effect = Exception("Cache error")

        result = self.hf_cache._is_model_cached("gpt2", "main")
        assert result is False

    @patch.dict(os.environ, {"HF_TOKEN": "test_token_12345"})
    @patch("huggingface_cache.snapshot_download")
    @patch("huggingface_cache.HuggingFaceCacheAhead._is_model_cached")
    def test_cache_model_download_uses_hf_token(
        self, mock_is_cached, mock_snapshot_download
    ):
        """Test that HF_TOKEN is passed to snapshot_download when present."""
        mock_is_cached.return_value = False
        mock_snapshot_download.return_value = "/cache/path/gpt2"

        result = self.hf_cache.cache_model_download("gpt2")

        assert result.success is True
        mock_snapshot_download.assert_called_once_with(
            repo_id="gpt2", revision="main", token="test_token_12345"
        )

    @patch.dict(os.environ, {}, clear=True)
    @patch("huggingface_cache.snapshot_download")
    @patch("huggingface_cache.HuggingFaceCacheAhead._is_model_cached")
    def test_cache_model_download_without_token(
        self, mock_is_cached, mock_snapshot_download
    ):
        """Test that None is passed when HF_TOKEN is not present."""
        mock_is_cached.return_value = False
        mock_snapshot_download.return_value = "/cache/path/gpt2"

        result = self.hf_cache.cache_model_download("gpt2")

        assert result.success is True
        mock_snapshot_download.assert_called_once_with(
            repo_id="gpt2", revision="main", token=None
        )

    @patch("huggingface_cache.HuggingFaceCacheAhead._is_model_cached")
    def test_cache_model_download_skips_when_cached(self, mock_is_cached):
        """Test that download is skipped when model is already cached."""
        mock_is_cached.return_value = True

        result = self.hf_cache.cache_model_download("gpt2")

        assert result.success is True
        assert "already cached" in result.stdout
        assert "cache hit" in result.stdout

    @patch("huggingface_cache.snapshot_download")
    @patch("huggingface_cache.HuggingFaceCacheAhead._is_model_cached")
    def test_cache_model_download_success(self, mock_is_cached, mock_snapshot_download):
        """Test successful model download."""
        mock_is_cached.return_value = False
        mock_snapshot_download.return_value = "/cache/path/gpt2"

        result = self.hf_cache.cache_model_download("gpt2")

        assert result.success is True
        assert "gpt2" in result.stdout
        assert "/cache/path/gpt2" in result.stdout

    @patch("huggingface_cache.snapshot_download")
    @patch("huggingface_cache.HuggingFaceCacheAhead._is_model_cached")
    def test_cache_model_download_handles_network_error(
        self, mock_is_cached, mock_snapshot_download
    ):
        """Test error handling for network failures."""
        mock_is_cached.return_value = False
        mock_snapshot_download.side_effect = Exception("Network error")

        result = self.hf_cache.cache_model_download("gpt2")

        assert result.success is False
        assert "Failed to cache-ahead" in result.error
        assert "gpt2" in result.error

    @patch("huggingface_cache.snapshot_download")
    @patch("huggingface_cache.HuggingFaceCacheAhead._is_model_cached")
    def test_cache_model_download_handles_invalid_model(
        self, mock_is_cached, mock_snapshot_download
    ):
        """Test error handling for invalid model IDs."""
        mock_is_cached.return_value = False
        mock_snapshot_download.side_effect = Exception("Model not found")

        result = self.hf_cache.cache_model_download("invalid-model-id")

        assert result.success is False
        assert "Failed to cache-ahead" in result.error

    @pytest.mark.asyncio
    @patch("huggingface_cache.asyncio.to_thread")
    async def test_cache_model_download_async_delegates_to_sync(self, mock_to_thread):
        """Test async wrapper properly delegates to sync method."""
        mock_response = FunctionResponse(success=True, stdout="Model cached")
        mock_to_thread.return_value = mock_response

        result = await self.hf_cache.cache_model_download_async("gpt2", "v1.0")

        mock_to_thread.assert_called_once()
        call_args = mock_to_thread.call_args
        assert call_args[0][0] == self.hf_cache.cache_model_download
        assert call_args[0][1] == "gpt2"
        assert call_args[0][2] == "v1.0"
        assert result == mock_response

    @patch.dict(os.environ, {}, clear=True)
    @patch("huggingface_cache.snapshot_download")
    @patch("huggingface_cache.HuggingFaceCacheAhead._is_model_cached")
    def test_cache_model_download_with_custom_revision(
        self, mock_is_cached, mock_snapshot_download
    ):
        """Test downloading specific model revision."""
        mock_is_cached.return_value = False
        mock_snapshot_download.return_value = "/cache/path/gpt2-v2"

        result = self.hf_cache.cache_model_download("gpt2", revision="v2.0")

        assert result.success is True
        mock_snapshot_download.assert_called_once_with(
            repo_id="gpt2", revision="v2.0", token=None
        )
