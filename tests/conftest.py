"""Pytest configuration and fixtures for aiidalab-exafs tests."""

import pytest

pytest_plugins = ["aiida.tools.pytest_fixtures"]


@pytest.fixture(autouse=True)
def _ensure_aiida_profile(aiida_profile):
    """Ensure an AiiDA test profile is loaded for all tests."""
    yield aiida_profile


def mock_of(cls):
    """Return a MagicMock limited to ``cls``'s attribute names that passes ``isinstance``.

    ``MagicMock(spec=cls)`` fails on Python 3.12 with aiida-core 2.9: mock calls
    ``getattr`` on every class attribute, and node classes raise
    ``UnsupportedSchemaError`` (not ``AttributeError``) for their ``Model``.
    ``dir`` only lists names, so a name list is used as the spec instead.
    """
    from unittest.mock import MagicMock

    mock = MagicMock(spec=dir(cls))
    mock.__class__ = cls
    return mock
