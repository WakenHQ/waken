"""Smoke test for M0: the package installs and imports cleanly."""

import waken


def test_package_imports() -> None:
    assert waken.__doc__
