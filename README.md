# AiiDAlab EXAFS

[![Release](https://img.shields.io/github/v/release/stfc/aiidalab-exafs)](https://github.com/stfc/aiidalab-exafs/releases)
[![Pipeline Status](https://github.com/stfc/aiidalab-exafs/actions/workflows/ci-testing.yml/badge.svg?branch=main)](https://github.com/stfc/aiidalab-exafs/actions)
[![Documentation](https://img.shields.io/badge/docs-GitHub%20Pages-blue)](https://stfc.github.io/aiidalab-exafs/)

An AiiDAlab application plugin for FEFF-based EXAFS and MD-EXAFS scientific workflows, maintained by the [Ada Lovelace Centre](https://adalovelacecentre.ac.uk/) (STFC / UKRI).

## Features

- **Interactive 5-Step Wizard**: Structure upload/selection, FEFF calculation parameters, compute resource configuration, live calculation progress, and spectra results exploration.
- **Debye-Waller Analysis**: Screen disorder and visualize mean square relative displacement (MSRD) via an integrated Marimo application (`notebooks/debye_waller.py` and `notebooks/paths_explorer.py`).
- **AiiDA Provenance Browser**: Same-origin integration with `aiida-explorer` for visualizing full calculation graphs.
- **Cloud & HPC Deployment**: Ready for deployment on STFC ADA (Apptainer) and local workstations via Docker/Podman.

## Usage

Launch the app within AiiDAlab or run the main interface in a Jupyter environment:

```python
from aiidalab_exafs.main import main
main()
```

### Experimental references

The **Spectrum** results tab accepts experimental files supported by Larch, including plain text/CSV, XDI, and Athena project files. Uploaded files are stored in AiiDA before Larch imports the selected spectrum, preserving both the source upload and the import parameters. Select an Athena group when a project contains more than one spectrum. For unlabelled or ambiguously labelled text files, choose **Specify column labels** and enter Larch labels such as `k,chi` or `energy,mu,mu0` in file-column order.

Use the live `S₀²` and `ΔE₀` controls to compare the selected FEFF spectrum against the experimental reference in χ(k) and χ(R). **Save scaled simulation** stores the current adjusted FEFF spectrum as a provenance-linked `XasData` node; it never modifies the original calculation output.

## Deployment & Container Workflows

Container tooling is provided in `docker/base/` based on the official `aiidalab/full-stack:edge` image.

### ADA (STFC Cloud Workspace)

ADA runs containers using Apptainer with host networking and isolated temporary storage:

```bash
apptainer run --compat --cleanenv \
    --bind ${HOME}:/home/jovyan \
    --home /home/jovyan \
    docker://ghcr.io/stfc/aiidalab-exafs/base:latest
```

Or run using the startup script:

```bash
./scripts/startup.sh --docker-image=ghcr.io/stfc/aiidalab-exafs/base:latest
```

### Live Development (aiidalab-launch)

To run the app in live development mode with local checkouts bind-mounted into an AiiDAlab container:

```bash
pipx install aiidalab-launch
python3 docker/base/launch.py --dev
```

### Deployment Image

To build and run a self-contained deployment image with the app and dependencies baked in:

```bash
# Build the image (tags aiidalab-exafs:latest)
./docker/base/build.sh

# Start the container with data persistence
./docker/base/startup.sh
```

## For Developers

### Installation

Install the package in editable mode with development dependencies:

```bash
pip install -e ".[testing,pre-commit,dev]"
```

### Style & Linting

Pre-commit hooks are configured using [Ruff](https://docs.astral.sh/ruff/) and [Mypy](https://mypy-lang.org/):

```bash
pip install pre-commit
pre-commit install
```

To run linting and formatting manually:

```bash
ruff check src/ tests/
ruff format src/ tests/
```

## License

[BSD 3-Clause License](LICENSE)
