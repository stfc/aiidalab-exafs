"""Tests for AiiDAlab FEFF models."""

from __future__ import annotations

from aiidalab_exafs.common.file_handling import _guess_ase_format
from aiidalab_exafs.input import _parse_indices, _upload_error_message
from aiidalab_exafs.models import InputModel, WorkflowModel


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
    assert _guess_ase_format(b"2\n\nC 0 0 0\nC 1 1 1\n", "foo.xyz") is None


def test_read_cif_xyz_extxyz_with_xyz_extension():
    """extxyz files with .xyz extension parse unit cell and PBC correctly."""
    from unittest.mock import MagicMock, patch

    import numpy as np

    from aiidalab_exafs.common.file_handling import read_cif_xyz_to_structure_data

    content = (
        b"2\n"
        b'Lattice="5.0 0.0 0.0 0.0 5.0 0.0 0.0 0.0 5.0" Properties=species:S:1:pos:R:3 pbc="T T T"\n'
        b"C 0.0 0.0 0.0\n"
        b"C 1.0 1.0 1.0\n"
    )

    with patch("aiidalab_exafs.common.file_handling.StructureData") as mock_sd_cls:
        mock_sd = MagicMock()
        mock_sd_cls.return_value = mock_sd
        read_cif_xyz_to_structure_data(content, "structure.xyz")

        cell = mock_sd.set_cell.call_args[0][0]
        pbc = mock_sd.set_pbc.call_args[0][0]
        assert np.allclose(cell, np.diag([5.0, 5.0, 5.0]))
        assert np.all(pbc)


def test_read_cif_xyz_fallback_to_plain_xyz():
    """Files with malformed extxyz headers fall back to plain xyz parsing."""
    from unittest.mock import MagicMock, patch

    import numpy as np

    from aiidalab_exafs.common.file_handling import read_cif_xyz_to_structure_data

    content = b"2\nProperties=species:S:1:pos:R:bad_number\nC 0.0 0.0 0.0\nC 1.0 1.0 1.0\n"

    with patch("aiidalab_exafs.common.file_handling.StructureData") as mock_sd_cls:
        mock_sd = MagicMock()
        mock_sd_cls.return_value = mock_sd
        read_cif_xyz_to_structure_data(content, "plain.xyz")

        cell = mock_sd.set_cell.call_args[0][0]
        pbc = mock_sd.set_pbc.call_args[0][0]
        assert np.allclose(cell, np.zeros((3, 3)))
        assert not np.any(pbc)


def test_read_xyz_to_trajectory_extxyz_with_xyz_extension():
    """Multi-frame extxyz files with .xyz extension parse unit cells for all frames."""
    from unittest.mock import MagicMock, patch

    import numpy as np

    from aiidalab_exafs.common.file_handling import read_xyz_to_trajectory_data

    frame = (
        b"2\n"
        b'Lattice="5.0 0.0 0.0 0.0 5.0 0.0 0.0 0.0 5.0" Properties=species:S:1:pos:R:3 pbc="T T T"\n'
        b"C 0.0 0.0 0.0\n"
        b"C 1.0 1.0 1.0\n"
    )
    content = frame + frame

    with patch("aiidalab_exafs.common.file_handling.TrajectoryData") as mock_td_cls:
        mock_td = MagicMock()
        mock_td_cls.return_value = mock_td
        read_xyz_to_trajectory_data(content, "traj.xyz")

        kwargs = mock_td.set_trajectory.call_args.kwargs
        assert kwargs["cells"].shape == (2, 3, 3)
        assert np.allclose(kwargs["cells"][0], np.diag([5.0, 5.0, 5.0]))
        assert kwargs["pbc"] == (True, True, True)


def test_workflow_parameter_validation():
    """FeffParametersWidget validates required parameters and rejects invalid ones."""
    from aiidalab_exafs.workflow import FeffParametersWidget

    model = WorkflowModel()
    widget = FeffParametersWidget(model)

    widget.radius.value = -1.0
    errors = widget.validate()
    assert any("Radius" in err for err in errors)


def test_workflow_advanced_defaults_and_reset():
    """FeffParametersWidget exposes advanced cards with defaults and supports resetting."""
    from aiidalab_exafs.workflow import FeffParametersWidget

    model = WorkflowModel()
    widget = FeffParametersWidget(model)

    assert widget.control.value == ""
    assert widget.print.value == "1 0 0 0 0 3"
    assert widget.exchange.value == "0 0 0"
    assert widget.scf.value == ""
    assert widget.criteria.value == ""
    assert widget.exafs.value == 0
    assert widget.delete_tags.value == ""

    # Mutate values
    widget.control.value = "0 0 0 1 1 1"
    widget.print.value = "0 0 0 0 0 1"
    widget.exchange.value = "1 0 0"
    widget.scf.value = "5.0 0 30 0.1 1"
    widget.exafs.value = 15
    widget.criteria.value = "2.0 1.0"
    widget.delete_tags.value = "NOHOLE"

    # Reset
    widget.reset_advanced()
    assert widget.control.value == ""
    assert widget.print.value == "1 0 0 0 0 3"
    assert widget.exchange.value == "0 0 0"
    assert widget.scf.value == ""
    assert widget.criteria.value == ""
    assert widget.exafs.value == 0
    assert widget.delete_tags.value == ""


class DummyXas:
    """Mock XasData for unit tests without AiiDA DB."""

    def __init__(self, k, chi):
        self._arrays = {"k": k, "chi_k": chi}

    def get_array(self, name):
        return self._arrays[name]


def test_average_xas_on_common_k_nan_aware():
    """_average_xas_on_common_k uses NaN-aware statistics."""
    import numpy as np

    from aiidalab_exafs.results import _average_xas_on_common_k

    x1 = DummyXas(np.array([1.0, 2.0, 3.0]), np.array([0.1, 0.2, 0.3]))
    x2 = DummyXas(np.array([1.0, 2.0]), np.array([0.15, 0.25]))

    k_ref, chi_avg, chi_std = _average_xas_on_common_k([x1, x2])
    assert np.allclose(k_ref, [1.0, 2.0, 3.0])
    assert np.allclose(chi_avg[:2], [0.125, 0.225])
    assert np.allclose(chi_avg[2], 0.3)
    assert np.isnan(chi_std[2])  # Only 1 sample at k=3.0 gives NaN std


def test_workflow_model_clean_scratch_defaults():
    """WorkflowModel exposes clean_scratch and stream_chunk_size with sensible defaults."""
    model = WorkflowModel()
    assert model.clean_scratch is True
    assert model.stream_chunk_size == 256

    model.clean_scratch = False
    model.stream_chunk_size = 64
    model.reset()
    assert model.clean_scratch is True
    assert model.stream_chunk_size == 256


def test_is_usable_workflow():
    """_is_usable_workflow accepts exit code 0 or partial failures with averaged_xas."""
    from unittest.mock import MagicMock

    from aiida.orm import WorkChainNode
    from conftest import mock_of

    from aiidalab_exafs.results_library import _is_usable_workflow

    # Successful workflow
    m_ok = mock_of(WorkChainNode)
    m_ok.process_label = "EnsembleExafsWorkChain"
    m_ok.is_finished_ok = True
    assert _is_usable_workflow(m_ok)

    # Partially-failed workflow with averaged_xas (exit code 301)
    m_part = mock_of(WorkChainNode)
    m_part.process_label = "EnsembleExafsWorkChain"
    m_part.is_finished_ok = False
    m_part.is_finished = True
    m_part.outputs = MagicMock()
    m_part.outputs.averaged_xas = MagicMock()
    assert _is_usable_workflow(m_part)

    # Truly failed workflow with no averaged_xas
    m_fail = mock_of(WorkChainNode)
    m_fail.process_label = "EnsembleExafsWorkChain"
    m_fail.is_finished_ok = False
    m_fail.is_finished = True
    m_fail.outputs = MagicMock(spec=[])  # no averaged_xas attribute
    assert not _is_usable_workflow(m_fail)

    # Wrong process label
    m_wrong = mock_of(WorkChainNode)
    m_wrong.process_label = "OtherWorkChain"
    m_wrong.is_finished_ok = True
    assert not _is_usable_workflow(m_wrong)


def test_get_workchain_status_surfaces_exit_message():
    """get_workchain_status includes exit status and exit message for terminated processes."""
    from unittest.mock import MagicMock

    from aiidalab_exafs.process import get_workchain_status

    node = MagicMock()
    node.pk = 100
    node.process_state = "finished"
    node.is_terminated = True
    node.exit_status = 301
    node.exit_message = "2 of 10 snapshot calculations failed."

    status = get_workchain_status(node)
    assert "PK 100: finished [301]" in status
    assert "2 of 10 snapshot calculations failed." in status
