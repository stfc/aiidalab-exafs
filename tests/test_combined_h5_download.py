"""Unit tests verifying combined .h5 file download and export capabilities."""

from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest
from aiida.orm import ProcessNode
from aiida_feff.data.archive import ExafsArchiveData
from aiida_feff.data.pathcontributions import PathContributionsData

from aiidalab_feff.common.file_handling import (
    export_combined_h5,
    find_combined_h5_node,
    get_combined_h5_bytes,
)
from aiidalab_feff.models import ResultsModel
from aiidalab_feff.results import ResultsWidget
from aiidalab_feff.results_library import ResultsLibraryWidget
from aiidalab_feff.widgets.paths_explorer import PathContributionsExplorer


class _Context:
    def __init__(self, content):
        self.content = content

    def __enter__(self):
        self.handle = io.BytesIO(self.content)
        return self.handle

    def __exit__(self, *args):
        self.handle.close()


def create_mock_archive_node(
    pk=101, content=b"\x89HDF\r\n\x1a\nfake-archive-bytes", filename="ensemble_results.h5"
):
    """Create a mock ExafsArchiveData node satisfying trait validation."""
    archive = MagicMock(spec=ExafsArchiveData)
    archive.pk = pk
    archive.filename = filename
    archive.node_type = "data.archive.ExafsArchiveData."
    archive.open.side_effect = lambda mode="rb": _Context(content)

    class _Repo:
        def list_object_names(self):
            return [filename]

        def get_object_content(self, name, mode="rb"):
            if name == filename:
                return content
            raise FileNotFoundError(name)

    archive.base.repository = _Repo()
    return archive


def create_mock_path_node(pk=202, content=b"\x89HDF\r\n\x1a\nfake-path-bytes"):
    """Create a mock PathContributionsData node satisfying trait validation."""
    paths = MagicMock(spec=PathContributionsData)
    paths.pk = pk
    paths.node_type = "data.pathcontributions.PathContributionsData."
    paths._raw.return_value = content
    return paths


def test_find_combined_h5_node_direct_and_results_model():
    """find_combined_h5_node resolves archive from ResultsModel or direct nodes."""
    archive = create_mock_archive_node(pk=11)
    paths = create_mock_path_node(pk=22)

    # Directly passing archive or path node
    assert find_combined_h5_node(archive) is archive
    assert find_combined_h5_node(paths) is paths
    assert find_combined_h5_node(None) is None

    # ResultsModel with archive
    rm_arch = ResultsModel()
    rm_arch.archive = archive
    assert find_combined_h5_node(rm_arch) is archive

    # ResultsModel with path contributions (when archive is None)
    rm_paths = ResultsModel()
    rm_paths.path_contributions = paths
    assert find_combined_h5_node(rm_paths) is paths


def test_find_combined_h5_node_from_workchain_outputs():
    """find_combined_h5_node discovers archive or paths from WorkChain outputs."""
    archive = create_mock_archive_node(pk=301)
    paths = create_mock_path_node(pk=302)

    # Workchain with outputs.archive
    wc_arch = SimpleNamespace(
        pk=1001,
        outputs=SimpleNamespace(archive=archive, path_contributions=None),
    )
    assert find_combined_h5_node(wc_arch) is archive

    # Workchain with outputs.path_contributions only
    wc_paths = SimpleNamespace(
        pk=1002,
        outputs=SimpleNamespace(path_contributions=paths),
    )
    assert find_combined_h5_node(wc_paths) is paths

    # Workchain with outgoing links
    link_arch = SimpleNamespace(link_label="archive", node=archive)
    wc_links = SimpleNamespace(
        pk=1003,
        outputs=SimpleNamespace(),
        base=SimpleNamespace(
            links=SimpleNamespace(get_outgoing=lambda: SimpleNamespace(all=lambda: [link_arch]))
        ),
    )
    assert find_combined_h5_node(wc_links) is archive


def test_get_combined_h5_bytes():
    """get_combined_h5_bytes extracts raw content from archive and path nodes."""
    archive = create_mock_archive_node(content=b"HDF5-ARCHIVE-DATA")
    paths = create_mock_path_node(content=b"HDF5-PATHS-DATA")

    assert get_combined_h5_bytes(archive) == b"HDF5-ARCHIVE-DATA"
    assert get_combined_h5_bytes(paths) == b"HDF5-PATHS-DATA"
    assert get_combined_h5_bytes(None) is None

    # Passing a workchain containing the archive
    wc = SimpleNamespace(outputs=SimpleNamespace(archive=archive))
    assert get_combined_h5_bytes(wc) == b"HDF5-ARCHIVE-DATA"


def test_export_combined_h5(tmp_path: Path):
    """export_combined_h5 writes the combined .h5 file to specified destinations."""
    archive = create_mock_archive_node(pk=777, content=b"\x89HDF-test-export-content")

    # Export to explicit file path
    target_file = tmp_path / "custom_run.h5"
    out_path = export_combined_h5(archive, target_file)
    assert out_path == target_file
    assert target_file.read_bytes() == b"\x89HDF-test-export-content"

    # Export to directory (generates default name feff-run-<pk>-combined.h5)
    dest_dir = tmp_path / "exports"
    dest_dir.mkdir()
    out_dir_path = export_combined_h5(archive, dest_dir)
    assert out_dir_path == dest_dir / "feff-run-777-combined.h5"
    assert out_dir_path.read_bytes() == b"\x89HDF-test-export-content"

    # Missing node raises FileNotFoundError
    with pytest.raises(FileNotFoundError, match="No combined .h5 file found"):
        export_combined_h5(SimpleNamespace(outputs=SimpleNamespace()))


def test_results_widget_download_combined_h5():
    """ResultsWidget provides a Download widget for combined .h5 in export_card."""
    rm = ResultsModel()
    rw = ResultsWidget(rm)

    assert hasattr(rw, "download_combined_h5")
    assert rw.download_combined_h5 in rw.export_card.children[1].children
    assert rw.combined_h5_download_output in rw.download_outputs.children
    assert rw.download_outputs in rw.export_card.children
    assert rw.download_combined_h5.disabled is True

    # Set up dummy averaged spectrum and archive node
    from aiida_feff.data.xasdata import XasData

    k = np.linspace(2.0, 14.0, 30)
    chi = 0.05 * np.sin(k)
    xas = XasData()
    xas.set_array("k", k)
    xas.set_array("chi_k", chi)
    archive = create_mock_archive_node(pk=456, content=b"HDF5-COMBINED-TEST-BYTES")

    proc = MagicMock(spec=ProcessNode)
    proc.pk = 456
    proc.inputs = SimpleNamespace()
    proc.label = "Test Process"
    rm.process_node = proc
    rm.averaged_xas = {"all": xas}
    rm.archive = archive

    rw._render()

    assert rw.download_combined_h5.disabled is False
    assert rw.download_combined_h5.filename == "feff-run-456-combined.h5"
    assert rw.download_combined_h5.mimetype == "application/x-hdf5"
    assert rw._combined_h5_bytes() == b"HDF5-COMBINED-TEST-BYTES"

    # Reset disables the button
    rw.reset()
    assert rw.download_combined_h5.disabled is True


def test_results_library_widget_download_combined_h5():
    """ResultsLibraryWidget provides a Download button in details_sidebar for any selected run."""
    lib = ResultsLibraryWidget(on_open=lambda _: None)

    assert hasattr(lib, "download_h5_button")
    assert lib.download_h5_button.disabled is True
    # Verify the download Output widget is mounted in details_sidebar
    assert lib.download_h5_output in lib.children[3].children[1].children

    archive = create_mock_archive_node(pk=999, content=b"LIBRARY-HDF5-BYTES")
    mock_node = SimpleNamespace(
        pk=999,
        outputs=SimpleNamespace(archive=archive),
        inputs=SimpleNamespace(),
    )

    import datetime

    record = {
        "pk": 999,
        "ctime": datetime.datetime.now(datetime.timezone.utc),
        "label": "Test Ensemble Run",
        "formula": "Cu",
        "absorber": "Cu K-edge",
        "frames_sites": "10",
        "status_code": "done",
        "status_text": "Done",
        "badge_class": "feff-badge feff-badge-done",
        "duration_str": "5m",
        "n_failed": 0,
        "node": mock_node,
    }
    lib._records = {999: record}

    # Selecting the record enables download
    lib._select_record(999)

    assert lib.download_h5_button.disabled is False
    assert lib.download_h5_button.filename == "feff-run-999-combined.h5"
    assert lib._download_selected_h5() == b"LIBRARY-HDF5-BYTES"

    # Selecting a run without h5 disables download
    record_no_h5 = dict(record)
    record_no_h5["pk"] = 1000
    record_no_h5["node"] = SimpleNamespace(
        pk=1000, outputs=SimpleNamespace(), inputs=SimpleNamespace()
    )
    lib._records[1000] = record_no_h5

    lib._select_record(1000)
    assert lib.download_h5_button.disabled is True
    assert lib._download_selected_h5() == b""


def test_paths_explorer_widget_download_combined_h5():
    """PathContributionsExplorer embeds a working combined .h5 download button."""
    from aiida_feff.data.pathcontributions import PathResult

    class DummyStoreWithBytes:
        pk = 555

        def _raw(self):
            return b"PATHS-HDF5-RAW-DATA"

        def iter_paths(self):
            yield PathResult(
                frame_idx=0,
                site_idx=0,
                r_eff=2.5,
                nlegs=2,
                degeneracy=12.0,
                scatterer="Cu",
                cw_ratio=100.0,
                k=np.linspace(0, 20, 10),
                feff_data=np.ones((10, 6)),
            )

    explorer = PathContributionsExplorer(DummyStoreWithBytes())
    assert hasattr(explorer, "download_h5")
    assert explorer.download_h5.disabled is False
    assert explorer.download_h5.filename == "feff-run-555-combined.h5"
    assert explorer._get_h5_bytes() == b"PATHS-HDF5-RAW-DATA"
    assert explorer.download_output in explorer.children[0].children

    # When results_model with process_node is provided, its run pk is used
    rm = ResultsModel()
    proc = MagicMock(spec=ProcessNode)
    proc.pk = 888
    rm.process_node = proc
    explorer_rm = PathContributionsExplorer(DummyStoreWithBytes(), results_model=rm)
    assert explorer_rm.download_h5.filename == "feff-run-888-combined.h5"

    # Arbitrary object without HDF5 archive is disabled
    class DummyNoArchive:
        base = object()

        def iter_paths(self):
            yield PathResult(
                frame_idx=0,
                site_idx=0,
                r_eff=2.5,
                nlegs=2,
                degeneracy=12.0,
                scatterer="Cu",
                cw_ratio=100.0,
                k=np.linspace(0, 20, 10),
                feff_data=np.ones((10, 6)),
            )

    explorer_no_arch = PathContributionsExplorer(DummyNoArchive())
    assert explorer_no_arch.download_h5.disabled is True
