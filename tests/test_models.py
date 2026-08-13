"""Tests for AiiDAlab FEFF models."""

from __future__ import annotations

from aiidalab_feff.common.file_handling import _guess_ase_format
from aiidalab_feff.input import _parse_indices, _upload_error_message
from aiidalab_feff.models import InputModel, WorkflowModel


def test_input_model_single_structure():
    """Single structure is reported as a one-element ensemble."""
    model = InputModel()
    assert not model.is_ensemble()

    model.structure = None  # explicit unset state is valid
    assert not model.is_ensemble()


def test_input_model_ensemble():
    """Multiple structures are reported as an ensemble."""
    model = InputModel()
    model.structures = {"frame_0000": "a", "frame_0001": "b"}  # type: ignore[assignment]
    assert model.is_ensemble()
    assert not model.is_single_structure()


def test_workflow_model_batch():
    """Batch is enabled only when batch_size > 1."""
    model = WorkflowModel()
    assert not model.is_batch()

    model.batch_size = 50
    model.n_workers = 8
    assert model.is_batch()


def test_parse_indices():
    """Index parsing handles comma lists and slices."""
    assert _parse_indices("0,5,10") == [0, 5, 10]
    assert _parse_indices("0:6:2") == [0, 2, 4]
    assert _parse_indices("") == []


def test_upload_error_message_is_actionable_and_escapes_details():
    """Upload failures show a visible alert without rendering file data as HTML."""
    message = _upload_error_message("<bad>.cif", "structure", ValueError("<invalid>"))

    assert "role='alert'" in message
    assert "Could not load &lt;bad&gt;.cif." in message
    assert "valid structure file" in message
    assert "Show technical details" in message
    assert "&lt;invalid&gt;" in message


def test_lammps_dump_header_selects_ase_text_reader():
    """LAMMPS dump files do not have a reliably distinguishable suffix."""
    dump_header = b"ITEM: TIMESTEP\n0\nITEM: NUMBER OF ATOMS\n1\n"

    assert _guess_ase_format(dump_header, "npt_traj.dump") == "lammps-dump-text"



