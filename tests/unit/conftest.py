"""Automatically apply unit marker to all tests in tests/unit/"""

import pytest


def pytest_collection_modifyitems(config, items):
    """Add unit marker to all tests in the unit directory"""
    for item in items:
        if "tests/unit" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
