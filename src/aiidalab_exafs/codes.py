"""Code provisioning and FEFF8L executable resolution for AiiDAlab EXAFS."""

from __future__ import annotations

import importlib.util
import os
import platform
import shutil
import subprocess
import sys
import warnings
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aiida.orm import Computer, InstalledCode


def find_larch_bin_dir() -> Path | None:
    """Locate the platform-specific larch binary directory."""
    system = platform.system().lower()
    if "linux" in system:
        subdir = "linux64"
    elif "darwin" in system:
        subdir = "darwin64"
    elif "windows" in system:
        subdir = "win64"
    else:
        subdir = "linux64"

    # 1. Search sys.path
    for p in sys.path:
        candidate = Path(p) / "larch" / "bin" / subdir
        if candidate.is_dir() and (candidate / "feff8l.sh").is_file():
            return candidate

    # 2. Search via importlib spec for larch
    try:
        spec = importlib.util.find_spec("larch")
        if spec and spec.submodule_search_locations:
            for loc in spec.submodule_search_locations:
                candidate = Path(loc) / "bin" / subdir
                if candidate.is_dir() and (candidate / "feff8l.sh").is_file():
                    return candidate
    except Exception:  # noqa: BLE001
        pass

    return None


def find_feff_script() -> Path | None:
    """Locate the feff8l.sh script bundled in xraylarch."""
    bin_dir = find_larch_bin_dir()
    if bin_dir is not None:
        script = bin_dir / "feff8l.sh"
        if script.is_file():
            return script
    return None


def feff8l_cli() -> int:
    """Console script entry point for ``exafs-feff8l``.

    Runs xraylarch's bundled ``feff8l.sh`` under bash. The script carries a
    ``#!/bin/sh`` shebang but uses ``${BASH_SOURCE[0]}`` to locate its own
    directory, so executing it directly leaves the module paths unset and FEFF
    exits with status 310.

    xraylarch also installs its own ``feff8l`` console script, which drives the
    same binaries from Python. We deliberately do *not* use it: it writes
    ``feff8l.log`` instead of FEFF's ``log.dat``, and aiida-feff reads the FEFF
    version banner out of ``log.dat``. Without it, potentials-only runs fail
    with exit 311 ("did not start") even though pot.pad and phase.pad were
    written correctly, and ordinary runs silently lose their recorded FEFF
    version. The entry point is named ``exafs-feff8l`` rather than ``feff8l``
    so it cannot shadow, or be shadowed by, xraylarch's script.
    """
    script = find_feff_script()
    if script is None or not script.is_file():
        sys.stderr.write("ERROR: feff8l.sh not found in the larch package.\n")
        return 1

    bash_exe = shutil.which("bash") or "/bin/bash"
    env = os.environ.copy()
    bin_dir = script.parent
    env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
    if platform.system().lower() == "darwin":
        env["DYLD_LIBRARY_PATH"] = f"{bin_dir}:{env.get('DYLD_LIBRARY_PATH', '')}"
    else:
        env["LD_LIBRARY_PATH"] = f"{bin_dir}:{env.get('LD_LIBRARY_PATH', '')}"

    return subprocess.run([bash_exe, str(script), *sys.argv[1:]], env=env, check=False).returncode


def get_feff_executable() -> str:
    """Return the path to the preferred FEFF8L executable.

    Prefers our ``exafs-feff8l`` wrapper, which runs the bundled ``feff8l.sh``
    under bash so that FEFF writes ``log.dat`` and aiida-feff can read the
    version banner. See :func:`feff8l_cli` for why xraylarch's own ``feff8l``
    console script is not used.
    """
    wrapper = shutil.which("exafs-feff8l")
    if wrapper is not None:
        return wrapper

    script = find_feff_script()
    if script is not None:
        return str(script)

    return "exafs-feff8l"


def ensure_profile() -> None:
    """Load the default AiiDA profile unless the caller already loaded one.

    AiiDA does not load a profile implicitly, so these helpers must do it
    themselves to work from a container boot hook, where nothing has called
    ``load_profile()`` yet. Inside a notebook the profile is already loaded and
    this is a no-op.
    """
    from aiida.manage import get_manager

    if get_manager().get_profile() is None:
        from aiida import load_profile

        load_profile()


def get_or_create_localhost_computer() -> Computer:
    """Return the localhost AiiDA computer, creating and configuring it if needed."""
    from aiida.common.exceptions import NotExistent
    from aiida.orm import Computer, load_computer

    ensure_profile()

    try:
        return load_computer("localhost")
    except NotExistent:
        pass

    work_dir = Path.home() / "aiida-exafs-runs"
    work_dir.mkdir(parents=True, exist_ok=True)

    computer = Computer(
        label="localhost",
        hostname="localhost",
        workdir=str(work_dir),
        transport_type="core.local",
        scheduler_type="core.direct",
    )
    computer.store()
    computer.set_minimum_job_poll_interval(0)
    computer.set_default_mpiprocs_per_machine(1)
    computer.configure()
    return computer


def _reuse_or_retire_code(code_label: str, computer_label: str, exe: str) -> InstalledCode | None:
    """Return an existing code if it already points at ``exe``, else retire it.

    A stored AiiDA code is immutable, so the only way to correct one whose
    executable has moved is to relabel it out of the way and create a
    replacement. Returning the stale code instead is how a corrected image
    still runs the old executable against a persistent ``$HOME``.
    """
    from aiida.common.exceptions import NotExistent
    from aiida.orm import InstalledCode, load_code

    try:
        code = load_code(f"{code_label}@{computer_label}")
    except NotExistent:
        return None

    assert isinstance(code, InstalledCode)
    if str(code.filepath_executable) == str(exe):
        return code

    retired = f"{code_label}-legacy-{code.pk}"
    code.label = retired
    warnings.warn(
        f"Existing code {code_label}@{computer_label} pointed at "
        f"{code.filepath_executable}, not {exe}. It has been relabelled "
        f"{retired} and a replacement created. Calculations already run "
        "with it keep their provenance; new ones will use the replacement.",
        stacklevel=3,
    )
    return None


def setup_feff_code(
    computer_label: str = "localhost",
    code_label: str = "feff",
    executable_path: str | None = None,
) -> tuple[InstalledCode, bool]:
    """Idempotently configure the FEFF code on the specified computer.

    An existing code that points at a different executable is retired rather
    than reused. This matters because a code registered against xraylarch's
    ``feff8l`` console script produces no ``log.dat`` and makes every
    potentials-only run fail with exit 311.

    Returns:
        tuple of (InstalledCode, created_bool)
    """
    from aiida.orm import InstalledCode

    ensure_profile()

    exe = executable_path or get_feff_executable()

    existing = _reuse_or_retire_code(code_label, computer_label, exe)
    if existing is not None:
        return existing, False

    if computer_label == "localhost":
        computer = get_or_create_localhost_computer()
    else:
        from aiida.orm import load_computer

        computer = load_computer(computer_label)

    code = InstalledCode(
        label=code_label,
        computer=computer,
        filepath_executable=exe,
        default_calc_job_plugin="feff.feff",
        description="FEFF8L from xraylarch",
    )
    code.store()
    return code, True


def setup_python3_code(
    computer_label: str = "localhost",
    code_label: str = "python3",
    executable_path: str | None = None,
) -> tuple[InstalledCode, bool]:
    """Idempotently configure the python3 code on the specified computer.

    Retires a code whose executable has moved, for the same reason as
    :func:`setup_feff_code`: the interpreter path changes whenever the image's
    conda environment is rebuilt, and a stored code cannot be edited.

    Returns:
        tuple of (InstalledCode, created_bool)
    """
    from aiida.orm import InstalledCode

    ensure_profile()

    exe = executable_path or sys.executable

    existing = _reuse_or_retire_code(code_label, computer_label, exe)
    if existing is not None:
        return existing, False

    if computer_label == "localhost":
        computer = get_or_create_localhost_computer()
    else:
        from aiida.orm import load_computer

        computer = load_computer(computer_label)

    code = InstalledCode(
        label=code_label,
        computer=computer,
        filepath_executable=exe,
        description="Python 3 for FEFF path aggregation",
    )
    code.store()
    return code, True
