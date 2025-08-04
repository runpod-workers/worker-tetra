from remote_execution import FunctionRequest, FunctionResponse, RemoteExecutorStub
from workspace_manager import WorkspaceManager
from dependency_installer import DependencyInstaller
from function_executor import FunctionExecutor
from class_executor import ClassExecutor


class RemoteExecutor(RemoteExecutorStub):
    """
    RemoteExecutor orchestrates remote function and class execution.
    Uses composition pattern with specialized components.
    """

    def __init__(self):
        super().__init__()

        # Initialize components using composition
        self.workspace_manager = WorkspaceManager()
        self.dependency_installer = DependencyInstaller(self.workspace_manager)
        self.function_executor = FunctionExecutor(self.workspace_manager)
        self.class_executor = ClassExecutor(self.workspace_manager)

    async def ExecuteFunction(self, request: FunctionRequest) -> FunctionResponse:
        """
        Execute a function or class method on the remote resource.

        Args:
            request: FunctionRequest object containing function details

        Returns:
            FunctionResponse object with execution result
        """
        # Initialize workspace if using volume
        if self.workspace_manager.has_runpod_volume:
            workspace_init = self.workspace_manager.initialize_workspace()
            if not workspace_init.success:
                return workspace_init
            if workspace_init.stdout:
                print(workspace_init.stdout)

        # Install system dependencies first
        if request.system_dependencies:
            sys_installed = self.dependency_installer.install_system_dependencies(
                request.system_dependencies
            )
            if not sys_installed.success:
                return sys_installed
            print(sys_installed.stdout)

        # Install Python dependencies next
        if request.dependencies:
            py_installed = self.dependency_installer.install_dependencies(
                request.dependencies
            )
            if not py_installed.success:
                return py_installed
            print(py_installed.stdout)

        # Route to appropriate execution method based on type
        execution_type = getattr(request, "execution_type", "function")
        if execution_type == "class":
            return self.class_executor.execute_class_method(request)
        else:
            return self.function_executor.execute(request)
