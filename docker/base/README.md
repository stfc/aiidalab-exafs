# AiiDAlab EXAFS Docker Image & Container Tooling

This directory contains tooling for running `aiidalab-exafs` inside an AiiDAlab
container, covering two complementary workflows:

1. **Live development** — the automated `aiidalab-launch` script
   ([`launch.py`](launch.py)) that mounts your local checkouts and gives an
   instant edit→refresh loop inside a running AiiDAlab container.
2. **Deployment** — a standard, self-contained Docker image
   ([`Dockerfile`](Dockerfile)) with the app and its dependencies baked in,
   plus a startup script for launching it on ADA or a user's machine.

---

## 1. Live Development (aiidalab-launch)

The launcher uses the official EPFL [AiiDAlab Launch](https://github.com/aiidalab/aiidalab-launch)
tool. It starts a standardized AiiDAlab base container (`aiidalab/full-stack:edge`),
mounts the local packages as live bind-mounts, and installs them in editable mode
inside.

- **Zero build times:** no waiting for custom Docker/Podman images to compile.
- **True live editing:** changes to local checkouts are instantly active in the container.
- **Mac / Podman friendly:** `aiidalab-launch` handles Podman VM socket
  configuration and port forwarding out of the box.

### Required layout

The launcher expects the standard sibling directory layout:

```text
<workspace>
├── aiidalab-exafs         # this repository
├── stfc_aiida-feff        # local dependency (optional in non-dev mode)
└── alc-aiidalab-widgets   # local dependency (optional in non-dev mode)
```

### Quick start

```bash
pipx install aiidalab-launch
python3 docker/base/launch.py
```

Pass `--dev` or set `AIIDALAB_EXAFS_DEV=1` to also bind-mount and editable-install local
sibling repositories for co-development. Without it, siblings are installed
from PyPI.

Development commands:

```bash
aiidalab-launch logs -p aiidalab-exafs
aiidalab-launch status -p aiidalab-exafs
aiidalab-launch stop -p aiidalab-exafs
aiidalab-launch exec -p aiidalab-exafs -- <command>
```

---

## 2. Deployment Image (Docker / Apptainer / ADA)

Builds a self-contained image with `aiidalab-exafs` and all dependencies
pre-installed:

```bash
./docker/base/build.sh                       # tags aiidalab-exafs:latest
./docker/base/build.sh --tag aiidalab-exafs:0.1.0a1
```

Or build manually:

```bash
docker build -f docker/base/Dockerfile -t aiidalab-exafs:latest .
```

### Running the image

Run with Docker:

```bash
docker run -it --rm -p 8888:8888 -v "$HOME":/home/jovyan aiidalab-exafs:latest
```

Or use the provided startup script (works with both Docker and Apptainer):

```bash
./docker/base/startup.sh --image aiidalab-exafs:latest --port 8888
```

On ADA (Apptainer):

```bash
apptainer run --compat --cleanenv --bind ${HOME}:/home/jovyan --home /home/jovyan docker://ghcr.io/stfc/aiidalab-exafs/base:latest
```
