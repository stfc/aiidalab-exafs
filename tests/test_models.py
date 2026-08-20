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


def test_workflow_parameter_validation():
    """FeffParametersWidget validates required parameters and rejects invalid ones."""
    from aiidalab_feff.workflow import FeffParametersWidget

    model = WorkflowModel()
    widget = FeffParametersWidget(model)

    widget.radius.value = -1.0
    errors = widget.validate()
    assert any("Radius" in err for err in errors)


class DummyXas:
    """Mock XasData for unit tests without AiiDA DB."""

    def __init__(self, k, chi):
        self._arrays = {"k": k, "chi_k": chi}

    def get_array(self, name):
        return self._arrays[name]


def test_average_xas_on_common_k_nan_aware():
    """_average_xas_on_common_k uses NaN-aware statistics."""
    import numpy as np

    from aiidalab_feff.results import _average_xas_on_common_k

    x1 = DummyXas(np.array([1.0, 2.0, 3.0]), np.array([0.1, 0.2, 0.3]))
    x2 = DummyXas(np.array([1.0, 2.0]), np.array([0.15, 0.25]))

    k_ref, chi_avg, chi_std = _average_xas_on_common_k([x1, x2])
    assert np.allclose(k_ref, [1.0, 2.0, 3.0])
    assert np.allclose(chi_avg[:2], [0.125, 0.225])
    assert np.allclose(chi_avg[2], 0.3)
    assert np.isnan(chi_std[2])  # Only 1 sample at k=3.0 gives NaN std




