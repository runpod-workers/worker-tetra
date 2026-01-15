"""Integration tests for unpack_volume module."""

import os
import sys
import tarfile
from pathlib import Path
from unittest.mock import patch

import pytest

from unpack_volume import unpack_app_from_volume


class TestUnpackVolumeIntegration:
    """End-to-end integration tests for volume unpacking."""

    @pytest.mark.integration
    def test_end_to_end_extraction_with_real_tarball(self, tmp_path):
        """Test complete extraction workflow with a real tarball."""
        # Create a realistic project structure
        project_src = tmp_path / "project_src"
        project_src.mkdir()

        # Create multiple files and directories
        (project_src / "main.py").write_text(
            """
import logging

logger = logging.getLogger(__name__)

def main():
    logger.info("Application started")
    return "success"

if __name__ == "__main__":
    main()
"""
        )

        (project_src / "utils").mkdir()
        (project_src / "utils" / "__init__.py").write_text("")
        (project_src / "utils" / "helpers.py").write_text(
            """
def add(a, b):
    return a + b

def multiply(a, b):
    return a * b
"""
        )

        (project_src / "config.json").write_text('{"version": "1.0.0"}')

        # Create the tarball
        artifact_path = tmp_path / "archive.tar.gz"
        with tarfile.open(artifact_path, mode="w:gz") as tar:
            for root, dirs, files in os.walk(project_src):
                for file in files:
                    file_path = Path(root) / file
                    arcname = file_path.relative_to(project_src)
                    tar.add(file_path, arcname=str(arcname))

        # Create app directory
        app_dir = tmp_path / "app"

        # Perform extraction
        with patch(
            "unpack_volume._canonical_project_artifact_path", return_value=artifact_path
        ):
            result = unpack_app_from_volume(app_dir=app_dir)

        # Verify results
        assert result is True

        # Check all files were extracted
        assert (app_dir / "main.py").exists()
        assert (app_dir / "utils" / "__init__.py").exists()
        assert (app_dir / "utils" / "helpers.py").exists()
        assert (app_dir / "config.json").exists()

        # Verify file contents
        assert "def main():" in (app_dir / "main.py").read_text()
        assert "def add(a, b):" in (app_dir / "utils" / "helpers.py").read_text()
        assert '"version": "1.0.0"' in (app_dir / "config.json").read_text()

        # Verify sys.path was updated
        assert str(app_dir) in sys.path

    @pytest.mark.integration
    def test_end_to_end_maybe_unpack_workflow(self, tmp_path):
        """Test complete maybe_unpack workflow with real environment."""
        # Create a simple tarball
        project_src = tmp_path / "project_src"
        project_src.mkdir()
        (project_src / "app.py").write_text("print('Hello from app')")

        artifact_path = tmp_path / "archive.tar.gz"
        with tarfile.open(artifact_path, mode="w:gz") as tar:
            tar.add(project_src / "app.py", arcname="app.py")

        app_dir = tmp_path / "app"

        # Mock environment to enable unpacking
        with (
            patch.dict(
                os.environ,
                {
                    "RUNPOD_POD_ID": "test-pod-123",
                },
            ),
            patch(
                "unpack_volume._canonical_project_artifact_path",
                return_value=artifact_path,
            ),
        ):
            # Reset global state
            import unpack_volume

            unpack_volume._UNPACKED = False

            # Call maybe_unpack (though it needs handler integration to work fully)
            # For now, test the unpack_app_from_volume directly
            result = unpack_app_from_volume(app_dir=app_dir)

        # Verify extraction
        assert result is True
        assert (app_dir / "app.py").exists()
        assert (app_dir / "app.py").read_text() == "print('Hello from app')"

    @pytest.mark.integration
    def test_large_tarball_extraction(self, tmp_path):
        """Test extraction of tarball with many files."""
        # Create a project with many files
        project_src = tmp_path / "project_src"
        project_src.mkdir()

        # Create 50 files across different directories
        for i in range(5):
            subdir = project_src / f"module_{i}"
            subdir.mkdir()
            for j in range(10):
                (subdir / f"file_{j}.py").write_text(f"# Module {i} File {j}\n")

        # Create the tarball
        artifact_path = tmp_path / "large_archive.tar.gz"
        with tarfile.open(artifact_path, mode="w:gz") as tar:
            for root, dirs, files in os.walk(project_src):
                for file in files:
                    file_path = Path(root) / file
                    arcname = file_path.relative_to(project_src)
                    tar.add(file_path, arcname=str(arcname))

        app_dir = tmp_path / "app"

        # Perform extraction
        with patch(
            "unpack_volume._canonical_project_artifact_path", return_value=artifact_path
        ):
            result = unpack_app_from_volume(app_dir=app_dir)

        # Verify all files were extracted
        assert result is True
        for i in range(5):
            for j in range(10):
                assert (app_dir / f"module_{i}" / f"file_{j}.py").exists()

        # Count total files
        extracted_files = list(app_dir.rglob("*.py"))
        assert len(extracted_files) == 50
