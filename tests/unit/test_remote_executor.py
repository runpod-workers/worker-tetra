import pytest
import base64
import cloudpickle
from unittest.mock import Mock, patch, AsyncMock

from remote_executor import RemoteExecutor
from tetra_rp.protos.remote_execution import FunctionRequest


class TestRemoteExecutor:
    """Unit tests for the RemoteExecutor orchestration class."""

    def setup_method(self):
        """Setup for each test method."""
        self.executor = RemoteExecutor()

    def encode_args(self, *args):
        """Helper to encode arguments."""
        return [base64.b64encode(cloudpickle.dumps(arg)).decode("utf-8") for arg in args]

    def encode_kwargs(self, **kwargs):
        """Helper to encode keyword arguments."""
        return {
            k: base64.b64encode(cloudpickle.dumps(v)).decode("utf-8") for k, v in kwargs.items()
        }

    def test_executor_composition_initialization(self):
        """Test RemoteExecutor initializes all component dependencies correctly."""
        # Test that all components are created
        assert hasattr(self.executor, "dependency_installer")
        assert hasattr(self.executor, "function_executor")
        assert hasattr(self.executor, "class_executor")

        # Test that components are properly initialized
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
            mock_class_execute.return_value = Mock(success=True, result="encoded_result")

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
                with patch.object(self.executor.function_executor, "execute") as mock_execute:
                    # Mock async methods with proper FunctionResponse returns
                    from tetra_rp.protos.remote_execution import FunctionResponse

                    mock_sys_deps_async.return_value = FunctionResponse(
                        success=True, stdout="System deps installed"
                    )
                    mock_py_deps_async.return_value = FunctionResponse(
                        success=True, stdout="Python deps installed"
                    )
                    mock_execute.return_value = Mock(success=True, result="encoded_result")

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
            with patch.object(self.executor.function_executor, "execute") as mock_execute:
                # Mock async method with FunctionResponse
                from tetra_rp.protos.remote_execution import FunctionResponse

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
        assert hasattr(self.executor, "dependency_installer")
        assert hasattr(self.executor, "function_executor")
        assert hasattr(self.executor, "class_executor")

        # Test class executor attributes through component
        assert hasattr(self.executor.class_executor, "class_instances")
        assert hasattr(self.executor.class_executor, "instance_metadata")

    @pytest.mark.asyncio
    async def test_hydration_before_installation_with_dependencies(self):
        """Test that hydrate_from_volume is called before installations when there are dependencies."""
        request = FunctionRequest(
            function_name="test_func",
            function_code="def test_func(): return 'test'",
            dependencies=["requests"],
            args=[],
            kwargs={},
        )

        with (
            patch.object(
                self.executor.cache_sync,
                "hydrate_from_volume",
                new_callable=AsyncMock,
            ) as mock_hydrate,
            patch.object(
                self.executor.cache_sync,
                "mark_baseline",
            ) as mock_baseline,
            patch.object(
                self.executor.dependency_installer,
                "install_dependencies_async",
                new_callable=AsyncMock,
            ) as mock_deps,
            patch.object(self.executor.function_executor, "execute") as mock_execute,
            patch.object(
                self.executor.cache_sync,
                "sync_to_volume",
                new_callable=AsyncMock,
            ) as mock_sync,
        ):
            from tetra_rp.protos.remote_execution import FunctionResponse

            mock_deps.return_value = FunctionResponse(success=True, stdout="Deps installed")
            mock_execute.return_value = Mock(success=True, result="encoded_result")

            await self.executor.ExecuteFunction(request)

            # Verify hydration was called
            mock_hydrate.assert_called_once()
            # Verify baseline was marked
            mock_baseline.assert_called_once()
            # Verify sync was called after installation
            mock_sync.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_hydration_without_dependencies(self):
        """Test that hydrate_from_volume is not called when there are no dependencies."""
        request = FunctionRequest(
            function_name="test_func",
            function_code="def test_func(): return 'test'",
            args=[],
            kwargs={},
        )

        with (
            patch.object(
                self.executor.cache_sync,
                "hydrate_from_volume",
                new_callable=AsyncMock,
            ) as mock_hydrate,
            patch.object(self.executor.function_executor, "execute") as mock_execute,
        ):
            mock_execute.return_value = Mock(success=True, result="encoded_result")

            await self.executor.ExecuteFunction(request)

            # Verify hydration was NOT called (no dependencies)
            mock_hydrate.assert_not_called()

    @pytest.mark.asyncio
    async def test_flash_detection_routes_to_flash_path_function(self):
        """Test that requests without function_code route to Flash execution path."""
        request = FunctionRequest(
            function_name="my_flash_function",
            # No function_code - indicates Flash deployment
            args=[],
            kwargs={},
        )

        with patch.object(self.executor, "_execute_flash_function") as mock_flash_execute:
            from tetra_rp.protos.remote_execution import FunctionResponse

            mock_flash_execute.return_value = FunctionResponse(success=True, result="flash_result")

            await self.executor.ExecuteFunction(request)

            # Verify Flash execution path was called
            mock_flash_execute.assert_called_once_with(request)

    @pytest.mark.asyncio
    async def test_flash_detection_routes_to_flash_path_class(self):
        """Test that class requests without class_code route to Flash execution path."""
        request = FunctionRequest(
            execution_type="class",
            class_name="MyFlashClass",
            # No class_code - indicates Flash deployment
            method_name="process",
            args=[],
            kwargs={},
        )

        with patch.object(self.executor, "_execute_flash_function") as mock_flash_execute:
            from tetra_rp.protos.remote_execution import FunctionResponse

            mock_flash_execute.return_value = FunctionResponse(success=True, result="flash_result")

            await self.executor.ExecuteFunction(request)

            # Verify Flash execution path was called
            mock_flash_execute.assert_called_once_with(request)

    @pytest.mark.asyncio
    async def test_live_serverless_detection_with_function_code(self):
        """Test that requests with function_code route to Live Serverless path."""
        request = FunctionRequest(
            function_name="live_function",
            function_code="def live_function(): return 'live'",
            args=[],
            kwargs={},
        )

        with (
            patch.object(self.executor, "_execute_flash_function") as mock_flash_execute,
            patch.object(self.executor.function_executor, "execute") as mock_execute,
        ):
            mock_execute.return_value = Mock(success=True, result="live_result")

            await self.executor.ExecuteFunction(request)

            # Verify Live Serverless path was used, not Flash
            mock_flash_execute.assert_not_called()
            mock_execute.assert_called_once_with(request)

    @pytest.mark.asyncio
    async def test_live_serverless_detection_with_class_code(self):
        """Test that class requests with class_code route to Live Serverless path."""
        request = FunctionRequest(
            execution_type="class",
            class_name="LiveClass",
            class_code="class LiveClass:\n    def __call__(self): return 'live'",
            args=[],
            kwargs={},
        )

        with (
            patch.object(self.executor, "_execute_flash_function") as mock_flash_execute,
            patch.object(
                self.executor.class_executor, "execute_class_method"
            ) as mock_class_execute,
        ):
            mock_class_execute.return_value = Mock(success=True, result="live_result")

            await self.executor.ExecuteFunction(request)

            # Verify Live Serverless path was used, not Flash
            mock_flash_execute.assert_not_called()
            mock_class_execute.assert_called_once_with(request)

    @pytest.mark.asyncio
    async def test_flash_execution_success(self):
        """Test successful Flash function execution with manifest lookup."""
        request = FunctionRequest(
            function_name="my_flash_function",
            args=self.encode_args(42),
            kwargs=self.encode_kwargs(name="test"),
        )

        # Mock manifest structure
        mock_manifest = {
            "function_registry": {"my_flash_function": "resource_01"},
            "resources": {
                "resource_01": {
                    "functions": [
                        {
                            "name": "my_flash_function",
                            "module": "test_module",
                            "is_async": False,
                        }
                    ]
                }
            },
        }

        with (
            patch.object(self.executor, "_load_flash_manifest", return_value=mock_manifest),
            patch("importlib.import_module") as mock_import,
            patch("asyncio.to_thread") as mock_to_thread,
        ):
            # Mock the imported function
            mock_func = Mock(return_value="flash_result")
            mock_module = Mock()
            mock_module.my_flash_function = mock_func
            mock_import.return_value = mock_module
            mock_to_thread.return_value = "flash_result"

            response = await self.executor._execute_flash_function(request)

            # Verify success
            assert response.success is True
            assert response.result is not None
            mock_import.assert_any_call("test_module")

    @pytest.mark.asyncio
    async def test_flash_execution_function_not_in_registry(self):
        """Test Flash execution fails when function not in registry."""
        request = FunctionRequest(function_name="unknown_function")

        mock_manifest = {"function_registry": {}, "resources": {}}

        with patch.object(self.executor, "_load_flash_manifest", return_value=mock_manifest):
            response = await self.executor._execute_flash_function(request)

            assert response.success is False
            assert "not found in flash_manifest.json" in response.error

    @pytest.mark.asyncio
    async def test_flash_execution_function_not_in_resource(self):
        """Test Flash execution fails when function in registry but not in resource."""
        request = FunctionRequest(function_name="my_function")

        mock_manifest = {
            "function_registry": {"my_function": "resource_01"},
            "resources": {"resource_01": {"functions": []}},
        }

        with patch.object(self.executor, "_load_flash_manifest", return_value=mock_manifest):
            response = await self.executor._execute_flash_function(request)

            assert response.success is False
            assert "found in registry but not in resource" in response.error

    @pytest.mark.asyncio
    async def test_flash_execution_async_function(self):
        """Test Flash execution handles async functions correctly."""
        request = FunctionRequest(function_name="async_flash_function")

        mock_manifest = {
            "function_registry": {"async_flash_function": "resource_01"},
            "resources": {
                "resource_01": {
                    "functions": [
                        {
                            "name": "async_flash_function",
                            "module": "async_module",
                            "is_async": True,
                        }
                    ]
                }
            },
        }

        async def mock_async_func(*args, **kwargs):
            return "async_result"

        with (
            patch.object(self.executor, "_load_flash_manifest", return_value=mock_manifest),
            patch("importlib.import_module") as mock_import,
        ):
            mock_module = Mock()
            mock_module.async_flash_function = mock_async_func
            mock_import.return_value = mock_module

            response = await self.executor._execute_flash_function(request)

            assert response.success is True
            assert response.result is not None

    @pytest.mark.asyncio
    async def test_flash_execution_handles_exception(self):
        """Test Flash execution handles execution exceptions."""
        request = FunctionRequest(function_name="failing_function")

        mock_manifest = {
            "function_registry": {"failing_function": "resource_01"},
            "resources": {
                "resource_01": {
                    "functions": [
                        {
                            "name": "failing_function",
                            "module": "fail_module",
                            "is_async": False,
                        }
                    ]
                }
            },
        }

        with (
            patch.object(self.executor, "_load_flash_manifest", return_value=mock_manifest),
            patch("importlib.import_module") as mock_import,
        ):
            mock_import.side_effect = ImportError("Module not found")

            response = await self.executor._execute_flash_function(request)

            assert response.success is False
            assert "Failed to execute Flash function" in response.error
            assert "Module not found" in response.error

    @pytest.mark.asyncio
    async def test_execute_function_with_cross_endpoint_routing(self):
        """Test ExecuteFunction routes to remote endpoint using ServiceRegistry."""
        request = FunctionRequest(function_name="my_func")

        # Mock ServiceRegistry to return remote endpoint URL
        with (
            patch("remote_executor.ServiceRegistry") as mock_registry_class,
            patch("aiohttp.ClientSession.post") as mock_post,
        ):
            mock_registry = AsyncMock()
            mock_registry.get_endpoint_for_function = AsyncMock(
                return_value="https://api.runpod.io/v2/endpoint-xyz789/run"
            )
            mock_registry_class.return_value = mock_registry

            # Re-initialize executor with mocked registry
            self.executor.service_registry = mock_registry

            # Mock aiohttp response
            mock_response_data = {
                "output": {
                    "success": True,
                    "result": "encoded_result",
                }
            }
            mock_post_response = AsyncMock()
            mock_post_response.status = 200
            mock_post_response.json = AsyncMock(return_value=mock_response_data)
            mock_post_response.__aenter__.return_value = mock_post_response
            mock_post_response.__aexit__.return_value = None
            mock_post.return_value = mock_post_response

            response = await self.executor.ExecuteFunction(request)

            assert response.success is True
            assert response.result == "encoded_result"
            # Verify ServiceRegistry was called for routing
            mock_registry.get_endpoint_for_function.assert_called_once_with("my_func")

    @pytest.mark.asyncio
    async def test_execute_function_flash_local_execution_with_service_registry(self):
        """Test ExecuteFunction executes locally when ServiceRegistry returns None."""
        request = FunctionRequest(function_name="my_func")

        # Mock manifest for _load_flash_manifest
        mock_manifest = {
            "function_registry": {"my_func": "resource_01"},
            "resources": {
                "resource_01": {
                    "functions": [
                        {
                            "name": "my_func",
                            "module": "test_module",
                            "is_async": False,
                        }
                    ],
                }
            },
        }

        # Mock ServiceRegistry to return None (local function)
        with (
            patch("remote_executor.ServiceRegistry") as mock_registry_class,
            patch.object(self.executor, "_load_flash_manifest", return_value=mock_manifest),
            patch("importlib.import_module") as mock_import,
            patch("asyncio.to_thread") as mock_to_thread,
        ):
            # Create mock registry that returns None for local functions
            mock_registry = AsyncMock()
            mock_registry.get_endpoint_for_function = AsyncMock(return_value=None)
            mock_registry_class.return_value = mock_registry

            # Re-initialize executor with mocked registry
            self.executor.service_registry = mock_registry

            # Mock the imported function
            mock_func = Mock(return_value="flash_result")
            mock_module = Mock()
            mock_module.my_func = mock_func
            mock_import.return_value = mock_module
            mock_to_thread.return_value = "flash_result"

            response = await self.executor.ExecuteFunction(request)

            assert response.success is True
            assert response.result is not None
            # Verify local execution (importlib was called with test_module)
            mock_import.assert_any_call("test_module")
            # Verify ServiceRegistry was called but returned None (local)
            mock_registry.get_endpoint_for_function.assert_called_once_with("my_func")
