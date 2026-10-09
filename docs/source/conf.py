# Configuration file for the Sphinx documentation builder.
import os
import sys
from importlib import metadata

sys.path.insert(0, os.path.abspath("../../src"))

project = "AiiDAlab EXAFS"
copyright = "2026, Ada Lovelace Centre (STFC)"
author = "J. Kane Shenton"
try:
    release = metadata.version("aiidalab-exafs")
except metadata.PackageNotFoundError:
    release = "0.0.0"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
]

templates_path = ["_templates"]
exclude_patterns = []

source_suffix = ".rst"

html_theme = "piccolo_theme"
html_static_path = ["_static"]
html_theme_options = {
    "source_url": "https://github.com/stfc/aiidalab-exafs",
}
html_logo = "../../logo.svg"
