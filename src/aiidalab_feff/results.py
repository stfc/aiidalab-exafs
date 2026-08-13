"""Results page for the AiiDAlab FEFF app."""

from __future__ import annotations

import csv
from io import StringIO
from typing import TypeGuard

import ipywidgets as ipw
import numpy as np
from aiida import orm
from aiida_feff.calcfunctions.experimental import scale_simulated_spectrum, scaled_chi_arrays
from aiida_feff.data.xasdata import XasData
from alc_aiidalab_widgets.widgets.download import Download
from alc_aiidalab_widgets.widgets.status import Status

from aiidalab_feff.models import ResultsModel
from aiidalab_feff.experimental import ExperimentalSpectrumWidget
from aiidalab_feff.widgets.paths_explorer import PathContributionsExplorer


# k-weight options: (display label, exponent n in kⁿχ(k))
_KWEIGHTS = [
    ("χ(k)  (k⁰)", 0),
    ("k·χ(k)  (k¹)", 1),
    ("k²·χ(k)  (k²)", 2),
    ("k³·χ(k)  (k³)", 3),
]


def _new_figure(figsize=(6, 4)):
    """Create an ipympl-backed figure + axes pair, bypassing the pyplot state
    machine so the figure is never auto-displayed in the calling cell.

    Using ``plt.subplots()`` would register the figure in ``matplotlib.pyplot``
    (causing it to leak into cell output and stack up across renders) and the
    original code also broke widget comms by calling ``plt.close(fig)`` on
    mounted canvases. Instead we construct a bare ``Figure`` and explicitly
    attach the ipympl widget canvas via the backend's
    ``new_figure_manager_given_figure`` — ``fig.canvas`` is then a proper
    ``ipywidgets.Widget`` we can mount in a tab exactly once and redraw freely.
    """
    from matplotlib.figure import Figure

    # Importing the backend registers it and exposes its canvas factory.
    from ipympl.backend_nbagg import new_figure_manager_given_figure

    fig = Figure(figsize=figsize)
    # Attaches a widget FigureCanvas + manager to ``fig``. Number 0 is unused
    # since we don't register this figure with the pyplot figure manager map.
    new_figure_manager_given_figure(0, fig)
    ax = fig.subplots()
    return fig, ax


def _ft_larch(k: np.ndarray, chi: np.ndarray, kmin: float, kmax: float,
              kweight: int, dk: float, rmax: float):
    """Run a larch xftf on the given arrays, returning (r, chir_mag).

    Lightweight wrapper around larch's group/xftf so we don't have to materialise
    AiiDA nodes (and so avoid polluting the provenance graph) every time the FT
    parameter sliders move.
    """
    from larch import Group
    from larch.xafs import xftf

    grp = Group(k=k, chi=chi)
    xftf(grp, kmin=kmin, kmax=kmax, kweight=kweight, dk=dk, rmax_out=rmax)
    return grp.r, np.abs(grp.chir)


def _new_figure_2subplots(figsize=(10, 3)):
    """Like :func:`_new_figure` but returns two side-by-side axes."""
    from matplotlib.figure import Figure

    from ipympl.backend_nbagg import new_figure_manager_given_figure

    fig = Figure(figsize=figsize)
    new_figure_manager_given_figure(0, fig)
    ax_left, ax_right = fig.subplots(1, 2)
    return fig, ax_left, ax_right


def _average_xas_on_common_k(xas_nodes):
    """Interpolate χ(k) from each XasData onto a common k-grid and average.

    Mirrors the plugin's ``_average_xas_data_impl`` but operates purely on
    numpy arrays so the convergence view can re-average arbitrary subsets of
    the :math:`(frame, site)` grid without creating AiiDA nodes.

    Returns ``(k_ref, chi_avg, chi_std)`` or ``(None, None, None)`` if empty.
    """
    if not xas_nodes:
        return None, None, None
    k_ref = np.asarray(xas_nodes[0].get_array("k"), dtype=float)
    chi_stack = []
    for node in xas_nodes:
        k_i = np.asarray(node.get_array("k"), dtype=float)
        chi_i = np.asarray(node.get_array("chi_k"), dtype=float)
        chi_stack.append(np.interp(k_ref, k_i, chi_i, left=0.0, right=0.0))
    chi_arr = np.asarray(chi_stack)
    return k_ref, chi_arr.mean(axis=0), chi_arr.std(axis=0)


class ResultsWidget(ipw.VBox):
    """Widget for displaying EXAFS calculation results."""

    def __init__(self, results_model: ResultsModel):
        self.results_model = results_model

        self.header = ipw.HTML("<h2>Results</h2>")
        self.pk_label = ipw.HTML()
        self.status = Status()
        self.tabs = ipw.Tab()

        # Persistent matplotlib figures — created once, mounted in their tabs
        # once, and redrawn on every render. We never replace a tab's children
        # with a fresh canvas, so plots can't stack up between refreshes.
        self._fig_chi_k, self._ax_chi_k = _new_figure(figsize=(4, 3))
        self._fig_chi_r, self._ax_chi_r = _new_figure(figsize=(4, 3))
        # Convergence figure compares the selected subset in k and R space.
        self._fig_conv, self._ax_conv, self._ax_conv_resid = _new_figure_2subplots()

        # --- interactive plot controls (shared chi(k)/chi(R) k-weight + FT) --
        self.kweight = ipw.Dropdown(
            options=_KWEIGHTS,
            value=2,
            description="k-weight:",
            layout={"width": "180px"},
        )
        self.ft_kmin = ipw.FloatText(value=2.0, step=0.1, description="k_min:", layout={"width": "140px"})
        self.ft_kmax = ipw.FloatText(value=14.0, step=0.1, description="k_max:", layout={"width": "140px"})
        self.ft_dk = ipw.FloatText(value=1.0, step=0.1, description="Δk:", layout={"width": "140px"})
        self.ft_rmax = ipw.FloatText(value=8.0, step=0.5, description="R_max (Å):", layout={"width": "160px"})
        self.show_legends = ipw.Checkbox(
            value=False,
            description="Show legends",
            indent=False,
            layout={"width": "130px"},
        )
        self.show_experimental = ipw.Checkbox(
            value=True,
            description="Show experimental",
            indent=False,
            layout={"width": "160px"},
        )
        self.comparison_s02 = ipw.BoundedFloatText(
            value=1.0,
            min=0.0,
            max=2.0,
            step=0.01,
            description="S₀²:",
            layout={"width": "130px"},
        )
        self.comparison_e0 = ipw.FloatText(
            value=0.0,
            step=0.1,
            description="ΔE₀ (eV):",
            layout={"width": "150px"},
        )
        self.save_scaled_spectrum = ipw.Button(
            description="Save scaled simulation",
            icon="save",
            disabled=True,
        )
        self.save_scaled_spectrum.on_click(self._on_save_scaled_spectrum)

        # Convergence-tab k-weight (independent from chi(k)/chi(R) tabs).
        self.conv_kweight = ipw.Dropdown(
            options=_KWEIGHTS,
            value=2,
            description="k-weight:",
            layout={"width": "180px"},
        )
        # Sub-sampling controls: which sites / which frames to include.
        self.conv_sites = ipw.SelectMultiple(
            options=[],
            value=[],
            description="Sites:",
            layout={"width": "180px", "height": "120px"},
        )
        self.conv_frames = ipw.SelectMultiple(
            options=[],
            value=[],
            description="Frames:",
            layout={"width": "180px", "height": "120px"},
        )
        self.conv_all_sites = ipw.Button(description="All sites", icon="check-double", layout={"width": "100px"})
        self.conv_all_frames = ipw.Button(description="All frames", icon="check-double", layout={"width": "100px"})
        self.conv_all_sites.on_click(lambda _: self._select_all_conv())
        self.conv_all_frames.on_click(lambda _: self._select_all_conv())
        self.conv_box = ipw.VBox([
            ipw.HBox([self.conv_kweight], layout={"margin": "0 0 4px 0"}),
            ipw.HBox([
                ipw.VBox([self.conv_sites, self.conv_all_sites]),
                ipw.VBox([self.conv_frames, self.conv_all_frames]),
            ], layout={"margin": "0 0 4px 0"}),
        ])
        self.conv_box.layout.display = "none"

        # Re-render the affected tabs whenever the controls change.
        self.kweight.observe(self._on_chi_controls_change, names="value")
        self.ft_kmin.observe(self._on_ft_change, names="value")
        self.ft_kmax.observe(self._on_ft_change, names="value")
        self.ft_dk.observe(self._on_ft_change, names="value")
        self.ft_rmax.observe(self._on_ft_change, names="value")
        self.show_legends.observe(self._on_legend_change, names="value")
        self.show_experimental.observe(self._on_comparison_change, names="value")
        self.comparison_s02.observe(self._on_comparison_change, names="value")
        self.comparison_e0.observe(self._on_comparison_change, names="value")
        self.conv_kweight.observe(self._on_conv_change, names="value")
        self.conv_sites.observe(self._on_conv_change, names="value")
        self.conv_frames.observe(self._on_conv_change, names="value")

        self.convergence_tab = ipw.VBox([self.conv_box, self._fig_conv.canvas])
        self.paths_tab = ipw.VBox()
        self.experimental_widget = ExperimentalSpectrumWidget(results_model)
        self.experimental_reference = ipw.Accordion([self.experimental_widget], selected_index=None)
        self.experimental_reference.set_title(0, "Experimental reference")
        self.export_spectrum = ipw.Dropdown(description="Spectrum:", options=[])
        self.export_spectrum.observe(self._on_spectrum_change, names="value")
        self.chi_k_preview = ipw.HTML("<em>No spectrum data available.</em>")
        self.chi_r_preview = ipw.HTML("<em>No Fourier-transform data available.</em>")
        self.chi_k_download_output = ipw.Output()
        self.chi_r_download_output = ipw.Output()
        self.download_chi_k = Download(
            "feff-exafs-chi-k.csv",
            cb=self._chi_k_csv,
            output=self.chi_k_download_output,
            mimetype="text/csv",
            description="Download CSV",
            icon="download",
            disabled=True,
        )
        self.download_chi_r = Download(
            "feff-exafs-chi-r.csv",
            cb=self._chi_r_csv,
            output=self.chi_r_download_output,
            mimetype="text/csv",
            description="Download CSV",
            icon="download",
            disabled=True,
        )
        self.chi_k_export = ipw.Accordion(
            [
                ipw.VBox(
                    [
                        ipw.HTML("Preview and CSV use the selected k-weight."),
                        self.download_chi_k,
                        self.chi_k_preview,
                        self.chi_k_download_output,
                    ]
                )
            ]
        )
        self.chi_k_export.set_title(0, "View and download χ(k) data")
        self.chi_r_export = ipw.Accordion(
            [
                ipw.VBox(
                    [
                        ipw.HTML("Preview and CSV use the k-weight and FT settings above."),
                        self.download_chi_r,
                        self.chi_r_preview,
                        self.chi_r_download_output,
                    ]
                )
            ]
        )
        self.chi_r_export.set_title(0, "View and download χ(R) data")
        self.spectrum_controls = ipw.HBox(
            [
                self.export_spectrum,
                self.kweight,
                self.ft_kmin,
                self.ft_kmax,
                self.ft_dk,
                self.ft_rmax,
                self.show_legends,
                self.show_experimental,
                self.comparison_s02,
                self.comparison_e0,
                self.save_scaled_spectrum,
            ],
            layout={"margin": "0 0 8px 0", "flex_flow": "row wrap"},
        )
        self.chi_k_panel = ipw.VBox(
            [
                ipw.HTML("<h3>χ(k)</h3>"),
                self._fig_chi_k.canvas,
                self.chi_k_export,
            ],
            layout={"flex": "1 1 0", "min_width": "0", "padding": "0 0.75em 0 0"},
        )
        self.chi_r_panel = ipw.VBox(
            [
                ipw.HTML("<h3>χ(R)</h3>"),
                self._fig_chi_r.canvas,
                self.chi_r_export,
            ],
            layout={"flex": "1 1 0", "min_width": "0", "padding": "0 0 0 0.75em"},
        )
        self.spectrum_tab = ipw.VBox(
            [
                ipw.HTML("<h2>Spectrum</h2>"),
                self.experimental_reference,
                self.spectrum_controls,
                ipw.HBox(
                    [self.chi_k_panel, self.chi_r_panel],
                    layout={"align_items": "flex-start", "width": "100%"},
                ),
            ]
        )

        self.tabs.children = [
            self.spectrum_tab,
            self.convergence_tab,
            self.paths_tab,
        ]
        self.tabs.set_title(0, "Spectrum")
        self.tabs.set_title(1, "Convergence")
        self.tabs.set_title(2, "Path contributions")

        self.reset_button = ipw.Button(
            description="Refresh results",
            icon="refresh",
        )
        self.reset_button.on_click(self._on_refresh)

        super().__init__(
            [
                self.header,
                self.pk_label,
                self.reset_button,
                self.status,
                self.tabs,
            ]
        )

        self.results_model.observe(self._on_results_change, names="averaged_xas")
        self.results_model.observe(self._on_results_change, names="path_contributions")
        self.results_model.observe(self._on_results_change, names="experimental_xas")

        self._render()

    # ── model / control observers ─────────────────────────────────────────
    def _on_results_change(self, change):
        if change["new"] is not None:
            self._render()

    def _on_refresh(self, _):
        self._render()

    def _on_chi_controls_change(self, _):
        """k-weight changed → redraw both chi(k) (weighted) and chi(R) (re-FT)."""
        self._render_chi_k()
        self._render_chi_r()
        self._render_exports()

    def _on_ft_change(self, _):
        self._render_chi_r()
        self._render_chi_r_export()
        self._render_convergence()

    def _on_legend_change(self, _):
        """Apply the legend preference to all spectrum and convergence plots."""
        self._render_chi_k()
        self._render_chi_r()
        self._render_convergence()

    def _on_comparison_change(self, _):
        """Refresh the live experimental/simulated comparison."""
        self._render_chi_k()
        self._render_chi_r()

    def _on_save_scaled_spectrum(self, _):
        """Store the active comparison scaling as a provenance-linked node."""
        simulated = self._selected_export_spectrum()
        if simulated is None:
            return
        try:
            scaled = scale_simulated_spectrum(
                simulated,
                orm.Dict(
                    dict={
                        "s02": float(self.comparison_s02.value),
                        "e0_shift": float(self.comparison_e0.value),
                    }
                ),
            )
            scaled.label = f"Scaled FEFF spectrum from PK {simulated.pk}"
            self.status.value = f"Stored scaled simulated spectrum PK {scaled.pk}."
        except Exception as exc:  # noqa: BLE001
            self.status.value = f"<span style='color: red'>Could not save scaling: {exc}</span>"

    def _on_spectrum_change(self, _):
        """Redraw charts and raw-data previews for the selected spectrum."""
        self._render_chi_k()
        self._render_chi_r()
        self._render_exports()

    def _on_conv_change(self, _):
        self._render_convergence()

    def _select_all_conv(self):
        """Select all available sites and frames, then re-render."""
        if self.conv_sites.options:
            self.conv_sites.value = tuple(self.conv_sites.options)
        if self.conv_frames.options:
            self.conv_frames.value = tuple(self.conv_frames.options)

    # ── top-level render ──────────────────────────────────────────────────
    def _render(self):
        self.status.value = ""
        has_xas = self.results_model.averaged_xas is not None
        if not has_xas:
            self.status.value = "No results yet."
            self.pk_label.value = ""
            self._clear_figure(self._ax_chi_k)
            self._clear_figure(self._ax_chi_r)
            self._clear_figure(self._ax_conv)
            self._clear_figure(self._ax_conv_resid)
            self.conv_box.layout.display = "none"
            self.export_spectrum.options = []
            self.chi_k_preview.value = "<em>No spectrum data available.</em>"
            self.chi_r_preview.value = "<em>No Fourier-transform data available.</em>"
            self.download_chi_k.disabled = True
            self.download_chi_r.disabled = True
            self.save_scaled_spectrum.disabled = True
            return

        node = self.results_model.process_node
        if isinstance(node, orm.ProcessNode) and node.pk is not None:
            self.pk_label.value = f"Process PK: <b>{node.pk}</b>"
        else:
            self.pk_label.value = ""

        site_keys = [k for k in self.results_model.averaged_xas if k.startswith("site_")]
        self.conv_box.layout.display = "block" if site_keys else "none"

        # Populate the convergence sub-sampling selectors from the grid.
        self._populate_conv_selectors()

        self._populate_export_spectra()
        self.save_scaled_spectrum.disabled = self._selected_export_spectrum() is None
        self._render_chi_k()
        self._render_chi_r()
        self._render_convergence()
        self._render_paths()

        if self.results_model.n_failed is not None and self.results_model.n_failed > 0:
            self.status.value = (
                f"<span style='color: orange'>"
                f"Warning: {self.results_model.n_failed} snapshot calculations failed."
                f"</span>"
            )

    # ── helpers ───────────────────────────────────────────────────────────
    @staticmethod
    def _clear_figure(ax) -> None:
        ax.clear()
        ax.figure.canvas.draw_idle()

    @staticmethod
    def _redraw(fig) -> None:
        fig.canvas.draw_idle()

    def _populate_conv_selectors(self):
        """Fill the site / frame multi-selects from the xas_grid.

        Defaults to selecting all available sites and all frames so the initial
        view matches the full ensemble average.
        """
        grid = self.results_model.xas_grid or {}
        if not grid:
            self.conv_sites.options = []
            self.conv_frames.options = []
            self.conv_sites.value = ()
            self.conv_frames.value = ()
            return
        site_indices = sorted({s for _, s in grid.keys()})
        frame_indices = sorted({f for f, _ in grid.keys()})
        # Use string values — ipywidgets SelectMultiple validates more
        # reliably with string values than ints.
        self.conv_sites.options = [str(s) for s in site_indices]
        self.conv_frames.options = [str(f) for f in frame_indices]
        # If nothing selected yet (first population), select everything.
        if not self.conv_sites.value:
            self.conv_sites.value = tuple(str(s) for s in site_indices)
        if not self.conv_frames.value:
            self.conv_frames.value = tuple(str(f) for f in frame_indices)

    def _spectrum_title(self, suffix: str = "") -> str:
        """Build a plot title using the model's absorber/edge metadata."""
        title = self.results_model.spectrum_title
        return f"{title} — {suffix}" if title else suffix

    @staticmethod
    def _kweight_label(n: int) -> str:
        return {0: "χ(k)", 1: "k·χ(k)", 2: "k²·χ(k)", 3: "k³·χ(k)"}.get(n, f"kⁿ·χ(k), n={n}")

    # ── per-tab renders ───────────────────────────────────────────────────
    def _render_chi_k(self):
        ax = self._ax_chi_k
        ax.clear()
        xas = self._selected_export_spectrum()
        if xas is None:
            self._redraw(self._fig_chi_k)
            return

        k = np.asarray(xas.get_array("k"), dtype=float)
        chi_k = np.asarray(xas.get_array("chi_k"), dtype=float)
        k, chi_k = scaled_chi_arrays(
            k, chi_k, self.comparison_s02.value, self.comparison_e0.value
        )
        n = int(self.kweight.value)
        weighted = chi_k * (k ** n) if n else chi_k

        label = self._kweight_label(n)
        ax.plot(k, weighted, label="Simulated")
        if "chi_k_std" in xas.get_arraynames() and n and self.comparison_e0.value == 0:
            std = np.asarray(xas.get_array("chi_k_std"), dtype=float) * (k ** n)
            ax.fill_between(
                k, weighted - self.comparison_s02.value * std,
                weighted + self.comparison_s02.value * std, alpha=0.3, label="±1σ"
            )
        experimental = self.results_model.experimental_xas
        if self.show_experimental.value and _has_chi_data(experimental):
            exp_k = np.asarray(experimental.get_array("k"), dtype=float)
            exp_chi = np.asarray(experimental.get_array("chi_k"), dtype=float)
            exp_weighted = exp_chi * (exp_k ** n) if n else exp_chi
            ax.plot(exp_k, exp_weighted, color="C3", ls="--", label="Experimental")
        ax.set_xlabel("k (Å⁻¹)")
        ax.set_ylabel(label)
        if self.show_legends.value:
            ax.legend()
        ax.set_title(self._spectrum_title(f"{self._selected_spectrum_label()} {label}"))
        self._redraw(self._fig_chi_k)

    def _render_chi_r(self):
        ax = self._ax_chi_r
        ax.clear()
        xas = self._selected_export_spectrum()
        if xas is None:
            self._redraw(self._fig_chi_r)
            return

        k = np.asarray(xas.get_array("k"), dtype=float)
        chi_k = np.asarray(xas.get_array("chi_k"), dtype=float)
        k, chi_k = scaled_chi_arrays(
            k, chi_k, self.comparison_s02.value, self.comparison_e0.value
        )
        kweight = int(self.kweight.value)
        kmin = float(self.ft_kmin.value)
        kmax = float(self.ft_kmax.value)
        dk = float(self.ft_dk.value)
        rmax = float(self.ft_rmax.value)

        try:
            r, chir_mag = _ft_larch(k, chi_k, kmin, kmax, kweight, dk, rmax)
        except Exception as exc:  # noqa: BLE001
            ax.set_title("FT failed")
            ax.text(0.5, 0.5, str(exc), ha="center", va="center", transform=ax.transAxes)
            self._redraw(self._fig_chi_r)
            return

        kw_lbl = self._kweight_label(kweight)
        ax.plot(r, chir_mag, label="Simulated")
        experimental = self.results_model.experimental_xas
        if self.show_experimental.value and _has_chi_data(experimental):
            try:
                exp_r, exp_chir_mag = self._chi_r_arrays(experimental, apply_comparison=False)
            except Exception as exc:  # noqa: BLE001
                self.status.value = (
                    f"<span style='color: orange'>Experimental FT unavailable: {exc}</span>"
                )
            else:
                ax.plot(exp_r, exp_chir_mag, color="C3", ls="--", label="Experimental")
        ax.set_xlabel("R (Å)")
        ax.set_ylabel("|χ(R)|")
        if self.show_legends.value:
            ax.legend()
        ax.set_title(self._spectrum_title(
            f"{self._selected_spectrum_label()} |χ(R)| ({kw_lbl} FT)"
        ))
        self._redraw(self._fig_chi_r)

    def _render_convergence(self):
        """Compare selected-subset convergence in χ(k) and χ(R)."""
        averaged_xas = self.results_model.averaged_xas
        ax_top = self._ax_conv
        ax_resid = self._ax_conv_resid
        ax_top.clear()
        ax_resid.clear()
        if averaged_xas is None:
            self._redraw(self._fig_conv)
            return

        grid = self.results_model.xas_grid or {}
        n = int(self.conv_kweight.value)
        kw_lbl = self._kweight_label(n)

        if not grid:
            ax_top.set_title("No per-snapshot grid available for sub-sampling.")
            self._redraw(self._fig_conv)
            return

        # Full ensemble average is the reference for the selected subset.
        full_xas = averaged_xas.get("all")
        if full_xas is None:
            ax_top.set_title("Full ensemble average unavailable.")
            self._redraw(self._fig_conv)
            return
        k_full = np.asarray(full_xas.get_array("k"), dtype=float)
        chi_full = np.asarray(full_xas.get_array("chi_k"), dtype=float)
        chi_full_w = chi_full * (k_full ** n) if n else chi_full

        # Selected subset
        sel_sites = {int(s) for s in (self.conv_sites.value or [])}
        sel_frames = {int(f) for f in (self.conv_frames.value or [])}
        subset_nodes = [
            grid[(f, s)] for (f, s) in grid.keys() if f in sel_frames and s in sel_sites
        ]

        n_sel = len(subset_nodes)
        n_total = len(grid)
        if not subset_nodes:
            ax_top.set_title("Select at least one site and one frame.")
            self._redraw(self._fig_conv)
            return

        # Re-average the selected subset on a common k-grid.
        k_sub, chi_sub_avg, _ = _average_xas_on_common_k(subset_nodes)
        chi_sub_w = chi_sub_avg * (k_sub ** n) if n else chi_sub_avg

        # --- left: sub-sampled χ(k) average + faint per-site averages ---
        ax_top.plot(k_sub, chi_sub_w, color="C0", lw=2,
                    label=f"Subset avg ({n_sel}/{n_total} runs)")
        # Full ensemble average (all sites, all frames) as a reference line.
        ax_top.plot(k_full, chi_full_w, color="k", lw=1.5, ls="--",
                    label=f"Full ensemble ({n_total} runs)")
        # Overlay per-site averages within the selected subset.
        site_keys_in_subset = sorted({s for (f, s) in grid.keys()
                                      if f in sel_frames and s in sel_sites})
        for i, s in enumerate(site_keys_in_subset):
            site_nodes = [grid[(f, s)] for f in sel_frames if (f, s) in grid]
            if not site_nodes:
                continue
            ks, chs, _ = _average_xas_on_common_k(site_nodes)
            chs_w = chs * (ks ** n) if n else chs
            ax_top.plot(ks, chs_w, alpha=0.5, lw=1, color=f"C{i + 1}",
                        label=f"Site {s}")

        ax_top.set_ylabel(kw_lbl)
        ax_top.set_xlabel("k (Å⁻¹)")
        if self.show_legends.value:
            ax_top.legend(fontsize=8)
        ax_top.set_title(f"χ(k) convergence ({n_sel}/{n_total} runs)")

        # --- right: the same subset/full comparison after Fourier transform ---
        try:
            r_sub, chir_sub = _ft_larch(
                k_sub, chi_sub_avg, float(self.ft_kmin.value),
                float(self.ft_kmax.value), n, float(self.ft_dk.value),
                float(self.ft_rmax.value),
            )
            r_full, chir_full = _ft_larch(
                k_full, chi_full, float(self.ft_kmin.value),
                float(self.ft_kmax.value), n, float(self.ft_dk.value),
                float(self.ft_rmax.value),
            )
        except Exception as exc:  # noqa: BLE001
            ax_resid.set_title("χ(R) transform failed")
            ax_resid.text(0.5, 0.5, str(exc), ha="center", va="center", transform=ax_resid.transAxes)
        else:
            ax_resid.plot(r_sub, chir_sub, color="C0", lw=2, label=f"Subset avg ({n_sel}/{n_total} runs)")
            ax_resid.plot(r_full, chir_full, color="k", lw=1.5, ls="--", label=f"Full ensemble ({n_total} runs)")
            ax_resid.set_xlabel("R (Å)")
            ax_resid.set_ylabel("|χ(R)|")
            ax_resid.set_title(f"χ(R) convergence ({kw_lbl} FT)")
            if self.show_legends.value:
                ax_resid.legend(fontsize=8)

        self._redraw(self._fig_conv)

    def _render_paths(self):
        if not self.results_model.has_path_contributions():
            self.paths_tab.children = [
                ipw.HTML(
                    "Path contributions not available. "
                    "Set Path CW threshold ≥ 0 in the FEFF parameters step."
                )
            ]
            return

        # Replace the explorer each time; the PathContributionsExplorer is
        # stateful and bound to a specific node, so reusing one instance across
        # different processes would display stale data.
        explorer = PathContributionsExplorer(
            self.results_model.path_contributions,  # type: ignore[arg-type]
        )
        self.paths_tab.children = [explorer]

    def _populate_export_spectra(self):
        """Populate the χ(k)/χ(R) export selector with averaged spectra."""
        averaged_xas = self.results_model.averaged_xas or {}
        options = [("Ensemble average", "all")] if "all" in averaged_xas else []
        options.extend(
            (f"Site {key.removeprefix('site_')}", key)
            for key in sorted(averaged_xas)
            if key.startswith("site_")
        )
        previous = self.export_spectrum.value
        self.export_spectrum.options = options
        if previous in dict(options):
            self.export_spectrum.value = previous
        elif options:
            self.export_spectrum.value = options[0][1]
        self._render_exports()

    def _render_exports(self, _=None):
        """Refresh both data exports for the selected spectrum."""
        self._render_chi_k_export()
        self._render_chi_r_export()

    def _render_chi_k_export(self):
        """Preview and export the selected k-weighted χ(k) spectrum."""
        xas = self._selected_export_spectrum()
        if xas is None:
            self.chi_k_preview.value = "<em>No spectrum data available.</em>"
            self.download_chi_k.disabled = True
            return
        k = np.asarray(xas.get_array("k"), dtype=float)
        chi_k = np.asarray(xas.get_array("chi_k"), dtype=float)
        k, chi_k = scaled_chi_arrays(
            k, chi_k, self.comparison_s02.value, self.comparison_e0.value
        )
        kweight = int(self.kweight.value)
        weighted = chi_k * (k ** kweight) if kweight else chi_k
        rows = _format_preview_rows(
            zip(k[:20], chi_k[:20], weighted[:20], strict=True)
        )
        remaining = (
            "" if len(k) <= 20 else f"<p><em>{len(k) - 20} further rows are in the download.</em></p>"
        )
        self.chi_k_preview.value = (
            f"<p>{len(k)} points. Preview of the first {min(len(k), 20)}:</p>"
            + _format_preview_table(
                ["k (Å⁻¹)", "χ(k)", self._kweight_label(kweight)],
                rows,
            )
            + remaining
        )
        self.download_chi_k.filename = f"feff-exafs-{self.export_spectrum.value}-chi-k.csv"
        self.download_chi_k.disabled = False

    def _render_chi_r_export(self):
        """Preview and export |χ(R)| using the active Fourier-transform settings."""
        xas = self._selected_export_spectrum()
        if xas is None:
            self.chi_r_preview.value = "<em>No Fourier-transform data available.</em>"
            self.download_chi_r.disabled = True
            return
        try:
            r, chir_mag = self._chi_r_arrays(xas)
        except Exception as exc:  # noqa: BLE001
            self.chi_r_preview.value = f"<em>Fourier transform unavailable: {exc}</em>"
            self.download_chi_r.disabled = True
            return
        rows = _format_preview_rows(
            zip(r[:20], chir_mag[:20], strict=True)
        )
        remaining = (
            "" if len(r) <= 20 else f"<p><em>{len(r) - 20} further rows are in the download.</em></p>"
        )
        self.chi_r_preview.value = (
            f"<p>{len(r)} points. Preview of the first {min(len(r), 20)}:</p>"
            + _format_preview_table(["R (Å)", "|χ(R)|"], rows)
            + remaining
        )
        self.download_chi_r.filename = f"feff-exafs-{self.export_spectrum.value}-chi-r.csv"
        self.download_chi_r.disabled = False

    def _selected_export_spectrum(self):
        """Return the XAS node selected for χ(k) and χ(R) exports."""
        key = self.export_spectrum.value
        averaged_xas = self.results_model.averaged_xas or {}
        return averaged_xas.get(key) if key else None

    def _selected_spectrum_label(self) -> str:
        """Return the human-readable label for the selected plotted spectrum."""
        selected = self.export_spectrum.value
        return next(
            (label for label, value in self.export_spectrum.options if value == selected),
            "Selected",
        )

    def _chi_k_csv(self) -> str:
        """Serialize the selected k-weighted χ(k) spectrum as CSV."""
        xas = self._selected_export_spectrum()
        if xas is None:
            return ""
        k = np.asarray(xas.get_array("k"), dtype=float)
        chi_k = np.asarray(xas.get_array("chi_k"), dtype=float)
        k, chi_k = scaled_chi_arrays(
            k, chi_k, self.comparison_s02.value, self.comparison_e0.value
        )
        kweight = int(self.kweight.value)
        weighted = chi_k * (k ** kweight) if kweight else chi_k
        output = StringIO()
        writer = csv.writer(output)
        _write_export_metadata(
            output,
            **self._common_export_metadata(),
            spectrum=self.export_spectrum.value,
            kweight=kweight,
            s02=float(self.comparison_s02.value),
            e0_shift=float(self.comparison_e0.value),
        )
        writer.writerow(["k_angstrom_inverse", "chi_k", f"chi_k_times_k_to_{kweight}"])
        writer.writerows(zip(k, chi_k, weighted, strict=True))
        return output.getvalue()

    def _chi_r_arrays(self, xas: XasData, apply_comparison: bool = True):
        """Calculate |χ(R)| using the active χ(R) control values."""
        k = np.asarray(xas.get_array("k"), dtype=float)
        chi_k = np.asarray(xas.get_array("chi_k"), dtype=float)
        if apply_comparison:
            k, chi_k = scaled_chi_arrays(
                k, chi_k, self.comparison_s02.value, self.comparison_e0.value
            )
        return _ft_larch(
            k,
            chi_k,
            float(self.ft_kmin.value),
            float(self.ft_kmax.value),
            int(self.kweight.value),
            float(self.ft_dk.value),
            float(self.ft_rmax.value),
        )

    def _chi_r_csv(self) -> str:
        """Serialize the selected |χ(R)| transform as CSV."""
        xas = self._selected_export_spectrum()
        if xas is None:
            return ""
        r, chir_mag = self._chi_r_arrays(xas)
        output = StringIO()
        writer = csv.writer(output)
        _write_export_metadata(
            output,
            **self._common_export_metadata(),
            spectrum=self.export_spectrum.value,
            kweight=int(self.kweight.value),
            kmin=float(self.ft_kmin.value),
            kmax=float(self.ft_kmax.value),
            dk=float(self.ft_dk.value),
            rmax=float(self.ft_rmax.value),
            s02=float(self.comparison_s02.value),
            e0_shift=float(self.comparison_e0.value),
        )
        writer.writerow(["r_angstrom", "chi_r_magnitude"])
        writer.writerows(zip(r, chir_mag, strict=True))
        return output.getvalue()

    def _common_export_metadata(self) -> dict[str, str | int | None]:
        """Return workflow and spectrum context common to all exports."""
        process_node = self.results_model.process_node
        return {
            "process_pk": getattr(process_node, "pk", None),
            "spectrum_title": self.results_model.spectrum_title or "unspecified",
        }

    def reset(self):
        self.status.value = ""
        self.pk_label.value = ""
        # Reuse the persistent figures: just clear them instead of dropping
        # the canvases, so the tabs don't lose their (already-mounted) widget.
        self._clear_figure(self._ax_chi_k)
        self._clear_figure(self._ax_chi_r)
        self._clear_figure(self._ax_conv)
        self._clear_figure(self._ax_conv_resid)
        self.paths_tab.children = []
        self.export_spectrum.options = []
        self.chi_k_preview.value = "<em>No spectrum data available.</em>"
        self.chi_r_preview.value = "<em>No Fourier-transform data available.</em>"
        self.download_chi_k.disabled = True
        self.download_chi_r.disabled = True
        self.save_scaled_spectrum.disabled = True
        self.conv_box.layout.display = "none"
        self.experimental_widget.reset()
        # Clear sub-sampling selectors.
        self.conv_sites.options = []
        self.conv_frames.options = []
        self.conv_sites.value = ()
        self.conv_frames.value = ()
        self.results_model.reset()


def _format_preview_rows(rows) -> str:
    """Format numeric rows for the compact HTML data previews."""
    return "".join(
        "<tr>" + "".join(f"<td>{value:.7g}</td>" for value in row) + "</tr>"
        for row in rows
    )


def _has_chi_data(xas: object | None) -> TypeGuard[XasData]:
    """Return whether an experimental reference can be drawn in k/R space."""
    return isinstance(xas, XasData) and {"k", "chi_k"}.issubset(xas.get_arraynames())


def _format_preview_table(headers: list[str], rows: str) -> str:
    """Render a readable table with consistent column spacing."""
    header_cells = "".join(f"<th>{header}</th>" for header in headers)
    return (
        '<table class="feff-data-preview" style="border-collapse: collapse; margin: 0.5em 0;">'
        f"<thead><tr>{header_cells}</tr></thead>"
        f'<tbody style="font-family: monospace;">{rows}</tbody></table>'
        "<style>"
        ".feff-data-preview th, .feff-data-preview td { "
        "padding: 0.3em 1.25em 0.3em 0.5em; text-align: right; }"
        ".feff-data-preview th { border-bottom: 2px solid #bbb; }"
        ".feff-data-preview td { border-bottom: 1px solid #eee; }"
        "</style>"
    )


def _write_export_metadata(output: StringIO, **metadata) -> None:
    """Write portable comment headers before CSV columns and data."""
    output.write("# AiiDAlab FEFF data export\n")
    for key, value in metadata.items():
        output.write(f"# {key}: {value}\n")


def get_spectrum_arrays(xas: XasData) -> tuple[np.ndarray, np.ndarray]:
    """Return (k, chi_k) arrays from a XasData node."""
    return xas.get_array("k"), xas.get_array("chi_k")