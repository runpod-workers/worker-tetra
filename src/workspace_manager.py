import os
from constants import (
    RUNPOD_VOLUME_PATH,
    RUNTIMES_DIR_NAME,
)


class WorkspaceManager:
    """
    Provides workspace path configuration for CDR daemon initialization.

    The workspace path identifies the persistent storage location in the network volume
    where CDR (Continuous Data Replication) daemon syncs container data.
    """

    def __init__(self) -> None:
        self.has_runpod_volume = os.path.exists(RUNPOD_VOLUME_PATH)
        self.endpoint_id = os.environ.get("RUNPOD_ENDPOINT_ID", "default")
        self.workspace_path = None

        if self.has_runpod_volume:
            # Endpoint-specific workspace: /runpod-volume/runtimes/{endpoint_id}
            self.workspace_path = os.path.join(
                RUNPOD_VOLUME_PATH, RUNTIMES_DIR_NAME, self.endpoint_id
            )
