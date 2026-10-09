"""AiiDAlab app for EXAFS calculations."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("aiidalab-exafs")
except PackageNotFoundError:
    __version__ = "0.1.0a1"

from aiidalab_exafs.main import ExafsApp, FeffApp, main

__all__ = ["ExafsApp", "FeffApp", "main", "__version__"]
