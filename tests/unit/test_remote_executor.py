import pytest
import base64
import cloudpickle
from unittest.mock import Mock, patch, AsyncMock

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
        with patch.object(self.executor.function_executor, "execute") as mock_execute:
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
            self.executor.class_executor, "execute_class_method"
        ) as mock_class_execute:
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
            self.executor.dependency_installer,
            "install_system_dependencies_async",
            new_callable=AsyncMock,
        ) as mock_sys_deps_async:
            with patch.object(
                self.executor.dependency_installer,
                "install_dependencies_async",
                new_callable=AsyncMock,
            ) as mock_py_deps_async:
                with patch.object(
                    self.executor.function_executor, "execute"
                ) as mock_execute:
                    # Mock async methods with proper FunctionResponse returns
                    from remote_execution import FunctionResponse

                    mock_sys_deps_async.return_value = FunctionResponse(
                        success=True, stdout="System deps installed"
                    )
                    mock_py_deps_async.return_value = FunctionResponse(
                        success=True, stdout="Python deps installed"
                    )
                    mock_execute.return_value = Mock(
                        success=True, result="encoded_result"
                    )

                    await self.executor.ExecuteFunction(request)

                    # Verify all components were called in correct order
                    mock_sys_deps_async.assert_called_once_with(["curl"], True)
                    mock_py_deps_async.assert_called_once_with(["requests"], True)
                    mock_execute.assert_called_once_with(request)

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
            self.executor.dependency_installer,
            "install_dependencies_async",
            new_callable=AsyncMock,
        ) as mock_py_deps_async:
            with patch.object(
                self.executor.function_executor, "execute"
            ) as mock_execute:
                # Mock async method with FunctionResponse
                from remote_execution import FunctionResponse

                mock_py_deps_async.return_value = FunctionResponse(
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

        # Test class executor attributes through component
        assert hasattr(self.executor.class_executor, "class_instances")
        assert hasattr(self.executor.class_executor, "instance_metadata")
