"""Unit tests verifying alc-aiidalab-widgets replacements across aiidalab-feff."""

from __future__ import annotations

from types import SimpleNamespace

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


def test_lazy_widget_builds_once_on_demand():
    """LazyWidget must not call its factory until something asks for the widget."""
    from aiidalab_feff.common.lazy import LazyWidget

    calls = []

    def factory():
        calls.append(1)
        return ipw.HTML("real")

    lazy = LazyWidget(factory, placeholder="<em>Loading…</em>")
    assert calls == []
    assert lazy.built is False
    lazy.reset()  # resetting must not force a build
    assert calls == []

    built = lazy.build()
    assert calls == [1]
    assert lazy.built is True
    assert lazy.children == (built,)
    assert lazy.build() is built
    assert calls == [1]


def test_app_defers_database_backed_widgets_until_revealed():
    """Startup must not construct the widgets that query the database.

    Both selectors run a full AiiDA query from their constructor and sit behind
    a collapsed accordion or an unselected tab, which is what made a page
    refresh slow.
    """
    from aiidalab_feff.input import InputWidget
    from aiidalab_feff.results import ResultsWidget

    inputs = InputWidget(InputModel())
    assert inputs._database_lazy.built is False
    inputs.tabs.selected_index = inputs.TAB_DATABASE
    assert inputs._database_lazy.built is True

    results = ResultsWidget(ResultsModel())
    assert results._experimental_lazy.built is False
    results.experimental_reference.selected_index = 0
    assert results._experimental_lazy.built is True


def test_experimental_selector_filters_in_sql_not_in_python():
    """The experimental selector narrows the query instead of post-filtering."""
    from aiidalab_feff.common.database import ProjectedQueryWidget
    from aiidalab_feff.experimental import ExperimentalXasDatabaseQueryWidget

    assert issubclass(ExperimentalXasDatabaseQueryWidget, ProjectedQueryWidget)
    filters = ExperimentalXasDatabaseQueryWidget.extra_filters
    assert filters["or"] == [
        {"attributes.source_kind": "experimental"},
        {"extras.source_kind": "experimental"},
    ]


def test_results_widget_reset_restores_spectrum_tab():
    """Resetting ResultsWidget must restore the Spectrum tab so subsequent runs load fast."""
    from aiidalab_feff.results import ResultsWidget

    widget = ResultsWidget(ResultsModel())
    paths_rendered = []
    widget._render_paths = lambda: paths_rendered.append(1)

    # User viewed the Path contributions tab on calculation A
    widget.tabs.selected_index = widget.TAB_PATHS
    assert widget.tabs.selected_index == widget.TAB_PATHS
    assert paths_rendered == [1]

    # Loading calculation B resets results
    widget.reset()
    assert widget.tabs.selected_index == widget.TAB_SPECTRUM

    # Invalidating the deferred tabs must not trigger an additional render of Paths
    widget._invalidate_tab(widget.TAB_PATHS)
    assert paths_rendered == [1]


def test_process_widget_defers_progress_view_when_on_results_loaded_wired():
    """_on_finished must not do child-job progress aggregation when navigating to Results."""
    from aiida.engine import ProcessState

    rendered = []
    widget = ProcessWidget(
        InputModel(),
        WorkflowModel(),
        SubmissionModel(),
        ResultsModel(),
        on_results_loaded=lambda: None,
    )
    widget._render_process_view = rendered.append

    proc = SimpleNamespace(
        is_terminated=True,
        pk=42,
        process_state=ProcessState.FINISHED,
        is_finished_ok=True,
        outputs=SimpleNamespace(),
    )
    # Stub _populate_results to avoid database link lookups in this test
    widget._populate_results = lambda _: None

    widget._on_finished(proc)
    assert rendered == []
    assert widget._dirty_process_view is True

    # Navigating to Progress triggers ensure_rendered
    widget.ensure_rendered()
    assert rendered == [proc]
    assert widget._dirty_process_view is False


def test_results_model_update_results():
    """ResultsModel.update_results sets model fields inside hold_trait_notifications."""
    model = ResultsModel()
    notifications = []
    model.observe(lambda change: notifications.append(change["name"]))

    model.update_results(
        process_node=None,
        averaged_xas={"all": object()},
        xas_grid={(0, 0): object()},
        edge="K",
        absorber_label="Fe",
        is_ensemble=True,
        n_failed=0,
    )
    assert model.edge == "K"
    assert model.absorber_label == "Fe"
    assert model.is_ensemble is True
    # Notifications fired after the block exits
    assert "averaged_xas" in notifications
