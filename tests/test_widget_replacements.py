"""Unit tests verifying alc-aiidalab-widgets replacements across aiidalab-feff."""

from __future__ import annotations

import ipywidgets as ipw
from alc_aiidalab_widgets.widgets.file_handling import FileUploadWidget
from alc_aiidalab_widgets.widgets.mesages import MessageBox
from alc_aiidalab_widgets.widgets.status import Status
from alc_aiidalab_widgets.widgets.structure import StructureViewWidget

from aiidalab_feff.absorber import AbsorberSelectorWidget
from aiidalab_feff.common.navigation import create_new_calculation_button
from aiidalab_feff.experimental import ExperimentalSpectrumWidget
from aiidalab_feff.input import (
    DatabaseInputWidget,
    StructureInputWidget,
    TrajectoryInputWidget,
)
from aiidalab_feff.models import InputModel, ResultsModel, SubmissionModel, WorkflowModel
from aiidalab_feff.process import ProcessWidget
from aiidalab_feff.results_library import ResultsLibraryWidget


def test_input_widgets_embed_structure_view_widget():
    """Input widgets embed StructureViewWidget for single structures, trajectories, and DB."""
    model = InputModel()

    struct_widget = StructureInputWidget(model)
    assert hasattr(struct_widget, "viewer")
    assert isinstance(struct_widget.viewer, StructureViewWidget)

    traj_widget = TrajectoryInputWidget(model)
    assert hasattr(traj_widget, "viewer")
    assert isinstance(traj_widget.viewer, StructureViewWidget)

    db_widget = DatabaseInputWidget(model)
    assert hasattr(db_widget, "viewer")
    assert isinstance(db_widget.viewer, StructureViewWidget)


def test_process_widget_monitoring_and_loading():
    """ProcessWidget uses Status and is prepared with ProcessNodeViewerWidget integration."""
    im = InputModel()
    wm = WorkflowModel()
    sm = SubmissionModel()
    rm = ResultsModel()

    pw = ProcessWidget(im, wm, sm, rm)
    assert isinstance(pw.status, Status)
    assert isinstance(pw.monitor_output, ipw.Output)


def test_experimental_spectrum_uses_file_upload_widget_and_viewer():
    """ExperimentalSpectrumWidget uses FileUploadWidget and has a file viewer accordion."""
    rm = ResultsModel()
    exp = ExperimentalSpectrumWidget(rm)

    assert hasattr(exp, "file_upload_widget")
    assert isinstance(exp.file_upload_widget, FileUploadWidget)
    assert hasattr(exp, "file_preview_accordion")
    assert isinstance(exp.file_preview_accordion, ipw.Accordion)
    assert isinstance(exp.status, Status)


def test_absorber_selector_uses_status():
    """AbsorberSelectorWidget uses Status widget from alc_aiidalab_widgets."""
    model = InputModel()
    absorber = AbsorberSelectorWidget(model)

    assert hasattr(absorber, "status")
    assert isinstance(absorber.status, Status)


def test_results_library_embeds_structure_view_widget():
    """ResultsLibraryWidget embeds StructureViewWidget for 3D inspection."""
    lib = ResultsLibraryWidget(on_open=lambda _: None)

    assert hasattr(lib, "structure_viewer")
    assert isinstance(lib.structure_viewer, StructureViewWidget)
    assert isinstance(lib.status, Status)


def test_create_new_calculation_button_with_messagebox():
    """New calculation button prompts with MessageBox when active state exists."""

    class DummyWizard:
        def __init__(self):
            self.input_model = InputModel()
            self.submission_model = SubmissionModel()
            self.resets = 0

        def reset(self):
            self.resets += 1

    wizard = DummyWizard()
    btn_container = create_new_calculation_button(wizard)
    assert isinstance(btn_container, ipw.VBox)

    # Click when empty -> resets directly
    btn_container.children[0].click()
    assert wizard.resets == 1
    assert len(btn_container.children) == 1

    # Add active state -> prompts with MessageBox
    wizard.input_model.structures = {"frame_0000": object()}  # type: ignore[assignment]
    btn_container.children[0].click()
    assert len(btn_container.children) == 2
    msg_box = btn_container.children[1]
    assert isinstance(msg_box, MessageBox)

    # Reject -> cancels reset
    msg_box.cancel_btn.click()
    assert wizard.resets == 1
    assert len(btn_container.children) == 1

    # Prompt again and accept -> executes reset
    btn_container.children[0].click()
    assert len(btn_container.children) == 2
    msg_box2 = btn_container.children[1]
    msg_box2.accept_btn.click()
    assert wizard.resets == 2
    assert len(btn_container.children) == 1


def test_results_widget_defers_convergence_and_paths_tabs():
    """Opening results must not render the Convergence / Path contributions tabs.

    Those two tabs dominated the "Open results" latency (the paths tab alone
    measured 4.5 s on a 34k-path run) even though neither is visible when the
    results view first appears. They are marked dirty and drawn on selection.
    """
    from aiidalab_feff.results import ResultsWidget

    model = ResultsModel()
    widget = ResultsWidget(model)
    calls = {"convergence": 0, "paths": 0}
    widget._render_convergence = lambda: calls.__setitem__("convergence", calls["convergence"] + 1)
    widget._render_paths = lambda: calls.__setitem__("paths", calls["paths"] + 1)

    widget.tabs.selected_index = widget.TAB_SPECTRUM
    widget._invalidate_tab(widget.TAB_CONVERGENCE)
    widget._invalidate_tab(widget.TAB_PATHS)
    assert calls == {"convergence": 0, "paths": 0}
    assert widget._dirty_tabs == {widget.TAB_CONVERGENCE, widget.TAB_PATHS}

    # Selecting a tab renders it exactly once; re-selecting reuses the render.
    widget.tabs.selected_index = widget.TAB_CONVERGENCE
    assert calls == {"convergence": 1, "paths": 0}
    widget.tabs.selected_index = widget.TAB_SPECTRUM
    widget.tabs.selected_index = widget.TAB_CONVERGENCE
    assert calls == {"convergence": 1, "paths": 0}

    widget.tabs.selected_index = widget.TAB_PATHS
    assert calls == {"convergence": 1, "paths": 1}

    # Invalidating the visible tab redraws it immediately.
    widget._invalidate_tab(widget.TAB_PATHS)
    assert calls == {"convergence": 1, "paths": 2}


def test_process_widget_defers_provenance_viewer_until_accordion_opens():
    """The AiiDA provenance viewer is only built when its accordion is expanded."""
    widget = ProcessWidget(InputModel(), WorkflowModel(), SubmissionModel(), ResultsModel())
    rendered = []
    widget._render_details = rendered.append

    assert widget.details_accordion.selected_index is None
    widget._pending_details_node = object()
    assert rendered == []

    widget.details_accordion.selected_index = 0
    assert rendered == [widget._pending_details_node]
