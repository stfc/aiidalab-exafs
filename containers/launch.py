#!/usr/bin/env python3
"""Automated launcher for aiidalab-feff using the official aiidalab-launch tool.

It configures the AiiDAlab profile with correct mount paths, starts the
container, installs the editable packages, and configures AiiDA.

Sibling dependencies (aiida-feff, alc-aiidalab-widgets) are by default
installed from their GitHub ``main`` branches. Set the environment variable
``AIIDALAB_FEFF_DEV=1`` to switch to development mode: sibling directories
``../stfc_aiida-feff`` and ``../alc-aiidalab-widgets`` are then bind-mounted
into the container and editable-installed, giving a live edit loop for
co-development.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import click
import toml

# GitHub URLs for the sibling dependencies (used in default / non-dev mode).
_FEFF_GIT_URL = "git+https://github.com/stfc/aiida-feff.git"
_WIDGETS_GIT_URL = "git+https://github.com/stfc/alc-aiidalab-widgets.git"


def detect_runtime(container_name: str) -> str:
    """Return 'docker' or 'podman' depending on which runtime owns the container.

    ``aiidalab-launch`` itself manages the container, but we still need to talk
    to a container runtime directly for a few host-side tasks (editable pip
    install as root, REST API proxy). The runtime in use varies by host, so we
    detect it rather than hard-coding one.
    """
    for runtime in ("docker", "podman"):
        proc = subprocess.run(
            [runtime, "inspect", container_name],
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0:
            return runtime
    print(
        f"ERROR: could not find container '{container_name}' under docker or podman. "
        "Is the AiiDAlab instance running?"
    )
    sys.exit(1)


def main():
    """Configure, start, and initialize the AiiDAlab Launch container."""
    script_dir = Path(__file__).resolve().parent
    repo_dir = script_dir.parent
    workspace_root = repo_dir.parent

    # Dev mode: bind-mount local sibling repos and editable-install them.
    # Default (no env var, or AIIDALAB_FEFF_DEV=0): install siblings from GitHub.
    dev_mode = os.environ.get("AIIDALAB_FEFF_DEV", "").strip() in ("1", "true", "True")

    feff_dir = workspace_root / "stfc_aiida-feff"
    widgets_dir = workspace_root / "alc-aiidalab-widgets"

    if dev_mode:
        if not feff_dir.is_dir():
            print(f"ERROR: AIIDALAB_FEFF_DEV=1 but sibling directory 'stfc_aiida-feff' "
                  f"not found at {feff_dir}")
            sys.exit(1)
        if not widgets_dir.is_dir():
            print(f"ERROR: AIIDALAB_FEFF_DEV=1 but sibling directory 'alc-aiidalab-widgets' "
                  f"not found at {widgets_dir}")
            sys.exit(1)
        print("=== Dev mode: local sibling repos will be bind-mounted + editable-installed ===")
    else:
        print("=== Sibling dependencies will be installed from GitHub (main) ===")

    # 1. Locate and load config.toml
    config_dir = Path(click.get_app_dir("org.aiidalab.aiidalab_launch"))
    config_path = config_dir / "config.toml"

    if config_path.is_file():
        config = toml.load(config_path)
    else:
        config = {"default_profile": "default", "version": "2024.1020", "profiles": {}}

    if "profiles" not in config:
        config["profiles"] = {}

    # 2. Configure or create 'aiidalab-feff' profile
    profile_name = "aiidalab-feff"
    if profile_name not in config["profiles"]:
        print(f"Adding new profile '{profile_name}' to AiiDAlab Launch config...")
        # Determine non-conflicting port
        ports = [p.get("port", 8888) for p in config["profiles"].values()]
        port = max(ports) + 1 if ports else 8889
        config["profiles"][profile_name] = {
            "port": port,
            "default_apps": [],
            "system_user": "jovyan",
            "home_mount": f"aiidalab_{profile_name}_home",
        }

    profile = config["profiles"][profile_name]
    profile["image"] = "ghcr.io/stfc/alc-ux/base:py310"

    # Set up bind mounts. The app itself is ALWAYS bind-mounted (it must be
    # at /home/jovyan/apps/aiidalab-feff for AiiDAlab app discovery and is
    # editable-installed). The two sibling repos are ONLY bind-mounted in
    # dev mode; in default mode they are installed from GitHub.
    extra_mounts = [f"{repo_dir}:/home/jovyan/apps/aiidalab-feff:rw"]
    if dev_mode:
        extra_mounts.append(f"{feff_dir}:/tmp/src/stfc_aiida-feff:rw")
        extra_mounts.append(f"{widgets_dir}:/tmp/src/alc-aiidalab-widgets:rw")
    profile["extra_mounts"] = extra_mounts

    # Save config
    config_dir.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w") as fh:
        toml.dump(config, fh)
    print(f"Configured profile '{profile_name}' at {config_path}")

    # 3. Start the container
    #
    # ``--restart`` is required: switching between default and dev mode
    # changes the profile's extra_mounts, and a running container cannot
    # gain new mounts. With --restart, aiidalab-launch stops + recreates
    # the container when the configuration changed (home volume persists).
    # Without it, the old container keeps running and the /tmp/src/* mounts
    # are missing, so the editable installs below fail.
    # ``--no-browser`` keeps this script non-interactive; URLs are printed
    # at the end instead.
    print(f"\n=== Starting AiiDAlab instance '{profile_name}' ===")
    subprocess.run(
        ["aiidalab-launch", "start", "-p", profile_name, "--restart", "--no-browser"],
        check=True,
    )

    # The base image ships its own RabbitMQ + PostgreSQL (in the
    # "aiida-core-services" conda env), already running inside the container at
    # localhost:5672 / localhost:5432. No host-side broker or network bridging
    # is required, so we deliberately do NOT do that here.

    container_name = f"aiidalab_{profile_name}"
    runtime = detect_runtime(container_name)

    # Jupyter writes notebook checkpoints into a ".ipynb_checkpoints" directory
    # next to each notebook. On a fresh clone these are owned by the host user
    # and often mode 700, so jovyan (uid 1000) cannot traverse or write into
    # them and saving a notebook fails with "Permission denied". Make any such
    # pre-existing checkpoint directories world-writable so jovyan can save.
    chmod_paths = ["/home/jovyan/apps/aiidalab-feff"]
    if dev_mode:
        chmod_paths.append("/tmp/src/stfc_aiida-feff")
        chmod_paths.append("/tmp/src/alc-aiidalab-widgets")
    subprocess.run([
        runtime, "exec", "--user", "root", container_name,
        "find", *chmod_paths,
        "-name", ".ipynb_checkpoints", "-type", "d",
        "-exec", "chmod", "777", "{}", "+",
    ], check=False)

    # 4. Install dependencies inside the container.
    #
    # The app itself is ALWAYS editable-installed from the bind-mount.
    # The sibling dependencies depend on the mode:
    #   - Default: pip install git+https://github.com/stfc/<repo>.git (non-editable)
    #   - Dev (AIIDALAB_FEFF_DEV=1): pip install -e /tmp/src/<repo> (editable, bind-mounted)
    #
    # NOTE: this must run as root. The bind-mounted source trees are owned by the
    # host user, whose uid generally differs from the container's jovyan user
    # (uid 1000). jovyan therefore cannot write the generated *.egg-info into the
    # mounted source, which makes a normal editable install fail with
    # "Cannot update time stamp of directory ...". Running pip as root bypasses
    # the permission mismatch. The packages install into the shared base conda
    # env so they remain importable by jovyan.
    # flask-cors and flask-restful are declared as app dependencies in
    # pyproject.toml (needed by the aiida-explorer REST API), so they are pulled
    # in automatically via the app's own dependencies — no need to list them
    # explicitly here.
    print("\n=== Installing packages inside the container (as root) ===")
    sibling_targets = []
    if dev_mode:
        print("  Dev mode: editable-installing siblings from bind-mounts")
        sibling_targets = ["-e", "/tmp/src/stfc_aiida-feff",
                           "-e", "/tmp/src/alc-aiidalab-widgets"]
    else:
        print("  Installing siblings from GitHub main")
        sibling_targets = [_FEFF_GIT_URL, _WIDGETS_GIT_URL]

    install_cmd = [
        runtime,
        "exec",
        "--user",
        "root",
        container_name,
        "pip",
        "install",
        "--pre",
        "--no-cache-dir",
        "--no-user",
        *sibling_targets,
        "-e", "/home/jovyan/apps/aiidalab-feff",
    ]
    subprocess.run(install_cmd, check=True)

    # The AiiDAlab base image auto-starts the AiiDA daemon on container boot,
    # i.e. BEFORE the installs above ran. Those workers therefore booted
    # without the aiida_feff entry points registered, so submitting an
    # aiida_feff workchain fails with "ModuleNotFoundError: No module named
    # 'aiida_feff'" during bundle load. Restart the daemon so fresh workers
    # pick up the newly installed plugins. (setup-aiida.sh below only starts
    # the daemon if it is not already running, so it will skip — that's fine.)
    print("\n=== Restarting AiiDA daemon to load freshly installed plugins ===")
    subprocess.run([
        runtime, "exec", container_name,
        "verdi", "daemon", "restart",
    ], check=False)

    # 5. Start the AiiDA REST API for the aiida-explorer button
    print("\n=== Starting AiiDA REST API inside the container ===")
    subprocess.run([
        "aiidalab-launch", "exec", "-p", profile_name, "--",
        "bash", "/home/jovyan/apps/aiidalab-feff/containers/start_restapi.sh"
    ], check=True)

    # 6. Expose the REST API on a host port via a proxy container.
    #
    # The AiiDAlab container sits on the runtime's default "bridge" network,
    # where container-name DNS resolution is not available. So we create a
    # small user-defined network, attach the AiiDAlab container to it, and run
    # the socat proxy there so it can reach the container by name.
    print("\n=== Exposing AiiDA REST API on host port 5050 ===")
    proxy_name = "aiidalab-feff-restapi-proxy"
    proxy_network = "aiidalab-feff-net"

    subprocess.run(
        [runtime, "network", "create", proxy_network],
        check=False,
        stdout=subprocess.DEVNULL,
    )
    subprocess.run(
        [runtime, "network", "connect", proxy_network, container_name],
        check=False,
    )
    subprocess.run([runtime, "rm", "-f", proxy_name], check=False)
    subprocess.run([
        runtime,
        "run",
        "-d",
        "--name",
        proxy_name,
        "--network",
        proxy_network,
        "-p",
        "5050:5000",
        "alpine/socat",
        "TCP-LISTEN:5000,fork",
        f"TCP:{container_name}:5000",
    ], check=True)

    # 7. Configure AiiDA ( localhost computer, codes, and daemon )
    print("\n=== Running AiiDA configuration inside the container ===")
    setup_cmd = [
        "aiidalab-launch",
        "exec",
        "-p",
        profile_name,
        "--",
        "bash",
        "/home/jovyan/apps/aiidalab-feff/containers/setup-aiida.sh",
    ]
    subprocess.run(setup_cmd, check=True)

    # Patch the FEFF8l launcher shell script inside the container.
    #
    # xraylarch ships feff8l.sh with a "#!/bin/sh" shebang but uses the
    # bash-only variable ${BASH_SOURCE[0]} to locate its own directory. Under
    # /bin/sh this substitution is empty, so DIR ends up empty and each
    # feff8l_* binary is invoked from the job's working directory instead of
    # the larch/bin/linux64 directory -> every binary is "not found" and FEFF
    # produces no xmu.dat, so every calculation fails with exit status 310.
    # Fix: switch the shebang to bash so BASH_SOURCE works. (Inside the image
    # this file is root-owned, so the sed runs as root.) Idempotent.
    print("\n=== Patching FEFF8l launcher shell compatibility bug ===")
    subprocess.run([
        runtime, "exec", "--user", "root", container_name,
        "bash", "-lc",
        "set -e; F=$(command -v feff8l.sh || "
        "echo /opt/conda/lib/python3.10/site-packages/larch/bin/linux64/feff8l.sh); "
        "D=$(dirname \"$F\"); "
        "if head -1 \"$F\" | grep -q '#!/bin/sh'; then "
        "sed -i \"1s|#!/bin/sh|#!/usr/bin/env bash|\" \"$F\" && echo patched \"$F\"; "
        "else echo already-patched \"$F\"; fi",
    ], check=False)

    # 8. Retrieve URL
    try:
        print("\n=== Retrieving clickable URLs ===")
        status_proc = subprocess.run(
            ["aiidalab-launch", "status"],
            capture_output=True,
            text=True,
            check=False,
        )
        if status_proc.returncode == 0:
            # Extract the URL from status output (handles tabular status format)
            url = None
            for line in status_proc.stdout.splitlines():
                if "aiidalab-feff" in line and "http://" in line:
                    for part in line.split():
                        if part.startswith("http://") or part.startswith("https://"):
                            url = part
                            break
                    if url:
                        break

            if url:
                token = ""
                if "token=" in url:
                    token = url.split("?")[-1]

                # Format the distinct modes.
                # The Jupyter base_url is "/", and appmode registers its handler
                # at "/apps/<notebook_path_relative_to_notebook_dir>". Since the
                # app notebook lives under /home/jovyan/apps/aiidalab-feff/,
                # its path relative to notebook_dir is "apps/aiidalab-feff/main.ipynb"
                # and the appmode URL becomes "/apps/apps/aiidalab-feff/main.ipynb".
                # JupyterLab uses its own "/lab/tree/<relative_path>" route.
                app_url = f"http://localhost:{profile['port']}/apps/apps/aiidalab-feff/main.ipynb"
                lab_url = f"http://localhost:{profile['port']}/lab/tree/apps/aiidalab-feff/main.ipynb"
                if token:
                    app_url = f"{app_url}?{token}"
                    lab_url = f"{lab_url}?{token}"

                print("=================================================================")
                print("  AiiDAlab is ready! Click one of the links below to open:     ")
                print("")
                print("  1. Direct App Mode (Recommended):")
                print("     " + app_url)
                print("")
                print("  2. JupyterLab Editor Mode (to view/edit code):")
                print("     " + lab_url)
                print("=================================================================")
            else:
                print("AiiDAlab is running. Run 'aiidalab-launch status' to find the URL.")
        else:
            print("AiiDAlab is running. Run 'aiidalab-launch status' to find the URL.")
    except Exception as e:
        print(f"Note: Could not retrieve URL automatically: {e}")


if __name__ == "__main__":
    main()