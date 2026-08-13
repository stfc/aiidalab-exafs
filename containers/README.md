# AiiDAlab FEFF Containers

This directory contains tooling for running `aiidalab-feff` inside an AiiDAlab
container, covering two complementary workflows:

1. **Live development** — the automated `aiidalab-launch` script
   ([`launch.py`](launch.py)) that mounts your local checkouts and gives an
   instant edit→refresh loop inside a running AiiDAlab container.
2. **Deployment** — a standard, self-contained Docker image
   ([`Dockerfile`](Dockerfile)) with the app and its dependencies baked in,
   plus a startup script for launching it on a user's machine.

---

## 1. Live Development (aiidalab-launch)

The launcher uses the official EPFL [AiiDAlab Launch](https://github.com/aiidalab/aiidalab-launch)
tool. We don't maintain custom Dockerfiles or build images from scratch — we
start a standardized AiiDAlab base container (`ghcr.io/stfc/alc-ux/base:py310`),
mount the local packages as live bind-mounts, and install them in editable mode
inside.

- **Zero build times:** no waiting for custom Docker/Podman images to compile.
- **True live editing:** changes to the local `aiidalab-feff`, `stfc_aiida-feff`
  and `alc-aiidalab-widgets` checkouts are instantly active in the container.
- **Mac / Podman friendly:** `aiidalab-launch` handles Podman VM socket
  configuration and port forwarding out of the box.

### Required layout

The launcher expects the standard sibling directory layout:

```text
<workspace>
├── aiidalab-exafs         # this repository
├── stfc_aiida-feff        # local dependency
└── alc-aiidalab-widgets   # local dependency
```

### Quick start

```bash
pipx install aiidalab-launch
python3 containers/launch.py
```

The script autonomously configures an `aiidalab-feff` profile, bind-mounts the
local directories, starts the container (Podman), editable-installs the three
packages, configures AiiDA inside the container, and prints direct clickable
URLs:

1. **Direct App Mode (Recommended):**
   `http://localhost:8889/apps/apps/aiidalab-feff/main.ipynb?token=...`
2. **JupyterLab Editor Mode:**
   `http://localhost:8889/lab/tree/apps/aiidalab-feff/main.ipynb?token=...`

Set `AIIDALAB_FEFF_DEV=1` to also bind-mount and editable-install the two
sibling repositories for co-development. Without it, siblings are installed
from their `main` GitHub branches.

Development commands:

```bash
aiidalab-launch logs -p aiidalab-feff
aiidalab-launch status -p aiidalab-feff
aiidalab-launch stop -p aiidalab-feff
aiidalab-launch exec -p aiidalab-feff -- <command>
```

---

## 2. Deployment Image

For production/end-user deployment we build a standard Docker image with the
app baked in, following the ALC-UX
[docker image guide](https://stfc.github.io/alc-ux/). The image is based on
`ghcr.io/stfc/alc-ux/base:py310` (a Python 3.10 port of the official
`aiidalab/full-stack` image; the official image is capped at Python 3.9).

The image:

- installs the `aiida-feff` and `alc-aiidalab-widgets` dependencies from their
  `main` GitHub branches;
- copies this repository into `/home/jovyan/apps/aiidalab-feff` (where the
  AiiDAlab runtime discovers apps) and `pip install`s the `aiidalab-feff`
  package;
- registers a `before-notebook.d` hook that configures AiiDA on first boot —
  the base image already creates the AiiDA profile and localhost computer, our
  hook additionally registers the localhost `feff` and `python3` codes and
  starts the AiiDA REST API used by the aiida-explorer button;
- applies the `feff8l.sh` shebang fix so FEFF calculations work under the
  container's bash.

### Build

```bash
./containers/build.sh                       # tags aiidalab-feff:latest
./containers/build.sh --tag aiidalab-feff:0.1.0
```

or directly:

```bash
docker build -f containers/Dockerfile -t aiidalab-feff:latest .
```

### Run

```bash
docker run -it --rm -p 8888:8888 -v "$HOME":/home/jovyan aiidalab-feff:latest
```

or use the provided startup script, which detects Docker/Apptainer, persists
data by binding `$HOME`, and asks for AiiDA profile details on first use:

```bash
./containers/startup.sh
./containers/startup.sh --image aiidalab-feff:0.1.0 --port 9999
```

### First-boot AiiDA profile

The base image creates a default AiiDA profile on first start using these
environment variables:

| Variable                     | Default          |
| ---------------------------- | ---------------- |
| `AIIDA_PROFILE_NAME`         | `default`        |
| `AIIDA_USER_EMAIL`           | `aiida@localhost` |
| `AIIDA_USER_FIRST_NAME`      | `Giuseppe`       |
| `AIIDA_USER_LAST_NAME`       | `Verdi`          |
| `AIIDA_USER_INSTITUTION`     | `Khedivial`      |

Set `SETUP_DEFAULT_AIIDA_PROFILE=false` to skip profile creation (e.g. when
reusing an existing profile from a previous bind mount). A profile is
considered present when `config.json` exists in the bind path's `.aiida`
directory — the startup script uses this check to decide whether to prompt for
the values above.

### Notes / limitations

- AiiDA profiles and databases are managed **inside** the container; a local
  AiiDA installation cannot access a container-created profile. Data persists
  as long as you bind-mount the home directory.
- The app is installed in system space (`/opt/aiidalab-feff/app`) and linked
  into `<home>/apps/aiidalab-feff` on every container start, mirroring how the
  base image installs its own home app. This keeps the app discoverable even
  when the home directory is a fresh bind mount.
- AiiDAlab images run as uid 1000 (`jovyan`). The bind directory must be
  writable by uid 1000 — this is usually already the case on single-user
  machines; otherwise `chown 1000:100 <dir>` or start with
  `--user root -e CHOWN_HOME=1`.
- The REST API runs on container port 5000; `startup.sh` maps it to the host
  port 5050 by default (`--restapi-port 0` disables it). Apptainer shares the
  host network, so no mapping is needed there.

---

## Files

| File | Purpose |
| ---- | ------- |
| `launch.py` | Live-development launcher (aiidalab-launch, bind-mount + editable install). |
| `setup-aiida.sh` | Idempotent AiiDA configuration: profile wait, localhost computer, `feff`/`python3` codes, daemon. Used inside the deployment image hook and by `launch.py`. |
| `start_restapi.sh` | Starts/restarts the AiiDA REST API on `0.0.0.0:5000` inside the container. |
| `95_setup-aiidalab-feff.sh` | `before-notebook.d` hook baked into the deployment image; runs `setup-aiida.sh` + `start_restapi.sh` on every container start. |
| `Dockerfile` | Deployment image definition (app + deps baked in). |
| `build.sh` | Convenience build wrapper around the `Dockerfile`. |
| `startup.sh` | End-user launcher (Docker/Apptainer, port/bind/profile configuration). |
