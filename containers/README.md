# AiiDAlab Launch Live Development

This directory contains the automated launcher script for `aiidalab-feff` using the official EPFL [AiiDAlab Launch](https://github.com/aiidalab/aiidalab-launch) tool.

By using the official `aiidalab-launch` utility, we don't need to maintain any custom Dockerfiles or build images from scratch (YAGNI!). Instead, we start a standardized, high-performance AiiDAlab base container (`ghcr.io/stfc/alc-ux/base:py310`), mount our local packages as live bind-mounts, and install them in editable mode inside.

## Why this is amazing
- **Zero build times:** No waiting for custom Docker/Podman images to compile.
- **True live editing:** Any change you make in your IDE on the host Mac to *any* of the three local repositories is **instantly active** inside the container without rebuilds or restarts!
- **Community standard:** Uses the same tools used for deploying AiiDAlab in production.
- **Mac / Podman friendly:** `aiidalab-launch` handles all Podman VM socket configuration and port forwarding natively out-of-the-box.

---

## Required Layout

The launcher expects the standard sibling directory layout:

```text
/Users/jks/coding
├── aiidalab-exafs        # this repository
├── stfc_aiida-feff       # local dependency
└── alc-aiidalab-widgets   # local dependency
```

---

## Quick Start

### 1. Install AiiDAlab Launch on your host Mac

If not already installed, run:

```bash
pipx install aiidalab-launch
```
*(or `pip install aiidalab-launch` inside your global Python environment).*

### 2. Run the automated launch script

From the repo root:

```bash
python3 containers/launch.py
```

This script will autonomously:
1. Locate your `aiidalab-launch` configuration and configure a dedicated `aiidalab-feff` profile.
2. Bind-mount the three local directories into the container.
3. Start the container (using Podman).
4. Run `pip install --pre -e` inside the container to install all three packages in editable mode.
5. Configure AiiDA inside the container (localhost computer, FEFF code, python3 path-aggregation code, and daemon) using `setup-aiida.sh`.
6. Print direct clickable URLs to open in your browser!

---

## Direct URLs

At completion, the script prints:

1. **Direct App Mode (Recommended):**
   `http://localhost:8889/apps/aiidalab-feff/main.ipynb?token=...`
   *Use this to test the clean interactive AiiDAlab dashboard directly.*

2. **JupyterLab Editor Mode:**
   `http://localhost:8889/lab/tree/apps/aiidalab-feff/main.ipynb?token=...`
   *Use this to inspect or debug code cells.*

---

## Development commands

- **View Logs:** `aiidalab-launch logs -p aiidalab-feff`
- **Check Status:** `aiidalab-launch status -p aiidalab-feff`
- **Stop Container:** `aiidalab-launch stop -p aiidalab-feff`
- **Execute command inside:** `aiidalab-launch exec -p aiidalab-feff -- <command>`
