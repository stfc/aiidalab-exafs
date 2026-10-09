#!/usr/bin/env python3
"""Automated launcher for aiidalab-exafs using the official aiidalab-launch tool.

It configures the AiiDAlab profile with correct mount paths, starts the
container, installs the editable packages, and configures AiiDA.

Sibling dependencies (md-exafs, aiida-feff, alc-aiidalab-widgets)
are by default installed from PyPI. Set the environment variable
``AIIDALAB_EXAFS_DEV=1`` or pass ``--dev`` to switch to development mode:
sibling directories ``../alc-dls-exafs``, ``../stfc_aiida-feff``, and
``../alc-aiidalab-widgets`` are then bind-mounted into the container and
editable-installed.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import click
import toml

_FEFF_PYPI = "aiida-feff>=0.1.0a1"
_WIDGETS_PYPI = "alc-aiidalab-widgets>=0.1.0"
_MD_EXAFS_PYPI = "md-exafs>=0.3.0,<0.4"


def detect_runtime(container_name: str) -> str:
    """Return 'docker' or 'podman' depending on which runtime owns the container."""
    for runtime in ("docker", "podman"):
        proc = subprocess.run(
            [runtime, "inspect", container_name],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0:
            return runtime
    print(
        f"ERROR: could not find container '{container_name}' under docker or podman. "
        "Is the AiiDAlab instance running?"
    )
    sys.exit(1)


def _resolve_sibling_repos(workspace_root: Path, dev_mode: bool) -> dict[str, Path]:
    """Return a mapping of found sibling repo names to their local paths."""
    candidates = {
        "alc-dls-exafs": [workspace_root / "alc-dls-exafs"],
        "stfc_aiida-feff": [workspace_root / "stfc_aiida-feff", workspace_root / "aiida-feff"],
        "alc-aiidalab-widgets": [workspace_root / "alc-aiidalab-widgets"],
    }
    found: dict[str, Path] = {}
    for name, paths in candidates.items():
        for path in paths:
            if path.is_dir():
                found[name] = path
                break

    if not dev_mode:
        print("=== Non-dev mode: sibling dependencies will be installed from PyPI ===")
        return {}

    for name, path in found.items():
        print(
            f"=== Dev mode: found sibling {name!r} at {path} (will bind-mount + editable-install) ==="
        )
    return found


@click.command()
@click.option("--profile", "-p", default=None, help="AiiDAlab profile name.")
@click.option("--port", default=None, type=int, help="Host port to bind.")
@click.option("--home-mount", default=None, help="Docker volume name for /home/jovyan.")
@click.option(
    "--dev/--no-dev",
    default=None,
    help="Enable/disable dev mode (bind-mount local sibling repos).",
)
def main(profile: str | None, port: int | None, home_mount: str | None, dev: bool | None):
    """Configure, start, and initialize the AiiDAlab Launch container."""
    local_bin = str(Path.home() / ".local" / "bin")
    if local_bin not in os.environ.get("PATH", ""):
        os.environ["PATH"] = f"{local_bin}:{os.environ.get('PATH', '')}"

    script_dir = Path(__file__).resolve().parent
    repo_dir = script_dir.parent.parent
    workspace_root = repo_dir.parent

    if dev is not None:
        dev_mode = dev
    else:
        dev_mode = os.environ.get(
            "AIIDALAB_EXAFS_DEV", os.environ.get("AIIDALAB_FEFF_DEV", "0")
        ).strip().lower() in ("1", "true")

    local_siblings = _resolve_sibling_repos(workspace_root, dev_mode)

    # 1. Locate and load config.toml
    config_dir = Path(click.get_app_dir("org.aiidalab.aiidalab_launch"))
    config_path = config_dir / "config.toml"

    if config_path.is_file():
        config = toml.load(config_path)
    else:
        config = {"default_profile": "default", "version": "2024.1020", "profiles": {}}

    if "profiles" not in config:
        config["profiles"] = {}

    # 2. Configure or update profile
    profile_name = (
        profile
        or os.environ.get("AIIDALAB_EXAFS_PROFILE")
        or os.environ.get("AIIDALAB_PROFILE", "aiidalab-exafs")
    )
    if profile_name not in config["profiles"]:
        print(f"Adding new profile '{profile_name}' to AiiDAlab Launch config...")
        config_port = port or int(
            os.environ.get("AIIDALAB_EXAFS_PORT", os.environ.get("AIIDALAB_PORT", "0"))
        )
        if not config_port:
            ports = [p.get("port", 8888) for p in config["profiles"].values()]
            config_port = max(ports) + 1 if ports else 8889
        config_home = home_mount or os.environ.get(
            "AIIDALAB_HOME_MOUNT", f"aiidalab_{profile_name}_home"
        )
        config["profiles"][profile_name] = {
            "port": config_port,
            "default_apps": [],
            "system_user": "jovyan",
            "home_mount": config_home,
        }
    else:
        if port:
            config["profiles"][profile_name]["port"] = port
        if home_mount:
            config["profiles"][profile_name]["home_mount"] = home_mount

    prof = config["profiles"][profile_name]
    prof["image"] = "aiidalab/full-stack:edge"

    extra_mounts = [
        f"{repo_dir}:/home/jovyan/apps/exafs:rw",
        f"{repo_dir}:/home/jovyan/apps/aiidalab-exafs:rw",
    ]
    if dev_mode:
        for name, p in local_siblings.items():
            extra_mounts.append(f"{p}:/tmp/src/{name}:rw")
    prof["extra_mounts"] = extra_mounts

    config_dir.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w") as fh:
        toml.dump(config, fh)
    print(f"Configured profile '{profile_name}' at {config_path}")

    # 3. Start the container
    print(f"\n=== Starting AiiDAlab instance '{profile_name}' ===")
    subprocess.run(
        ["aiidalab-launch", "start", "-p", profile_name, "--restart", "--no-browser"],
        check=True,
    )

    container_name = f"aiidalab_{profile_name}"
    runtime = detect_runtime(container_name)

    # Make checkpoints world-writable
    chmod_paths = ["/home/jovyan/apps/exafs"]
    if dev_mode:
        for name in local_siblings:
            chmod_paths.append(f"/tmp/src/{name}")
    subprocess.run(
        [
            runtime,
            "exec",
            "--user",
            "root",
            container_name,
            "find",
            *chmod_paths,
            "-name",
            ".ipynb_checkpoints",
            "-type",
            "d",
            "-exec",
            "chmod",
            "777",
            "{}",
            "+",
        ],
        check=False,
    )

    # 4. Install dependencies inside container
    print("\n=== Installing packages inside the container (as root) ===")
    sibling_targets = []
    if dev_mode:
        if "alc-dls-exafs" in local_siblings:
            print("  Dev mode: editable-installing alc-dls-exafs from bind-mount")
            sibling_targets.extend(["-e", "/tmp/src/alc-dls-exafs"])
        else:
            sibling_targets.append(_MD_EXAFS_PYPI)

        if "stfc_aiida-feff" in local_siblings:
            print("  Dev mode: editable-installing stfc_aiida-feff from bind-mount")
            sibling_targets.extend(["-e", "/tmp/src/stfc_aiida-feff"])
        else:
            sibling_targets.append(_FEFF_PYPI)

        if "alc-aiidalab-widgets" in local_siblings:
            print("  Dev mode: editable-installing alc-aiidalab-widgets from bind-mount")
            sibling_targets.extend(["-e", "/tmp/src/alc-aiidalab-widgets"])
        else:
            sibling_targets.append(_WIDGETS_PYPI)
    else:
        print("  Installing siblings from PyPI")
        sibling_targets = [_MD_EXAFS_PYPI, _FEFF_PYPI, _WIDGETS_PYPI]

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
        "-e",
        "/home/jovyan/apps/exafs",
    ]
    subprocess.run(install_cmd, check=True)

    # 5. Configure AiiDA (localhost computer, codes, and daemon)
    print("\n=== Running AiiDA configuration inside the container ===")
    setup_cmd = [
        "aiidalab-launch",
        "exec",
        "-p",
        profile_name,
        "--",
        "bash",
        "/home/jovyan/apps/exafs/docker/base/setup-aiida.sh",
    ]
    subprocess.run(setup_cmd, check=True)

    # 6. Retrieve URL
    try:
        print("\n=== Retrieving clickable URLs ===")
        status_proc = subprocess.run(
            ["aiidalab-launch", "status"],
            capture_output=True,
            text=True,
            check=False,
        )
        if status_proc.returncode == 0:
            url = None
            for line in status_proc.stdout.splitlines():
                if profile_name in line and "http://" in line:
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

                app_url = f"http://localhost:{prof['port']}/apps/apps/exafs/main.ipynb"
                lab_url = f"http://localhost:{prof['port']}/lab/tree/apps/exafs/main.ipynb"
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
