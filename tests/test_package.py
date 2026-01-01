"""Basic package tests."""

import haar


def test_version():
    """Test that version is defined."""
    assert haar.__version__ == "0.1.0"


def test_import():
    """Test that package can be imported."""
    assert haar is not None
