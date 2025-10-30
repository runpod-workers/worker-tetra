"""
Flash Server startup script.

Downloads project tarball, extracts it, and starts the FastAPI server.
"""

import logging
import os
import sys
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-5s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

log = logging.getLogger(__name__)


def main():
    """Main entry point for Flash Server."""
    log.info("Flash Server starting...")

    # Step 1: Load tarball if specified
    try:
        from tarball_loader import should_load_tarball, download_and_extract_tarball

        if should_load_tarball():
            success = download_and_extract_tarball()
            if not success:
                log.error("Failed to load project tarball - exiting")
                sys.exit(1)
        else:
            log.info("No tarball specified - using local code")
    except ImportError:
        log.warning("tarball_loader not available - using local code")

    # Step 2: Add project directory to Python path
    project_dir = Path("/app/project")
    if project_dir.exists():
        log.info(f"Adding project directory to Python path: {project_dir}")
        sys.path.insert(0, str(project_dir))
    else:
        log.info("Using /app as project directory")
        sys.path.insert(0, "/app")

    # Step 3: Import and start FastAPI app
    try:
        # Look for main.py with app instance
        log.info("Looking for FastAPI app...")

        # Try to import from project
        try:
            from main import app

            log.info("Found app in main.py")
        except ImportError:
            # Try workers/main.py (if project structure uses workers/)
            try:
                from workers.main import app

                log.info("Found app in workers/main.py")
            except ImportError:
                log.error("Could not find FastAPI app in main.py or workers/main.py")
                sys.exit(1)

        # Step 4: Start Uvicorn server
        import uvicorn

        port = int(os.getenv("PORT", "8000"))
        log.info(f"Starting Uvicorn server on port {port}")

        uvicorn.run(
            app,
            host="0.0.0.0",
            port=port,
            log_level="info",
        )

    except Exception as e:
        log.error(f"Failed to start server: {e}")
        import traceback

        log.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()
