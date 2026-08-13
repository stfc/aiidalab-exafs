# AiiDAlab EXAFS

[![Release](https://img.shields.io/github/v/release/stfc/aiidalab-exafs)](https://github.com/stfc/aiidalab-exafs/releases)
[![Pipeline Status](https://github.com/stfc/aiidalab-exafs/actions/workflows/ci-testing.yml/badge.svg?branch=main)](https://github.com/stfc/aiidalab-exafs/actions)

An AiiDAlab application plugin for FEFF-based EXAFS and MD-EXAFS scientific workflows, maintained by the [Ada Lovelace Centre](https://adalovelacecentre.ac.uk/) (ALC).

The app is in active early development.

## Usage

Launch the app within AiiDAlab or run the main interface in a Jupyter environment:

```python
from aiidalab_feff.main import main
main()
```

### Experimental references

The **Spectrum** results tab accepts experimental files supported by Larch,
including plain text/CSV, XDI, and Athena project files. Uploaded files are
stored in AiiDA before Larch imports the selected spectrum, preserving both
the source upload and the import parameters. Select an Athena group when a
project contains more than one spectrum. For unlabelled or ambiguously labelled
text files, choose **Specify column labels** and enter Larch labels such as
`k,chi` or `energy,mu,mu0` in file-column order.

Use the live `S₀²` and `ΔE₀` controls to compare the selected FEFF spectrum
against the experimental reference in χ(k) and χ(R). **Save scaled
simulation** stores the current adjusted FEFF spectrum as a provenance-linked
`XasData` node; it never modifies the original calculation output.

## Container Workflows

Container tooling is provided in the `containers/` directory for both development and deployment based on `ghcr.io/stfc/alc-ux/base:py310`.

### Live Development (aiidalab-launch)

To run the app in live development mode with local checkouts bind-mounted into an AiiDAlab container:

```bash
pipx install aiidalab-launch
python3 containers/launch.py
```

This starts an AiiDAlab container, bind-mounts local package checkouts, installs them in editable mode, configures AiiDA, and provides local JupyterLab and App URLs.

### Deployment Image

To build and run a self-contained deployment image with the app and dependencies baked in:

```bash
# Build the image (tags aiidalab-feff:latest)
./containers/build.sh

# Start the container with data persistence
./containers/startup.sh
```

`startup.sh` supports both Docker and Apptainer engines and maps Jupyter (port 8888) and the AiiDA REST API (port 5050).

## For Developers

### Installation

Install the package in editable mode with development dependencies:

```bash
pip install -e ".[testing,pre-commit]"
```

### Style & Linting

Pre-commit hooks are configured using [Ruff](https://docs.astral.sh/ruff/) and [Mypy](https://mypy-lang.org/):

```bash
pip install pre-commit
pre-commit install
```

To run linting and formatting manually:

```bash
ruff check aiidalab_feff/ tests/
ruff format aiidalab_feff/ tests/
```

### Testing

Run unit tests using [pytest](https://docs.pytest.org/):

```bash
pytest
```

## License

[BSD 3-Clause License](LICENSE)

## Funding

Contributors to this project were funded by

<div align="center">
    <a href="https://adalovelacecentre.ac.uk/">
        <img src="images/alc.svg" alt="ALC Logo" style="width: 30%">
    </a>
</div>



