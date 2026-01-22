"""Tests for unpack_volume module."""

import os
import sys
import tarfile
from pathlib import Path
from unittest.mock import patch

import pytest

from unpack_volume import (
    _canonical_project_artifact_path,
    _safe_extract_tar,
    _should_unpack_from_volume,
    maybe_unpack,
    unpack_app_from_volume,
)


class TestSafeExtractTar:
    """Test path traversal prevention in tar extraction."""

    def test_safe_extract_tar_with_normal_paths(self, tmp_path):
        """Test extraction with normal, safe paths."""
        target_dir = tmp_path / "extract"
        target_dir.mkdir()

        # Create a tar file with safe paths
        tar_path = tmp_path / "safe.tar"
        with tarfile.open(tar_path, mode="w") as tar:
            # Add a simple file
            test_file = tmp_path / "test.txt"
            test_file.write_text("safe content")
            tar.add(test_file, arcname="test.txt")

        # Extract and verify
        with tarfile.open(tar_path, mode="r") as tar:
            _safe_extract_tar(tar, target_dir)

        extracted_file = target_dir / "test.txt"
        assert extracted_file.exists()
        assert extracted_file.read_text() == "safe content"

    def test_safe_extract_tar_prevents_path_traversal_dotdot(self, tmp_path):
        """Test prevention of path traversal using ../ in tar members."""
        target_dir = tmp_path / "extract"
        target_dir.mkdir()

        # Create a tar file with malicious path traversal
        tar_path = tmp_path / "malicious.tar"
        with tarfile.open(tar_path, mode="w") as tar:
            # Add a file with path traversal attempt
            test_file = tmp_path / "malicious.txt"
            test_file.write_text("malicious content")
            tar.add(test_file, arcname="../../../etc/passwd")

        # Attempt extraction - should raise ValueError
        with tarfile.open(tar_path, mode="r") as tar:
            with pytest.raises(ValueError, match="unsafe tar member path"):
                _safe_extract_tar(tar, target_dir)

    def test_safe_extract_tar_prevents_absolute_paths(self, tmp_path):
        """Test prevention of absolute path attacks in tar members."""
        target_dir = tmp_path / "extract"
        target_dir.mkdir()

        # Create a tar file with symlink-based path traversal
        tar_path = tmp_path / "symlink_attack.tar"
        with tarfile.open(tar_path, mode="w") as tar:
            # Create a tarinfo with path traversal
            test_file = tmp_path / "normal.txt"
            test_file.write_text("content")

            # Manually create a TarInfo with traversal path
            tarinfo = tar.gettarinfo(str(test_file), arcname="../../../etc/shadow")
            with open(test_file, "rb") as f:
                tar.addfile(tarinfo, f)

        # Attempt extraction - should raise ValueError
        with tarfile.open(tar_path, mode="r") as tar:
            with pytest.raises(ValueError, match="unsafe tar member path"):
                _safe_extract_tar(tar, target_dir)

    def test_safe_extract_tar_allows_subdirectories(self, tmp_path):
        """Test that safe subdirectory extraction works correctly."""
        target_dir = tmp_path / "extract"
        target_dir.mkdir()

        # Create a tar file with nested directories
        tar_path = tmp_path / "nested.tar"
        with tarfile.open(tar_path, mode="w") as tar:
            # Add files in subdirectories
            subdir = tmp_path / "subdir"
            subdir.mkdir()
            test_file = subdir / "nested.txt"
            test_file.write_text("nested content")
            tar.add(test_file, arcname="subdir/nested.txt")

        # Extract and verify
        with tarfile.open(tar_path, mode="r") as tar:
            _safe_extract_tar(tar, target_dir)

        extracted_file = target_dir / "subdir" / "nested.txt"
        assert extracted_file.exists()
        assert extracted_file.read_text() == "nested content"


class TestCanonicalProjectArtifactPath:
    """Test artifact path resolution."""

    def test_default_artifact_path(self):
        """Test default artifact path when no environment variable is set."""
        with patch.dict(os.environ, {}, clear=False):
            # Remove the env var if it exists
            os.environ.pop("FLASH_BUILD_ARTIFACT_PATH", None)
            path = _canonical_project_artifact_path()
            assert path == Path("/root/.runpod/archive.tar.gz")

    def test_custom_artifact_path(self):
        """Test custom artifact path from environment variable."""
        custom_path = "/custom/path/artifact.tar.gz"
        with patch.dict(os.environ, {"FLASH_BUILD_ARTIFACT_PATH": custom_path}):
            path = _canonical_project_artifact_path()
            assert path == Path(custom_path)


class TestUnpackAppFromVolume:
    """Test main unpacking functionality."""

    def test_unpack_app_from_volume_success(self, tmp_path):
        """Test successful extraction of build artifact."""
        # Create a mock artifact
        artifact_path = tmp_path / "archive.tar.gz"
        with tarfile.open(artifact_path, mode="w:gz") as tar:
            test_file = tmp_path / "app.py"
            test_file.write_text("print('hello from app')")
            tar.add(test_file, arcname="app.py")

        # Create app directory
        app_dir = tmp_path / "app"

        # Mock the artifact path
        with patch("unpack_volume._canonical_project_artifact_path", return_value=artifact_path):
            result = unpack_app_from_volume(app_dir=app_dir)

        assert result is True
        assert (app_dir / "app.py").exists()
        assert (app_dir / "app.py").read_text() == "print('hello from app')"

    def test_unpack_app_from_volume_adds_to_syspath(self, tmp_path):
        """Test that app directory is added to sys.path."""
        # Create a mock artifact
        artifact_path = tmp_path / "archive.tar.gz"
        with tarfile.open(artifact_path, mode="w:gz") as tar:
            test_file = tmp_path / "module.py"
            test_file.write_text("value = 42")
            tar.add(test_file, arcname="module.py")

        app_dir = tmp_path / "app"

        # Mock the artifact path
        with patch("unpack_volume._canonical_project_artifact_path", return_value=artifact_path):
            unpack_app_from_volume(app_dir=app_dir)

        # Verify app_dir is in sys.path
        assert str(app_dir) in sys.path

    def test_unpack_app_from_volume_missing_artifact(self, tmp_path):
        """Test handling of missing artifact file."""
        artifact_path = tmp_path / "nonexistent.tar.gz"
        app_dir = tmp_path / "app"

        with patch("unpack_volume._canonical_project_artifact_path", return_value=artifact_path):
            with pytest.raises(FileNotFoundError, match="flash build artifact not found"):
                unpack_app_from_volume(app_dir=app_dir)

    def test_unpack_app_from_volume_artifact_is_directory(self, tmp_path):
        """Test handling when artifact path is a directory instead of file."""
        artifact_path = tmp_path / "artifact_dir"
        artifact_path.mkdir()
        app_dir = tmp_path / "app"

        with patch("unpack_volume._canonical_project_artifact_path", return_value=artifact_path):
            with pytest.raises(FileNotFoundError, match="flash build artifact not found"):
                unpack_app_from_volume(app_dir=app_dir)

    def test_unpack_app_from_volume_extraction_error(self, tmp_path):
        """Test handling of extraction errors."""
        # Create a corrupted tar file
        artifact_path = tmp_path / "corrupted.tar.gz"
        artifact_path.write_text("not a valid tar file")

        app_dir = tmp_path / "app"

        with patch("unpack_volume._canonical_project_artifact_path", return_value=artifact_path):
            with pytest.raises(RuntimeError, match="failed to extract flash artifact"):
                unpack_app_from_volume(app_dir=app_dir)

    def test_unpack_app_from_volume_creates_app_dir(self, tmp_path):
        """Test that app directory is created if it doesn't exist."""
        artifact_path = tmp_path / "archive.tar.gz"
        with tarfile.open(artifact_path, mode="w:gz") as tar:
            test_file = tmp_path / "test.py"
            test_file.write_text("test")
            tar.add(test_file, arcname="test.py")

        app_dir = tmp_path / "nonexistent_dir" / "app"

        with patch("unpack_volume._canonical_project_artifact_path", return_value=artifact_path):
            result = unpack_app_from_volume(app_dir=app_dir)

        assert result is True
        assert app_dir.exists()
        assert (app_dir / "test.py").exists()


class TestShouldUnpackFromVolume:
    """Test environment variable detection logic."""

    def test_should_unpack_for_flash_mothership(self):
        """Test unpacking is enabled for Flash Mothership deployment."""
        with patch.dict(
            os.environ,
            {
                "RUNPOD_POD_ID": "test-pod-id",
                "FLASH_IS_MOTHERSHIP": "true",
            },
            clear=False,
        ):
            os.environ.pop("FLASH_DISABLE_UNPACK", None)
            assert _should_unpack_from_volume() is True

    def test_should_unpack_for_flash_child_endpoint(self):
        """Test unpacking is enabled for Flash Child endpoint deployment."""
        with patch.dict(
            os.environ,
            {
                "RUNPOD_ENDPOINT_ID": "test-endpoint-id",
                "FLASH_MOTHERSHIP_ID": "mothership-endpoint-id",
                "FLASH_RESOURCE_NAME": "gpu_worker",
            },
            clear=False,
        ):
            os.environ.pop("FLASH_DISABLE_UNPACK", None)
            os.environ.pop("RUNPOD_POD_ID", None)
            assert _should_unpack_from_volume() is True

    def test_should_not_unpack_for_live_serverless(self):
        """Test unpacking is disabled for Live Serverless (RUNPOD_* set but no FLASH_*)."""
        with patch.dict(
            os.environ,
            {"RUNPOD_POD_ID": "test-pod-id"},
            clear=False,
        ):
            os.environ.pop("FLASH_DISABLE_UNPACK", None)
            os.environ.pop("FLASH_IS_MOTHERSHIP", None)
            os.environ.pop("FLASH_MOTHERSHIP_ID", None)
            os.environ.pop("FLASH_RESOURCE_NAME", None)
            assert _should_unpack_from_volume() is False

    def test_should_not_unpack_when_no_runpod_vars(self):
        """Test unpacking is disabled when no RunPod environment variables are set."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("RUNPOD_POD_ID", None)
            os.environ.pop("RUNPOD_ENDPOINT_ID", None)
            os.environ.pop("FLASH_DISABLE_UNPACK", None)
            assert _should_unpack_from_volume() is False

    def test_should_not_unpack_when_disabled_with_1(self):
        """Test unpacking is disabled when FLASH_DISABLE_UNPACK=1."""
        with patch.dict(
            os.environ,
            {
                "RUNPOD_POD_ID": "test-pod-id",
                "FLASH_IS_MOTHERSHIP": "true",
                "FLASH_DISABLE_UNPACK": "1",
            },
        ):
            assert _should_unpack_from_volume() is False

    def test_should_not_unpack_when_disabled_with_true(self):
        """Test unpacking is disabled when FLASH_DISABLE_UNPACK=true."""
        with patch.dict(
            os.environ,
            {
                "RUNPOD_POD_ID": "test-pod-id",
                "FLASH_IS_MOTHERSHIP": "true",
                "FLASH_DISABLE_UNPACK": "true",
            },
        ):
            assert _should_unpack_from_volume() is False

    def test_should_not_unpack_when_disabled_with_yes(self):
        """Test unpacking is disabled when FLASH_DISABLE_UNPACK=yes."""
        with patch.dict(
            os.environ,
            {
                "RUNPOD_POD_ID": "test-pod-id",
                "FLASH_IS_MOTHERSHIP": "true",
                "FLASH_DISABLE_UNPACK": "yes",
            },
        ):
            assert _should_unpack_from_volume() is False

    def test_should_unpack_when_disable_flag_has_wrong_value(self):
        """Test unpacking is enabled when FLASH_DISABLE_UNPACK has non-disable value."""
        with patch.dict(
            os.environ,
            {
                "RUNPOD_POD_ID": "test-pod-id",
                "FLASH_IS_MOTHERSHIP": "true",
                "FLASH_DISABLE_UNPACK": "false",
            },
        ):
            assert _should_unpack_from_volume() is True

    def test_should_not_unpack_when_disabled_with_uppercase_true(self):
        """Test unpacking is disabled when FLASH_DISABLE_UNPACK=True (uppercase)."""
        with patch.dict(
            os.environ,
            {
                "RUNPOD_POD_ID": "test-pod-id",
                "FLASH_IS_MOTHERSHIP": "true",
                "FLASH_DISABLE_UNPACK": "True",
            },
        ):
            assert _should_unpack_from_volume() is False

    def test_should_not_unpack_when_disabled_with_uppercase_yes(self):
        """Test unpacking is disabled when FLASH_DISABLE_UNPACK=YES (uppercase)."""
        with patch.dict(
            os.environ,
            {
                "RUNPOD_POD_ID": "test-pod-id",
                "FLASH_IS_MOTHERSHIP": "true",
                "FLASH_DISABLE_UNPACK": "YES",
            },
        ):
            assert _should_unpack_from_volume() is False

    def test_should_not_unpack_when_disabled_with_mixed_case(self):
        """Test unpacking is disabled when FLASH_DISABLE_UNPACK=Yes (mixed case)."""
        with patch.dict(
            os.environ,
            {
                "RUNPOD_POD_ID": "test-pod-id",
                "FLASH_IS_MOTHERSHIP": "true",
                "FLASH_DISABLE_UNPACK": "Yes",
            },
        ):
            assert _should_unpack_from_volume() is False


class TestMaybeUnpack:
    """Test idempotency and error handling of maybe_unpack."""

    def setup_method(self):
        """Reset global state before each test."""
        import unpack_volume

        unpack_volume._UNPACKED = False

    @patch("unpack_volume._should_unpack_from_volume")
    @patch("unpack_volume.unpack_app_from_volume")
    def test_maybe_unpack_success(self, mock_unpack, mock_should_unpack):
        """Test successful unpacking flow."""
        mock_should_unpack.return_value = True
        mock_unpack.return_value = True

        maybe_unpack()

        mock_should_unpack.assert_called_once()
        mock_unpack.assert_called_once()

    @patch("unpack_volume._should_unpack_from_volume")
    @patch("unpack_volume.unpack_app_from_volume")
    def test_maybe_unpack_idempotency(self, mock_unpack, mock_should_unpack):
        """Test that multiple calls to maybe_unpack only unpack once."""
        mock_should_unpack.return_value = True
        mock_unpack.return_value = True

        # Call multiple times
        maybe_unpack()
        maybe_unpack()
        maybe_unpack()

        # Should only actually unpack once
        mock_unpack.assert_called_once()

    @patch("unpack_volume._should_unpack_from_volume")
    @patch("unpack_volume.unpack_app_from_volume")
    def test_maybe_unpack_skips_when_should_not_unpack(self, mock_unpack, mock_should_unpack):
        """Test that unpacking is skipped when conditions are not met."""
        mock_should_unpack.return_value = False

        maybe_unpack()

        mock_should_unpack.assert_called_once()
        mock_unpack.assert_not_called()

    @patch("unpack_volume._should_unpack_from_volume")
    @patch("unpack_volume.unpack_app_from_volume")
    def test_maybe_unpack_propagates_exceptions(self, mock_unpack, mock_should_unpack):
        """Test that exceptions during unpacking are propagated."""
        mock_should_unpack.return_value = True
        mock_unpack.side_effect = FileNotFoundError("Artifact not found")

        with pytest.raises(RuntimeError, match="failed to unpack app from volume"):
            maybe_unpack()

    @patch("unpack_volume._should_unpack_from_volume")
    @patch("unpack_volume.unpack_app_from_volume")
    @patch("unpack_volume.logger")
    def test_maybe_unpack_logs_info_on_start(self, mock_logger, mock_unpack, mock_should_unpack):
        """Test that info is logged when unpacking starts."""
        mock_should_unpack.return_value = True
        mock_unpack.return_value = True

        maybe_unpack()

        mock_logger.info.assert_called_once_with("unpacking app from volume")

    @patch("unpack_volume._should_unpack_from_volume")
    @patch("unpack_volume.unpack_app_from_volume")
    @patch("unpack_volume.logger")
    def test_maybe_unpack_logs_error_on_failure(self, mock_logger, mock_unpack, mock_should_unpack):
        """Test that errors are logged when unpacking fails."""
        mock_should_unpack.return_value = True
        error_msg = "Extraction failed"
        mock_unpack.side_effect = RuntimeError(error_msg)

        with pytest.raises(RuntimeError, match="failed to unpack app from volume"):
            maybe_unpack()

        mock_logger.error.assert_called_once()
        call_args = mock_logger.error.call_args
        assert "failed to unpack app from volume" in call_args[0][0]
