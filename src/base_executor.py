"""Base executor class to ensure consistent patterns across all executors."""

from abc import ABC, abstractmethod
from remote_execution import FunctionRequest, FunctionResponse


class BaseExecutor(ABC):
    """
    Base class for all executors to ensure consistent initialization and execution patterns.

    This class enforces that all executors:
    1. Accept workspace_manager in constructor
    2. Setup Python path before execution
    3. Follow consistent error handling patterns
    """

    def __init__(self, workspace_manager):
        """
        Initialize executor with required workspace manager.

        Args:
            workspace_manager: WorkspaceManager instance for volume operations
        """
        if workspace_manager is None:
            raise ValueError("workspace_manager is required for all executors")
        self.workspace_manager = workspace_manager

    def _setup_execution_environment(self):
        """
        Setup execution environment including Python path.

        This method MUST be called before any code execution to ensure:
        - Volume-installed packages are available in sys.path
        - Workspace is properly configured
        """
        # Setup Python path for volume packages - CRITICAL for volume-installed dependencies
        self.workspace_manager.setup_python_path()

    @abstractmethod
    def execute(self, request: FunctionRequest) -> FunctionResponse:
        """
        Execute the request. Subclasses must implement this method.

        IMPORTANT: All implementations MUST call self._setup_execution_environment()
        before executing any user code.
        """
        pass
