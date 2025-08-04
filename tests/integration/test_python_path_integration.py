"""Integration tests to ensure Python path setup works for both function and class execution."""

from unittest.mock import patch, MagicMock

from class_executor import ClassExecutor
from function_executor import FunctionExecutor
from remote_execution import FunctionRequest
from workspace_manager import WorkspaceManager


class TestPythonPathIntegration:
    """Test Python path setup for volume-installed packages."""

    def setup_method(self):
        """Setup test environment."""
        self.mock_workspace_manager = MagicMock(spec=WorkspaceManager)
        self.mock_workspace_manager.has_runpod_volume = True
        self.mock_workspace_manager.venv_path = "/runpod-volume/runtimes/test/.venv"

        self.function_executor = FunctionExecutor(self.mock_workspace_manager)
        self.class_executor = ClassExecutor(self.mock_workspace_manager)

    def test_function_executor_calls_setup_python_path(self):
        """Test that FunctionExecutor calls setup_python_path before execution."""
        # Create a simple function request
        request = FunctionRequest(
            function_code="def test_func(): return 'success'",
            function_name="test_func",
            args=[],
            kwargs={},
            dependencies=[],
            system_dependencies=[],
        )

        # Mock the setup_python_path method
        with patch.object(
            self.mock_workspace_manager, "setup_python_path"
        ) as mock_setup:
            with patch.object(
                self.mock_workspace_manager, "change_to_workspace", return_value=None
            ):
                self.function_executor.execute(request)
                mock_setup.assert_called_once()

    def test_class_executor_calls_setup_python_path(self):
        """Test that ClassExecutor calls setup_python_path before execution."""
        # Create a simple class request
        request = FunctionRequest(
            class_code="class TestClass:\n    def __call__(self): return 'success'",
            class_name="TestClass",
            execution_type="class",
            args=[],
            kwargs={},
            dependencies=[],
            system_dependencies=[],
        )

        # Mock the setup_python_path method
        with patch.object(
            self.mock_workspace_manager, "setup_python_path"
        ) as mock_setup:
            self.class_executor.execute_class_method(request)
            mock_setup.assert_called_once()

    def test_volume_package_import_simulation(self):
        """Test simulation of importing a volume-installed package."""
        # This test simulates the scenario where a package is installed in the volume
        # and needs to be available during class instantiation

        class_code = """
class VolumePackageUser:
    def __init__(self):
        # This would normally fail if setup_python_path() wasn't called
        import sys
        self.paths = sys.path
        
    def get_paths(self):
        return self.paths
"""

        request = FunctionRequest(
            class_code=class_code,
            class_name="VolumePackageUser",
            method_name="get_paths",
            execution_type="class",
            args=[],
            kwargs={},
            dependencies=[],
            system_dependencies=[],
        )

        # Mock setup_python_path to add a fake volume path
        def mock_setup_python_path():
            import sys

            fake_volume_path = (
                "/runpod-volume/runtimes/test/.venv/lib/python3.12/site-packages"
            )
            if fake_volume_path not in sys.path:
                sys.path.insert(0, fake_volume_path)

        with patch.object(
            self.mock_workspace_manager,
            "setup_python_path",
            side_effect=mock_setup_python_path,
        ):
            result = self.class_executor.execute_class_method(request)

            # Verify execution succeeded
            assert result.success is True

            # Verify the fake volume path was added to sys.path
            import sys

            fake_volume_path = (
                "/runpod-volume/runtimes/test/.venv/lib/python3.12/site-packages"
            )
            assert fake_volume_path in sys.path

    def test_base_executor_enforces_workspace_manager(self):
        """Test that BaseExecutor enforces workspace_manager requirement."""
        from base_executor import BaseExecutor

        # Test that BaseExecutor requires workspace_manager
        try:

            class TestExecutor(BaseExecutor):
                def execute(self, request):
                    return None

            # This should raise ValueError
            TestExecutor(None)
            assert False, "Should have raised ValueError for None workspace_manager"
        except ValueError as e:
            assert "workspace_manager is required" in str(e)

    def test_setup_execution_environment_called_by_base_class(self):
        """Test that _setup_execution_environment is properly called."""
        from base_executor import BaseExecutor

        class TestExecutor(BaseExecutor):
            def execute(self, request):
                self._setup_execution_environment()
                return "executed"

        mock_workspace = MagicMock()
        executor = TestExecutor(mock_workspace)

        executor.execute(None)

        # Verify setup_python_path was called
        mock_workspace.setup_python_path.assert_called_once()
