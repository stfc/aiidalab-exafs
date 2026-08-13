"""Common file handling utilities for AiiDAlab FEFF."""

from __future__ import annotations

from io import StringIO
from pathlib import Path

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
    try:
        # Try reading with the format first, or fall back to auto-detection
        atoms = ase_read(StringIO(text), format=fmt)
    except Exception:
        try:
            atoms = ase_read(StringIO(text))
        except Exception as exc:
            msg = f"Could not parse file '{filename}' with ASE: {exc}"
            raise ValueError(msg) from exc

    if isinstance(atoms, list):
        atoms = atoms[0]

    return ase_atoms_to_structure_data(atoms, label=Path(filename).stem)


def read_xyz_to_trajectory_data(file_content: bytes, filename: str) -> TrajectoryData:
    """Read a multi-frame file and return an AiiDA TrajectoryData node."""
    text = file_content.decode("utf-8", errors="ignore")
    fmt = _guess_ase_format(file_content, filename)
    try:
        atoms_list = ase_read(StringIO(text), index=":", format=fmt)
    except Exception:
        try:
            atoms_list = ase_read(StringIO(text), index=":")
        except Exception as exc:
            msg = f"Could not parse trajectory file '{filename}' with ASE: {exc}"
            raise ValueError(msg) from exc

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


def _guess_ase_format(file_content: bytes, filename: str) -> str:
    """Return an ASE format, including header-based LAMMPS dump detection."""
    if b"ITEM: TIMESTEP" in file_content[:4096]:
        return "lammps-dump-text"
    return Path(filename).suffix.lstrip(".").lower()


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


def build_step_indices(n_frames: int, stride: int) -> list[int]:
    """Return frame indices from 0 to n_frames with a given stride."""
    return list(range(0, n_frames, stride))
