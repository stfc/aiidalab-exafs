"""Pytest configuration and fixtures for aiidalab-feff tests."""

import pytest

pytest_plugins = ["aiida.tools.pytest_fixtures"]


@pytest.fixture(autouse=True)
def _ensure_aiida_profile(aiida_profile):
    """Ensure an AiiDA test profile is loaded for all tests."""
    yield aiida_profile
