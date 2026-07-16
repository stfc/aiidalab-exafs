"""Results page for the AiiDAlab FEFF app."""

from __future__ import annotations

import ipywidgets as ipw
import numpy as np
from aiida import orm
from aiida_feff.data.xasdata import XasData
from alc_aiidalab_widgets.widgets.status import Status

from aiidalab_feff.models import ResultsModel
from aiidalab_feff.widgets.paths_explorer import PathContributionsExplorer


# k-weight options: (display label, exponent n in kⁿχ(k))
_KWEIGHTS = [
    ("χ(k)  (k⁰)", 0),
    ("k·χ(k)  (k¹)", 1),
    ("k²·χ(k)  (k²)", 2),
    ("k³·χ(k)  (k³)", 3),
]


def _new_figure():
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

    fig = Figure(figsize=(6, 4))
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


def _new_figure_2subplots(figsize=(6, 6)):
    """Like :func:`_new_figure` but returns (fig, ax_top, ax_bottom)."""
    from matplotlib.figure import Figure

    from ipympl.backend_nbagg import new_figure_manager_given_figure

    fig = Figure(figsize=figsize)
    new_figure_manager_given_figure(0, fig)
    ax_top, ax_bottom = fig.subplots(2, 1, sharex=True, gridspec_kw={"height_ratios": [3, 1]})
    return fig, ax_top, ax_bottom


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
        self._fig_chi_k, self._ax_chi_k = _new_figure()
        self._fig_chi_r, self._ax_chi_r = _new_figure()
        # Convergence figure has two subplots: χ(k) average (top) + residual (bottom)
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
        self.conv_kweight.observe(self._on_conv_change, names="value")
        self.conv_sites.observe(self._on_conv_change, names="value")
        self.conv_frames.observe(self._on_conv_change, names="value")

        self.chi_k_tab = ipw.VBox([
            ipw.HBox([self.kweight], layout={"margin": "0 0 4px 0"}),
            self._fig_chi_k.canvas,
        ])
        self.chi_r_tab = ipw.VBox([
            ipw.HBox([self.kweight, self.ft_kmin, self.ft_kmax, self.ft_dk, self.ft_rmax],
                     layout={"margin": "0 0 4px 0", "flex_flow": "row wrap"}),
            self._fig_chi_r.canvas,
        ])
        self.convergence_tab = ipw.VBox([self.conv_box, self._fig_conv.canvas])
        self.paths_tab = ipw.VBox()

        self.tabs.children = [
            self.chi_k_tab,
            self.chi_r_tab,
            self.convergence_tab,
            self.paths_tab,
        ]
        self.tabs.set_title(0, "χ(k)")
        self.tabs.set_title(1, "χ(R)")
        self.tabs.set_title(2, "Convergence")
        self.tabs.set_title(3, "Path contributions")

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

    def _on_ft_change(self, _):
        self._render_chi_r()

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
        averaged_xas = self.results_model.averaged_xas
        ax = self._ax_chi_k
        ax.clear()
        if averaged_xas is None or "all" not in averaged_xas:
            self._redraw(self._fig_chi_k)
            return

        xas = averaged_xas["all"]
        k = np.asarray(xas.get_array("k"), dtype=float)
        chi_k = np.asarray(xas.get_array("chi_k"), dtype=float)
        n = int(self.kweight.value)
        weighted = chi_k * (k ** n) if n else chi_k

        label = self._kweight_label(n)
        ax.plot(k, weighted, label=label)
        if "chi_k_std" in xas.get_arraynames() and n:
            std = np.asarray(xas.get_array("chi_k_std"), dtype=float) * (k ** n)
            ax.fill_between(k, weighted - std, weighted + std, alpha=0.3, label="±1σ")
        ax.set_xlabel("k (Å⁻¹)")
        ax.set_ylabel(label)
        ax.legend()
        ax.set_title(self._spectrum_title(f"Average {label}"))
        self._redraw(self._fig_chi_k)

    def _render_chi_r(self):
        averaged_xas = self.results_model.averaged_xas
        ax = self._ax_chi_r
        ax.clear()
        if averaged_xas is None or "all" not in averaged_xas:
            self._redraw(self._fig_chi_r)
            return

        xas = averaged_xas["all"]
        k = np.asarray(xas.get_array("k"), dtype=float)
        chi_k = np.asarray(xas.get_array("chi_k"), dtype=float)
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
        ax.plot(r, chir_mag, label=f"|χ(R)|  ({kw_lbl}, k={kmin:g}–{kmax:g} Å⁻¹)")
        ax.set_xlabel("R (Å)")
        ax.set_ylabel("|χ(R)|")
        ax.legend()
        ax.set_title(self._spectrum_title(f"|χ(R)| magnitude  ({kw_lbl} FT)"))
        self._redraw(self._fig_chi_r)

    def _render_convergence(self):
        """Convergence / sub-sampling view.

        Top axis: the ensemble-averaged χ(k)·kⁿ over the currently-selected
        subset of sites and frames (faint per-site averages overlaid).

        Bottom axis: the residual — (sub-sampled average) minus (full ensemble
        average) — so you can see how dropping sites/frames affects the result
        relative to the complete run.
        """
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

        # Full ensemble average (the gold-standard baseline for the residual).
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

        # Interpolate full onto the same k-grid for the residual.
        chi_full_interp = np.interp(k_sub, k_full, chi_full, left=0.0, right=0.0)
        resid = chi_sub_w - (chi_full_interp * (k_sub ** n) if n else chi_full_interp)

        # --- top: sub-sampled average + faint per-site averages ---
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
        ax_top.legend(fontsize=8)
        n_sites = len(sel_sites)
        n_frames = len(sel_frames)
        ax_top.set_title(self._spectrum_title(
            f"Convergence — {n_sel}/{n_total} runs "
            f"({n_frames} frames×{n_sites} sites)"))

        # --- bottom: residual vs full ensemble ---
        ax_resid.plot(k_sub, resid, color="C3", lw=1.5)
        ax_resid.axhline(0, color="k", lw=0.5, ls="--")
        ax_resid.set_xlabel("k (Å⁻¹)")
        ax_resid.set_ylabel(f"Δ {kw_lbl}")
        ax_resid.set_title("Residual vs full ensemble", fontsize=9)

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
        self.conv_box.layout.display = "none"
        # Clear sub-sampling selectors.
        self.conv_sites.options = []
        self.conv_frames.options = []
        self.conv_sites.value = ()
        self.conv_frames.value = ()
        self.results_model.reset()


def get_spectrum_arrays(xas: XasData) -> tuple[np.ndarray, np.ndarray]:
    """Return (k, chi_k) arrays from a XasData node."""
    return xas.get_array("k"), xas.get_array("chi_k")