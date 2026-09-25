"""Unit tests verifying the UI/UX review specification implementations."""

from __future__ import annotations

import numpy as np
from aiida_feff.data.xasdata import XasData

from aiidalab_feff.main import FeffApp
from aiidalab_feff.models import InputModel, ResultsModel, WorkflowModel
from aiidalab_feff.resources import ResourcesWidget
from aiidalab_feff.results import ResultsWidget
from aiidalab_feff.results_library import _format_duration
from aiidalab_feff.widgets.paths_explorer import PathContributionsExplorer
from aiidalab_feff.workflow import FeffParametersWidget


def test_feff_parameters_presets():
    """FeffParametersWidget supports presets (Quick look, Standard, Publication, Custom)."""
    wm = WorkflowModel()
    im = InputModel()
    pw = FeffParametersWidget(wm, im)

    # Initial state is Standard
    assert pw.preset_selector.value == "Standard"
    assert pw.radius.value == 5.5
    assert pw.nleg.value == 6

    # Select Quick look
    pw.preset_selector.value = "Quick look"
    assert pw.radius.value == 4.5
    assert pw.nleg.value == 4
    assert pw.precompute_potentials.value is True

    # Select Publication
    pw.preset_selector.value = "Publication"
    assert pw.radius.value == 6.5
    assert pw.nleg.value == 8
    assert pw.precompute_potentials.value is False

    # User edit switches to Custom
    pw.radius.value = 7.0
    assert pw.preset_selector.value == "Custom"


def test_shared_fourier_model_sync():
    """ResultsModel synchronizes Fourier parameters across ResultsWidget and PathContributionsExplorer."""
    rm = ResultsModel()
    assert rm.ft_kmin == 2.0
    assert rm.ft_kmax == 14.0
    assert rm.kweight == 2

    rw = ResultsWidget(rm)

    # ResultsWidget change pushes to ResultsModel
    rw.ft_kmin.value = 3.2
    assert rm.ft_kmin == 3.2

    rw.kweight.value = 1
    assert rm.kweight == 1

    # ResultsModel change reflects back in ResultsWidget
    rm.ft_kmax = 16.5
    assert rw.ft_kmax.value == 16.5


def test_path_contributions_explorer_syncs_with_results_model():
    """PathContributionsExplorer synchronizes Fourier settings with ResultsModel."""
    rm = ResultsModel()
    rm.ft_kmin = 2.5
    rm.kweight = 3

    class DummyPath:
        def iter_paths(self):
            return iter([])

    explorer = PathContributionsExplorer(DummyPath(), results_model=rm)
    # Initialized from model
    assert explorer.kmin.value == 2.5
    assert explorer.kweight.value == 3

    # Updating explorer updates model
    explorer.kmin.value = 4.0
    assert rm.ft_kmin == 4.0


def test_athena_export_format():
    """ResultsWidget produces valid Athena-compatible .chi and .chir formats."""
    rm = ResultsModel()
    rw = ResultsWidget(rm)

    # Create dummy XasData
    k = np.linspace(2.0, 14.0, 50)
    chi = 0.05 * np.sin(2.0 * k)
    xas = XasData()
    xas.set_array("k", k)
    xas.set_array("chi_k", chi)
    rm.averaged_xas = {"all": xas}
    rm.edge = "K"
    rm.absorber_label = "Cu"

    rw._render()

    chi_athena = rw._chi_k_athena()
    assert "# Athena chi(k) data file" in chi_athena
    assert "# title: Cu K-edge" in chi_athena
    assert "2.0000" in chi_athena

    chir_athena = rw._chi_r_athena()
    assert "# Athena chi(R) data file" in chir_athena
    assert "# FT window:" in chir_athena


def test_ft_window_change_updates_chi_k_plot():
    """Changing Fourier window (k_min, k_max) immediately redraws chi(k) and window boundaries."""
    rm = ResultsModel()
    rw = ResultsWidget(rm)

    k = np.linspace(0.05, 20.0, 100)
    chi = 0.05 * np.sin(2.0 * k)
    xas = XasData()
    xas.set_array("k", k)
    xas.set_array("chi_k", chi)
    rm.averaged_xas = {"all": xas}

    rw._render()

    # Changing ft_kmin from 2.0 to 4.5 immediately redraws chi(k)
    rw.ft_kmin.value = 4.5

    # Check that axvline at 4.5 exists in _ax_chi_k
    vlines = [
        line.get_xdata()[0]
        for line in rw._ax_chi_k.lines
        if len(line.get_xdata()) == 2 and line.get_xdata()[0] == line.get_xdata()[1]
    ]
    assert 4.5 in vlines


def test_load_experimental_spectrum_updates_ui_cleanly():
    """Setting experimental_xas updates show_experimental, titles, and overlays cleanly."""
    rm = ResultsModel()
    rw = ResultsWidget(rm)

    k = np.linspace(0.5, 19.0, 100)
    chi = 0.05 * np.sin(2.0 * k)
    xas = XasData()
    xas.set_array("k", k)
    xas.set_array("chi_k", chi)
    rm.averaged_xas = {"all": xas}
    rw._render()

    # Before experimental data: show_experimental is disabled and unchecked
    assert rw.show_experimental.disabled is True
    assert rw.show_experimental.value is False

    # Load experimental spectrum
    exp_k = np.linspace(0.5, 19.0, 100)
    exp_chi = 0.04 * np.sin(2.0 * exp_k + 0.1)
    exp_xas = XasData()
    exp_xas.set_array("k", exp_k)
    exp_xas.set_array("chi_k", exp_chi)
    exp_xas.label = "Experimental: Cu foil"

    # Observe change
    rm.experimental_xas = exp_xas

    # Now show_experimental is enabled and checked
    assert rw.show_experimental.disabled is False
    assert rw.show_experimental.value is True
    assert "✓ Experimental reference:" in rw.experimental_reference.get_title(0)
    assert rw.experimental_reference.selected_index is None

    # Experimental curve is plotted on both chi(k) and chi(R)
    k_labels = [line.get_label() for line in rw._ax_chi_k.lines]
    assert "Experimental" in k_labels

    r_labels = [line.get_label() for line in rw._ax_chi_r.lines]
    assert "Experimental" in r_labels


def test_review_card_and_label():
    """ResourcesWidget formats calculation summary card and prefilled label."""
    im = InputModel()
    wm = WorkflowModel()
    rw = ResourcesWidget(wm, im)

    assert rw.label_input.value != ""
    assert "Calculation summary" in rw.review_card.value
    assert "Total calculations:" in rw.review_card.value


def test_feff_app_stepper_and_action_bar():
    """FeffApp has 5 steps, consolidated breadcrumbs, and a single bottom action bar."""
    app = FeffApp()
    assert len(app.steps) == 5
    assert app.step_titles == [
        "1. Structure",
        "2. Settings",
        "3. Review & run",
        "4. Progress",
        "5. Results",
    ]
    assert hasattr(app, "action_bar")
    assert hasattr(app, "results_library")
    assert app.app_tabs.get_title(app.TAB_NEW) == "New calculation"
    assert "Runs" in app.app_tabs.get_title(app.TAB_RUNS)


def test_format_duration():
    """_format_duration accurately formats seconds into hours, minutes, seconds."""
    assert _format_duration(45) == "45s"
    assert _format_duration(125) == "2m 5s"
    assert _format_duration(3665) == "1h 1m 5s"


def test_runs_table_truncation_and_open_button():
    """Runs table truncates long labels with hover tooltip and includes Open action button."""
    import datetime

    from aiidalab_feff.results_library import _build_unified_table_rows, _cell

    # Check cell tooltip and truncation
    long_label = "PB_pristine_222supercell_K_2026-09-24"
    cell = _cell(long_label, "140px", bold=True)
    assert f"title='{long_label}'" in cell.value
    assert "text-overflow:ellipsis" in cell.value
    assert cell.layout.width == "140px"

    opened_nodes = []
    selected_pks = []

    records = [
        {
            "pk": 14420,
            "ctime": datetime.datetime.now(datetime.timezone.utc),
            "label": long_label,
            "formula": "KFe2(CN)6",
            "absorber": "K (32 sites)",
            "frames_sites": "32",
            "status_code": "done",
            "status_text": "Done (1 failed)",
            "badge_class": "feff-badge feff-badge-done",
            "duration_str": "12m 30s",
            "node": "dummy_node_14420",
        }
    ]

    header, row = _build_unified_table_rows(
        records,
        on_select=selected_pks.append,
        on_open=opened_nodes.append,
    )

    # Header and row alignment
    assert len(header.children) == len(row.children)
    # Action column has Open button
    open_btn = row.children[1]
    assert open_btn.description == "Open"
    open_btn.click()
    assert selected_pks == [14420]
    assert opened_nodes == ["dummy_node_14420"]
    assert selected_pks == [14420]
    assert opened_nodes == ["dummy_node_14420"]


def test_compute_chi_from_params_smooth():
    """compute_chi_from_params generates smooth, non-oscillating chi(k) on fine grid."""
    from aiidalab_feff.widgets.paths_explorer import compute_chi_from_params

    k_coarse = np.array([0.0, 1.0, 2.0, 4.0, 6.0, 8.0, 10.0, 14.0, 18.0, 20.0])
    amp = np.ones_like(k_coarse) * 0.5
    pha = np.linspace(-15.0, -25.0, len(k_coarse))
    lam = np.linspace(30.0, 10.0, len(k_coarse))
    rep = np.linspace(1.5, 10.0, len(k_coarse))

    k_fine = np.arange(0.05, 20.0, 0.05)
    chi = compute_chi_from_params(k_fine, amp, pha, lam, rep, reff=3.0, degen=1.0, k_param=k_coarse)

    assert len(chi) == len(k_fine)
    assert not np.isnan(chi).any()
    assert not np.isinf(chi).any()
    # Check that amplitude is finite and smooth (no infinite spikes)
    assert np.max(np.abs(chi)) < 2.0
