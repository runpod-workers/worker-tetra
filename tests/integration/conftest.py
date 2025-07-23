"""Automatically apply integration marker to all tests in tests/integration/"""

import pytest


def pytest_collection_modifyitems(config, items):
    """Add integration marker to all tests in the integration directory"""
    for item in items:
        if "tests/integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
