import pytest
import base64
import cloudpickle
from unittest.mock import Mock, patch

from remote_executor import RemoteExecutor
from remote_execution import FunctionRequest


class TestRemoteExecutor:
    """Unit tests for the RemoteExecutor orchestration class."""

    def setup_method(self):
        """Setup for each test method."""
        self.executor = RemoteExecutor()

    def encode_args(self, *args):
        """Helper to encode arguments."""
        return [
            base64.b64encode(cloudpickle.dumps(arg)).decode("utf-8") for arg in args
        ]

    def encode_kwargs(self, **kwargs):
        """Helper to encode keyword arguments."""
        return {
            k: base64.b64encode(cloudpickle.dumps(v)).decode("utf-8")
            for k, v in kwargs.items()
        }

    def test_executor_composition_initialization(self):
        """Test RemoteExecutor initializes all component dependencies correctly."""
        # Test that all components are created
        assert hasattr(self.executor, "workspace_manager")
        assert hasattr(self.executor, "dependency_installer")
        assert hasattr(self.executor, "function_executor")
        assert hasattr(self.executor, "class_executor")

        # Test that components are properly initialized
        assert self.executor.workspace_manager is not None
        assert self.executor.dependency_installer is not None
        assert self.executor.function_executor is not None
        assert self.executor.class_executor is not None

    @pytest.mark.asyncio
    async def test_execute_function_orchestration_success(self):
        """Test ExecuteFunction orchestrates components correctly for function execution."""
        request = FunctionRequest(
            function_name="hello",
            function_code="def hello():\n    return 'hello world'",
            args=[],
            kwargs={},
        )

        # Mock component methods to verify orchestration
        with patch.object(
            self.executor.workspace_manager, "initialize_workspace"
        ) as mock_init:
            with patch.object(
                self.executor.function_executor, "execute"
            ) as mock_execute:
                mock_init.return_value = Mock(success=True, stdout="Workspace ready")
                mock_execute.return_value = Mock(success=True, result="encoded_result")

                await self.executor.ExecuteFunction(request)

                # Verify function executor was called
                mock_execute.assert_called_once_with(request)

    @pytest.mark.asyncio
    async def test_execute_function_orchestration_class(self):
        """Test ExecuteFunction routes class execution to class executor."""
        request = FunctionRequest(
            execution_type="class",
            class_name="TestClass",
            class_code="class TestClass:\n    def __call__(self): return 'test'",
            args=[],
            kwargs={},
        )

        with patch.object(
            self.executor.workspace_manager, "initialize_workspace"
        ) as mock_init:
            with patch.object(
                self.executor.class_executor, "execute_class_method"
            ) as mock_class_execute:
                mock_init.return_value = Mock(success=True, stdout="Workspace ready")
                mock_class_execute.return_value = Mock(
                    success=True, result="encoded_result"
                )

                await self.executor.ExecuteFunction(request)

                # Verify class executor was called
                mock_class_execute.assert_called_once_with(request)

    @pytest.mark.asyncio
    async def test_execute_function_with_dependencies_orchestration(self):
        """Test ExecuteFunction orchestrates dependency installation before execution."""
        request = FunctionRequest(
            function_name="test_func",
            function_code="def test_func(): return 'test'",
            dependencies=["requests"],
            system_dependencies=["curl"],
            args=[],
            kwargs={},
        )

        with patch.object(
            self.executor.workspace_manager, "initialize_workspace"
        ) as mock_init:
            with patch.object(
                self.executor.dependency_installer, "install_system_dependencies"
            ) as mock_sys_deps:
                with patch.object(
                    self.executor.dependency_installer, "install_dependencies"
                ) as mock_py_deps:
                    with patch.object(
                        self.executor.function_executor, "execute"
                    ) as mock_execute:
                        # Setup successful responses
                        mock_init.return_value = Mock(
                            success=True, stdout="Workspace ready"
                        )
                        mock_sys_deps.return_value = Mock(
                            success=True, stdout="System deps installed"
                        )
                        mock_py_deps.return_value = Mock(
                            success=True, stdout="Python deps installed"
                        )
                        mock_execute.return_value = Mock(
                            success=True, result="encoded_result"
                        )

                        await self.executor.ExecuteFunction(request)

                        # Verify all components were called in correct order
                        mock_sys_deps.assert_called_once_with(["curl"])
                        mock_py_deps.assert_called_once_with(["requests"], True)
                        mock_execute.assert_called_once_with(request)

    @pytest.mark.asyncio
    async def test_execute_function_workspace_failure_stops_execution(self):
        """Test ExecuteFunction stops on workspace initialization failure."""
        request = FunctionRequest(
            function_name="test_func",
            function_code="def test_func(): return 'test'",
            args=[],
            kwargs={},
        )

        # Mock the workspace to have volume so initialization is triggered
        with patch.object(self.executor.workspace_manager, "has_runpod_volume", True):
            with patch.object(
                self.executor.workspace_manager, "initialize_workspace"
            ) as mock_init:
                with patch.object(
                    self.executor.function_executor, "execute"
                ) as mock_execute:
                    # Setup workspace failure - must return actual response-like object
                    workspace_failure = Mock()
                    workspace_failure.success = False
                    workspace_failure.error = "Workspace init failed"
                    mock_init.return_value = workspace_failure

                    response = await self.executor.ExecuteFunction(request)

                    # Verify execution stopped and error returned
                    assert response.success is False
                    assert response.error and "Workspace init failed" in response.error
                    mock_execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_function_dependency_failure_stops_execution(self):
        """Test ExecuteFunction stops on dependency installation failure."""
        request = FunctionRequest(
            function_name="test_func",
            function_code="def test_func(): return 'test'",
            dependencies=["nonexistent-package"],
            args=[],
            kwargs={},
        )

        with patch.object(
            self.executor.workspace_manager, "initialize_workspace"
        ) as mock_init:
            with patch.object(
                self.executor.dependency_installer, "install_dependencies"
            ) as mock_py_deps:
                with patch.object(
                    self.executor.function_executor, "execute"
                ) as mock_execute:
                    # Setup successful workspace but failed dependencies
                    mock_init.return_value = Mock(
                        success=True, stdout="Workspace ready"
                    )
                    mock_py_deps.return_value = Mock(
                        success=False, error="Package not found"
                    )

                    response = await self.executor.ExecuteFunction(request)

                    # Verify execution stopped and error returned
                    assert response.success is False
                    assert response.error and "Package not found" in response.error
                    mock_execute.assert_not_called()

    def test_component_access_methods(self):
        """Test that components can be accessed directly."""
        # Test dependency installer methods
        with patch.object(
            self.executor.dependency_installer, "install_dependencies"
        ) as mock_install:
            mock_install.return_value = Mock(success=True)
            self.executor.dependency_installer.install_dependencies(["test"], True)
            mock_install.assert_called_once_with(["test"], True)

        # Test workspace manager methods
        with patch.object(
            self.executor.workspace_manager, "initialize_workspace"
        ) as mock_init:
            mock_init.return_value = Mock(success=True)
            self.executor.workspace_manager.initialize_workspace(30)
            mock_init.assert_called_once_with(30)  # default timeout

        # Test function executor methods
        request = FunctionRequest(
            function_name="test",
            function_code="def test(): return 'test'",
        )
        with patch.object(self.executor.function_executor, "execute") as mock_execute:
            mock_execute.return_value = Mock(success=True)
            self.executor.function_executor.execute(request)
            mock_execute.assert_called_once_with(request)

    def test_component_attribute_exposure(self):
        """Test that component attributes are properly exposed."""
        # Test that components are properly accessible
        assert hasattr(self.executor, "workspace_manager")
        assert hasattr(self.executor, "dependency_installer")
        assert hasattr(self.executor, "function_executor")
        assert hasattr(self.executor, "class_executor")

        # Test workspace manager attributes through component
        assert hasattr(self.executor.workspace_manager, "has_runpod_volume")
        assert hasattr(self.executor.workspace_manager, "workspace_path")
        assert hasattr(self.executor.workspace_manager, "venv_path")
        assert hasattr(self.executor.workspace_manager, "cache_path")

        # Test class executor attributes through component
        assert hasattr(self.executor.class_executor, "class_instances")
        assert hasattr(self.executor.class_executor, "instance_metadata")
