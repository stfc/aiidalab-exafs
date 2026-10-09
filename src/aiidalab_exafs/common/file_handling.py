"""Common file handling utilities for AiiDAlab FEFF."""

from __future__ import annotations

import logging
from io import StringIO
from pathlib import Path
from typing import Any

import ase
import numpy as np
from aiida.orm import StructureData, TrajectoryData
from ase.io import read as ase_read


def ase_atoms_to_structure_data(atoms: ase.Atoms, label: str | None = None) -> StructureData:
    """Convert an ASE Atoms object to an AiiDA StructureData node."""
    structure = StructureData()
    structure.set_cell(atoms.cell)
    structure.set_pbc(atoms.pbc)
    structure.set_ase(atoms)
    if label:
        structure.label = label
    return structure


def read_cif_xyz_to_structure_data(file_content: bytes, filename: str) -> StructureData:
    """Read any file format supported by ASE and return a StructureData node.

    Parameters
    ----------
    file_content : bytes
        The uploaded file content.
    filename : str
        Original filename, used for the label and to guess the format.

    Returns:
    -------
    StructureData
    """
    text = file_content.decode("utf-8", errors="ignore")
    fmt = _guess_ase_format(file_content, filename)
    stream = StringIO(text)
    stream.name = filename
    try:
        # Let ASE detect the format (e.g. extxyz for .xyz), falling back to plain xyz
        atoms = ase_read(stream, format=fmt)
    except Exception as orig_exc:
        try:
            stream.seek(0)
            atoms = ase_read(stream, format="xyz")
        except Exception:
            msg = f"Could not parse file '{filename}' with ASE: {orig_exc}"
            raise ValueError(msg) from orig_exc

    if isinstance(atoms, list):
        atoms = atoms[0]

    return ase_atoms_to_structure_data(atoms, label=Path(filename).stem)


def read_xyz_to_trajectory_data(file_content: bytes, filename: str) -> TrajectoryData:
    """Read a multi-frame file and return an AiiDA TrajectoryData node."""
    text = file_content.decode("utf-8", errors="ignore")
    fmt = _guess_ase_format(file_content, filename)
    stream = StringIO(text)
    stream.name = filename
    try:
        atoms_list = ase_read(stream, index=":", format=fmt)
    except Exception as orig_exc:
        try:
            stream.seek(0)
            atoms_list = ase_read(stream, index=":", format="xyz")
        except Exception:
            msg = f"Could not parse trajectory file '{filename}' with ASE: {orig_exc}"
            raise ValueError(msg) from orig_exc

    if not isinstance(atoms_list, list) or len(atoms_list) == 0:
        msg = f"File {filename} did not contain multiple frames."
        raise ValueError(msg)

    trajectory = ase_atoms_list_to_trajectory_data(atoms_list)
    trajectory.label = Path(filename).stem
    return trajectory


def read_file_list_to_structures(
    file_list: list[tuple[str, bytes]],
) -> dict[str, StructureData]:
    """Convert a list of uploaded files to a dict of StructureData nodes.

    Parameters
    ----------
    file_list : list of (filename, content) tuples
        Uploaded files, all expected to be CIF or XYZ.

    Returns:
    -------
    dict[str, StructureData]
        Sanitised filename stem → StructureData.
    """
    structures: dict[str, StructureData] = {}
    for filename, content in file_list:
        structure = read_cif_xyz_to_structure_data(content, filename)
        key = _sanitise_key(Path(filename).stem)
        if key in structures:
            msg = f"Duplicate sanitised filename stem: {key}"
            raise ValueError(msg)
        structures[key] = structure
    return structures


def _sanitise_key(stem: str) -> str:
    """Sanitise a filename stem to be a valid dictionary key."""
    return "".join(c if c.isalnum() or c in "_-" else "_" for c in stem).rstrip("_")


def _guess_ase_format(file_content: bytes, filename: str) -> str | None:
    """Return an ASE format, including header-based LAMMPS dump detection."""
    if b"ITEM: TIMESTEP" in file_content[:4096]:
        return "lammps-dump-text"
    return None


def ase_atoms_list_to_trajectory_data(atoms_list: list[ase.Atoms]) -> TrajectoryData:
    """Convert equally shaped ASE frames to a TrajectoryData without intermediate nodes."""
    symbols = atoms_list[0].get_chemical_symbols()
    pbc = (
        bool(atoms_list[0].pbc[0]),
        bool(atoms_list[0].pbc[1]),
        bool(atoms_list[0].pbc[2]),
    )
    for atoms in atoms_list[1:]:
        if atoms.get_chemical_symbols() != symbols:
            msg = "All trajectory frames must contain the same atoms in the same order."
            raise ValueError(msg)
        if tuple(bool(value) for value in atoms.pbc) != pbc:
            msg = "All trajectory frames must use the same periodic boundary conditions."
            raise ValueError(msg)

    trajectory = TrajectoryData()
    trajectory_kwargs = {
        "symbols": symbols,
        "positions": np.asarray([atoms.positions for atoms in atoms_list]),
        "cells": np.asarray([atoms.cell.array for atoms in atoms_list]),
    }
    try:
        trajectory.set_trajectory(**trajectory_kwargs, pbc=pbc)
    except TypeError as exc:
        if "unexpected keyword argument 'pbc'" not in str(exc):
            raise
        trajectory.set_trajectory(**trajectory_kwargs)
    return trajectory


logger = logging.getLogger(__name__)


def build_step_indices(n_frames: int, stride: int) -> list[int]:
    """Return frame indices from 0 to n_frames with a given stride."""
    return list(range(0, n_frames, stride))


def _find_in_outgoing(node: Any) -> Any:
    """Helper to locate archive or path contributions in node outgoing return links."""
    if hasattr(node, "base") and hasattr(node.base, "links"):
        try:
            from aiida.common.links import LinkType

            # Query RETURN links (workchain outputs) to avoid loading hundreds of child jobs
            links_mgr = node.base.links
            try:
                outgoing = links_mgr.get_outgoing(link_type=LinkType.RETURN).all()
            except TypeError:
                outgoing = links_mgr.get_outgoing().all()

            for label in ("archive", "path_contributions"):
                for link in outgoing:
                    if getattr(link, "link_label", None) == label:
                        return link.node

            for link in outgoing:
                nt = str(getattr(link.node, "node_type", "")).lower()
                if "archive" in nt or "pathcontributions" in nt:
                    return link.node
                if "singlefile" in nt and getattr(link.node, "filename", "").endswith(
                    (".h5", ".hdf5")
                ):
                    return link.node
        except Exception:
            pass
    return None


def find_combined_h5_node(run_or_node: Any) -> Any:  # noqa: PLR0911
    """Locate the combined HDF5 data node (ExafsArchiveData or PathContributionsData) for a run.

    Parameters
    ----------
    run_or_node : Any
        A WorkChainNode, ProcessNode, node PK (int or str),
        ExafsArchiveData, PathContributionsData, or ResultsModel.

    Returns
    -------
    Node | None
        The AiiDA node containing the combined .h5 archive or path contributions,
        or None if not found.
    """
    if run_or_node is None:
        return None

    # Check ResultsModel
    if hasattr(run_or_node, "archive") and run_or_node.archive is not None:
        return run_or_node.archive
    if hasattr(run_or_node, "path_contributions") and run_or_node.path_contributions is not None:
        return run_or_node.path_contributions
    if hasattr(run_or_node, "process_node") and run_or_node.process_node is not None:
        return find_combined_h5_node(run_or_node.process_node)

    # Check PK (int or numeric string)
    if isinstance(run_or_node, int) or (isinstance(run_or_node, str) and run_or_node.isdigit()):
        try:
            from aiida.orm import load_node

            run_or_node = load_node(int(run_or_node))
        except Exception:
            return None

    # Direct data node check
    node_type = str(getattr(run_or_node, "node_type", "")).lower()
    if "archive" in node_type or "pathcontributions" in node_type:
        return run_or_node
    if "singlefile" in node_type and getattr(run_or_node, "filename", "").endswith(
        (".h5", ".hdf5")
    ):
        return run_or_node

    # Check outputs namespace on WorkChainNode / CalcJobNode
    outputs = getattr(run_or_node, "outputs", None)
    if outputs is not None:
        arch = getattr(outputs, "archive", None) or getattr(outputs, "path_contributions", None)
        if arch is not None:
            return arch

    return _find_in_outgoing(run_or_node)


def get_combined_h5_bytes(h5_or_run_node: Any) -> bytes | None:
    """Extract raw bytes of the combined HDF5 file from a node or run.

    Parameters
    ----------
    h5_or_run_node : Any
        A data node (ExafsArchiveData, PathContributionsData, SinglefileData)
        or a run node (WorkChainNode) whose combined .h5 should be retrieved.

    Returns
    -------
    bytes | None
        The raw bytes of the .h5 file, or None if unavailable.
    """
    if h5_or_run_node is None:
        return None

    # First resolve target data node if a run/workchain/model was passed
    target = find_combined_h5_node(h5_or_run_node) or h5_or_run_node

    try:
        # 1. Standard AiiDA file open context manager (SinglefileData, ExafsArchiveData)
        if hasattr(target, "open"):
            with target.open(mode="rb") as handle:
                return bytes(handle.read())
        # 2. PathContributionsData / custom store with _raw()
        if hasattr(target, "_raw"):
            raw = target._raw()
            if isinstance(raw, (bytes, bytearray)):
                return bytes(raw)
        # 3. Direct AiiDA repository content
        if hasattr(target, "base") and hasattr(target.base, "repository"):
            repo = target.base.repository
            fn = getattr(target, "filename", None)
            if fn and fn in repo.list_object_names():
                return bytes(repo.get_object_content(fn, mode="rb"))
            for name in repo.list_object_names():
                if name.endswith((".h5", ".hdf5")):
                    return bytes(repo.get_object_content(name, mode="rb"))
    except Exception as exc:
        logger.warning("Could not read h5 bytes from %s: %s", target, exc)

    return None


def export_combined_h5(run_or_node: Any, destination: str | Path | None = None) -> Path:
    """Save the combined .h5 file for any given run to local disk using streaming.

    Parameters
    ----------
    run_or_node : Any
        A WorkChainNode, process node, PK, or archive data node.
    destination : str | Path | None, optional
        Target file path or directory. If None or directory, a default
        filename 'feff-run-<pk>-combined.h5' is used.

    Returns
    -------
    Path
        The path of the written .h5 file.

    Raises
    -------
    FileNotFoundError
        If no combined .h5 archive or path contributions node exists for the run.
    """
    import shutil

    h5_node = find_combined_h5_node(run_or_node)
    if h5_node is None:
        raise FileNotFoundError(f"No combined .h5 file found for run: {run_or_node}")

    proc_node = getattr(run_or_node, "process_node", None) or run_or_node
    pk = getattr(proc_node, "pk", None) or getattr(h5_node, "pk", "unknown")
    default_name = f"feff-run-{pk}-combined.h5"

    if destination is None:
        out_path = Path.cwd() / default_name
    else:
        dest_p = Path(destination)
        if dest_p.is_dir():
            out_path = dest_p / default_name
        else:
            dest_p.parent.mkdir(parents=True, exist_ok=True)
            out_path = dest_p

    # Stream file to disk to avoid multi-hundred-megabyte RAM allocations
    written = False
    try:
        if hasattr(h5_node, "open"):
            with h5_node.open(mode="rb") as src, out_path.open("wb") as dst:
                shutil.copyfileobj(src, dst)
                written = True
        elif hasattr(h5_node, "base") and hasattr(h5_node.base, "repository"):
            repo = h5_node.base.repository
            fn = getattr(h5_node, "filename", None)
            target_fn = None
            if fn and fn in repo.list_object_names():
                target_fn = fn
            else:
                for name in repo.list_object_names():
                    if name.endswith((".h5", ".hdf5")):
                        target_fn = name
                        break
            if target_fn:
                with repo.open(target_fn, mode="rb") as src, out_path.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
                    written = True
    except Exception as exc:
        logger.debug("Streaming export failed, falling back to bytes: %s", exc)

    if not written:
        data = get_combined_h5_bytes(h5_node)
        if not data:
            raise FileNotFoundError(f"Combined .h5 node {h5_node} contains no data.")
        out_path.write_bytes(data)

    if out_path.stat().st_size == 0:
        out_path.unlink(missing_ok=True)
        raise FileNotFoundError(f"Combined .h5 node {h5_node} produced an empty file.")

    return out_path
