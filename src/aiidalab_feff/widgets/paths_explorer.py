"""Path contributions explorer widget for the AiiDAlab FEFF app (ADR 0007)."""

from __future__ import annotations

import ipywidgets as ipw
import numpy as np
import pandas as pd
from aiida_feff.data.archive import ExafsArchiveData
from aiida_feff.data.pathcontributions import PathContributionsData
from alc_aiidalab_widgets.widgets.status import Status
from ipydatagrid import DataGrid, TextRenderer
from IPython.display import display
from md_exafs.viz import group_path_results


class PathContributionsExplorer(ipw.VBox):
    """Interactive explorer for PathContributionsData and ExafsArchiveData nodes.

    Consumes md_exafs.viz for canonical grouping algorithms and Altair charts (ADR 0007).
    """

    def __init__(
        self,
        path_contributions: PathContributionsData | ExafsArchiveData,
        structure: object | None = None,
        results_model: object | None = None,
    ):
        """Build the explorer from any node exposing ``iter_paths()``."""
        self.path_contributions = path_contributions
        self.results_model = results_model
        self.path_groups = self._load_path_groups()

        self.status = Status()
        onclick_js = "window.open('http://' + window.location.hostname + ':2718/?file=paths_explorer.py', '_blank')"
        deep_dive_card = ipw.HTML(
            f"""
            <div style="margin-top: 16px; padding: 12px 16px; border: 1px solid var(--feff-rule, #D5DBE1); background: var(--feff-surface, #F4F6F8); border-radius: 4px;">
              <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;">
                <div style="flex: 1; min-width: 260px;">
                  <div style="font-weight: 600; font-size: 13px; color: var(--feff-ink, #1F2933);">
                    Deep dive: Debye–Waller factor matching & 3D scattering analysis
                  </div>
                  <div style="font-size: 12px; color: var(--feff-ink-muted, #52606D); margin-top: 2px;">
                    Correlate FEFF scattering paths with molecular dynamics Mean Square Relative Displacement (MSRD) disorder in Marimo.
                  </div>
                </div>
                <div>
                  <a href="javascript:void(0)" onclick="{onclick_js}"
                     class="jupyter-widgets jupyter-button widget-button"
                     style="display: inline-flex; align-items: center; justify-content: center; height: 32px; padding: 0 16px; text-decoration: none; background-color: var(--feff-accent, #1B5E9B); color: white; font-weight: 500; font-size: 12.5px; border-radius: 4px; cursor: pointer; white-space: nowrap;">
                    Open Debye–Waller analysis (Marimo) ↗
                  </a>
                </div>
              </div>
            </div>
            """
        )

        # Fourier transform controls: pair sliders with numeric text inputs
        ft_kmin_val = float(getattr(results_model, "ft_kmin", 2.0)) if results_model else 2.0
        ft_kmax_val = float(getattr(results_model, "ft_kmax", 14.0)) if results_model else 14.0
        ft_dk_val = float(getattr(results_model, "ft_dk", 1.0)) if results_model else 1.0
        ft_rmax_val = float(getattr(results_model, "ft_rmax", 8.0)) if results_model else 8.0
        kweight_val = int(getattr(results_model, "kweight", 2)) if results_model else 2

        self.kmin = ipw.FloatSlider(
            value=ft_kmin_val,
            min=0.0,
            max=8.0,
            step=0.1,
            description="k_min:",
            style={"description_width": "initial"},
            layout={"width": "160px"},
        )
        self.kmin_text = ipw.FloatText(value=ft_kmin_val, step=0.1, layout={"width": "65px"})
        ipw.jslink((self.kmin, "value"), (self.kmin_text, "value"))

        self.kmax = ipw.FloatSlider(
            value=ft_kmax_val,
            min=5.0,
            max=20.0,
            step=0.5,
            description="k_max:",
            style={"description_width": "initial"},
            layout={"width": "160px"},
        )
        self.kmax_text = ipw.FloatText(value=ft_kmax_val, step=0.5, layout={"width": "65px"})
        ipw.jslink((self.kmax, "value"), (self.kmax_text, "value"))

        self.dk = ipw.FloatSlider(
            value=ft_dk_val,
            min=0.0,
            max=4.0,
            step=0.1,
            description="Δk:",
            style={"description_width": "initial"},
            layout={"width": "140px"},
        )
        self.dk_text = ipw.FloatText(value=ft_dk_val, step=0.1, layout={"width": "65px"})
        ipw.jslink((self.dk, "value"), (self.dk_text, "value"))

        self.rmax = ipw.FloatSlider(
            value=ft_rmax_val,
            min=2.0,
            max=20.0,
            step=0.5,
            description="R_max:",
            style={"description_width": "initial"},
            layout={"width": "140px"},
        )
        self.rmax_text = ipw.FloatText(value=ft_rmax_val, step=0.5, layout={"width": "65px"})
        ipw.jslink((self.rmax, "value"), (self.rmax_text, "value"))

        self.kweight = ipw.Dropdown(
            options=[("k⁰", 0), ("k¹", 1), ("k²", 2), ("k³", 3)],
            value=kweight_val,
            description="k-weight:",
            style={"description_width": "initial"},
            layout={"width": "130px"},
        )

        # Sync with shared ResultsModel if provided
        if results_model is not None:
            self._syncing_model = False

            def _push_to_model(_):
                if getattr(self, "_syncing_model", False):
                    return
                self._syncing_model = True
                try:
                    self.results_model.ft_kmin = float(self.kmin.value)
                    self.results_model.ft_kmax = float(self.kmax.value)
                    self.results_model.ft_dk = float(self.dk.value)
                    self.results_model.ft_rmax = float(self.rmax.value)
                    self.results_model.kweight = int(self.kweight.value)
                finally:
                    self._syncing_model = False

            self.kmin.observe(_push_to_model, names="value")
            self.kmax.observe(_push_to_model, names="value")
            self.dk.observe(_push_to_model, names="value")
            self.rmax.observe(_push_to_model, names="value")
            self.kweight.observe(_push_to_model, names="value")

            def _pull_from_model(change):
                if getattr(self, "_syncing_model", False):
                    return
                self._syncing_model = True
                try:
                    name = change.get("name")
                    val = change.get("new")
                    if name == "ft_kmin":
                        self.kmin.value = float(val)
                    elif name == "ft_kmax":
                        self.kmax.value = float(val)
                    elif name == "ft_dk":
                        self.dk.value = float(val)
                    elif name == "ft_rmax":
                        self.rmax.value = float(val)
                    elif name == "kweight":
                        self.kweight.value = int(val)
                finally:
                    self._syncing_model = False

            self.results_model.observe(
                _pull_from_model, names=["ft_kmin", "ft_kmax", "ft_dk", "ft_rmax", "kweight"]
            )

        for slider in (self.kmin, self.kmax, self.dk, self.rmax, self.kweight):
            slider.observe(lambda _: self._on_plot(None), names="value")

        # Keep plot_button for backward compatibility
        self.plot_button = ipw.Button(
            description="Plot selected",
            button_style="primary",
            icon="chart-line",
            layout={"display": "none"},
        )
        self.plot_button.on_click(self._on_plot)

        if not self.path_groups:
            self.status.value = "No scattering paths found in this calculation."
            empty_card = ipw.HTML(
                """
                <div style='padding: 16px; color: #555; background: #fdfdfd; border: 1px solid #e0e0e0; border-radius: 6px; margin-bottom: 12px;'>
                  <div style='font-weight: 600; color: #c0392b; margin-bottom: 4px;'>No individual scattering paths were stored for this workflow.</div>
                  To store path contributions during execution, enable <b>'Store individual scattering paths'</b> in Step 2 (FEFF parameters) before launching.<br><br>
                  You can also open the Marimo Paths Explorer below to explore external HDF5 archive files or other stored runs.
                </div>
                """
            )
            super().__init__(
                [
                    empty_card,
                    deep_dive_card,
                ]
            )
            return

        self.status.value = (
            f"Loaded {len(self.path_groups)} path groups (sorted by amplitude ratio)."
        )

        overview_html = ipw.HTML(
            f"<div style='font-size: 13px; color: var(--feff-ink, #1F2933); margin-bottom: 8px;'>"
            f"<strong>Scattering paths:</strong> Loaded <strong>{len(self.path_groups)}</strong> path groups "
            f"(sorted by amplitude ratio). Click rows to toggle selection (plots update live)."
            f"</div>"
        )

        # 1. Build DataFrame for ipydatagrid DataGrid
        records = []
        for i, pg in enumerate(self.path_groups):
            records.append(
                {
                    "#": i + 1,
                    "Path": pg.get("path_key", f"Path {i + 1}"),
                    "Scatterer": pg.get("scatterer", "—"),
                    "Legs": int(pg.get("nlegs", 2)),
                    "Reff (Å)": round(float(pg.get("r_eff", 0.0)), 3),
                    "Amplitude ratio (%)": round(float(pg.get("cw_ratio", 0.0)), 1),
                    "Degeneracy": round(float(pg.get("degeneracy", 1.0)), 1),
                }
            )
        self.df = pd.DataFrame(records)

        # 2. Interactive DataGrid table widget from ipydatagrid
        self.table_widget = DataGrid(
            self.df,
            selection_mode="row",
            base_row_size=28,
            column_widths={
                "#": 45,
                "Path": 130,
                "Scatterer": 75,
                "Legs": 50,
                "Reff (Å)": 85,
                "Amplitude ratio (%)": 130,
                "Degeneracy": 85,
            },
            renderers={
                "Reff (Å)": TextRenderer(format=".3f"),
                "Amplitude ratio (%)": TextRenderer(format=".1f"),
                "Degeneracy": TextRenderer(format=".1f"),
            },
            layout=ipw.Layout(height="380px", width="100%"),
        )
        self.table = self.table_widget

        # Select initial top paths
        default_count = min(3, len(self.path_groups))
        if default_count > 0:
            self.table_widget.selections = [
                {"r1": 0, "r2": default_count - 1, "c1": 0, "c2": len(self.df.columns) - 1}
            ]

        self.charts_output = ipw.Output(layout=ipw.Layout(min_height="320px", width="100%"))

        # 4. 3-D structure viewer
        self.structure_output = ipw.Output(layout=ipw.Layout(min_height="340px", width="100%"))
        self.structure_viewer = None
        if structure is not None:
            try:
                ase_atoms = structure.get_ase() if hasattr(structure, "get_ase") else structure
                if ase_atoms is not None and len(ase_atoms) > 0:
                    from weas_widget import WeasWidget

                    self.structure_viewer = WeasWidget(from_ase=ase_atoms)
                    self.structure_viewer.layout = ipw.Layout(height="340px", width="100%")
                    with self.structure_output:
                        display(self.structure_viewer)
                else:
                    with self.structure_output:
                        print("No structure coordinates available for 3D visualization.")
            except Exception as exc:  # noqa: BLE001
                with self.structure_output:
                    print(f"Could not initialize 3D structure viewer: {exc}")
        else:
            with self.structure_output:
                print("No structure node supplied for 3D visualization.")

        self.structure_accordion = ipw.Accordion(children=[self.structure_output])
        self.structure_accordion.set_title(0, "3D Structure View")
        self.structure_accordion.selected_index = None

        ft_controls = ipw.HBox(
            [
                ipw.HBox([self.kmin, self.kmin_text], layout=ipw.Layout(align_items="center")),
                ipw.HBox([self.kmax, self.kmax_text], layout=ipw.Layout(align_items="center")),
                ipw.HBox([self.dk, self.dk_text], layout=ipw.Layout(align_items="center")),
                ipw.HBox([self.rmax, self.rmax_text], layout=ipw.Layout(align_items="center")),
                self.kweight,
            ],
            layout=ipw.Layout(
                flex_flow="row wrap",
                grid_gap="12px",
                align_items="center",
                padding="8px 12px",
                margin="0 0 12px 0",
            ),
        )

        table_and_charts = ipw.HBox(
            [
                ipw.VBox(
                    [self.table_widget], layout=ipw.Layout(flex="1 1 480px", min_width="360px")
                ),
                ipw.VBox(
                    [self.charts_output], layout=ipw.Layout(flex="1 1 480px", min_width="360px")
                ),
            ],
            layout=ipw.Layout(
                flex_flow="row wrap",
                grid_gap="16px",
                align_items="flex-start",
                width="100%",
            ),
        )

        super().__init__(
            [
                overview_html,
                ft_controls,
                table_and_charts,
                self.structure_accordion,
                deep_dive_card,
            ]
        )

        # Wire live table selection to automatic re-plotting
        self.table_widget.observe(lambda _: self._on_plot(None), names="selections")

        # Initial plot of top paths so user immediately sees results!
        self._on_plot(None)

    def _load_path_groups(self) -> list[dict]:
        """Load and group paths using canonical md_exafs.viz grouping."""
        paths = list(self.path_contributions.iter_paths())
        groups = group_path_results(paths, r_bin_width=0.1)
        # Default sorting by contribution ratio descending (highest contribution first)
        return sorted(groups, key=lambda x: float(x.get("cw_ratio", 0.0)), reverse=True)

    def _get_selected_indices(self) -> list[int]:
        """Return the indices of selected rows in the table."""
        if hasattr(self, "table_widget") and hasattr(self.table_widget, "selections"):
            num_cols = len(self.df.columns) if hasattr(self, "df") else 7
            total_rows = len(self.path_groups)

            rows = set()
            for s in self.table_widget.selections:
                r1, r2 = s.get("r1", 0), s.get("r2", 0)
                c1, c2 = s.get("c1", 0), s.get("c2", 0)

                # Ignore column header click (which selects the entire column from r=0 to r=total_rows-1)
                col_span = abs(c2 - c1) + 1
                row_span = abs(r2 - r1) + 1
                if col_span < num_cols and row_span == total_rows and total_rows > 1:
                    continue

                rmin, rmax = min(r1, r2), max(r1, r2)
                for r in range(rmin, rmax + 1):
                    if 0 <= r < total_rows:
                        rows.add(r)

            return sorted(r for r in rows if 0 <= r < total_rows)
        if hasattr(self, "table_widget") and hasattr(self.table_widget, "selected"):
            return list(self.table_widget.selected)
        if hasattr(self, "table"):
            return list(getattr(self.table, "value", ()))
        return []

    def _on_plot(self, _):
        if not getattr(self, "path_groups", None):
            return
        selected = self._get_selected_indices()
        if not selected:
            # If a column header was clicked, keep previous selection instead of clearing
            if getattr(self, "_last_selected_indices", None):
                return
            self.charts_output.clear_output()
            with self.charts_output:
                print("Select one or more paths to plot.")
            return

        self._last_selected_indices = list(selected)
        selected_groups = [self.path_groups[i] for i in selected if 0 <= i < len(self.path_groups)]
        self._plot_groups(selected_groups)

    def _plot_groups(self, groups: list[dict]):
        """Plot k-space and R-space χ for selected path groups."""
        import altair as alt

        alt.data_transformers.disable_max_rows()

        kw = int(self.kweight.value)
        k_step = 0.05
        k_new = np.arange(0.05, 20.0 + k_step / 2, k_step)

        rows_k = []
        rows_r = []
        chi_sum = np.zeros_like(k_new)

        # Cap the individual lines plotted to avoid Altair slowdown / hairball
        max_individual = 20
        individual_groups = groups[:max_individual]

        for group in groups:
            chi = self._compute_chi(group, k_new)
            chi_sum += chi

            # Only append individual path traces for the first max_individual paths
            if group in individual_groups:
                path_lbl = group["path_key"]
                y_k = chi * (k_new**kw)
                for k_val, y_val in zip(k_new, y_k, strict=False):
                    rows_k.append({"k": float(k_val), "k_chi": float(y_val), "path": path_lbl})

                # R-space via larch
                try:
                    from md_exafs.spectra import xftf_arrays

                    res = xftf_arrays(
                        k_new,
                        chi,
                        {
                            "kmin": float(self.kmin.value),
                            "kmax": float(self.kmax.value),
                            "kweight": kw,
                            "dk": float(self.dk.value),
                            "rmax": float(self.rmax.value),
                        },
                    )
                    for r_val, mag in zip(res["r"], res["chir_mag"], strict=False):
                        rows_r.append({"r": float(r_val), "chir_mag": float(mag), "path": path_lbl})
                except Exception as exc:
                    self.charts_output.clear_output()
                    with self.charts_output:
                        print(f"Error computing Fourier transform: {exc}")
                    return

        # If multiple paths selected, also plot the Sum of selected
        if len(groups) > 1:
            y_sum_k = chi_sum * (k_new**kw)
            for k_val, y_val in zip(k_new, y_sum_k, strict=False):
                rows_k.append({"k": float(k_val), "k_chi": float(y_val), "path": "Sum of selected"})

            try:
                from md_exafs.spectra import xftf_arrays

                res_sum = xftf_arrays(
                    k_new,
                    chi_sum,
                    {
                        "kmin": float(self.kmin.value),
                        "kmax": float(self.kmax.value),
                        "kweight": kw,
                        "dk": float(self.dk.value),
                        "rmax": float(self.rmax.value),
                    },
                )
                for r_val, mag in zip(res_sum["r"], res_sum["chir_mag"], strict=False):
                    rows_r.append(
                        {"r": float(r_val), "chir_mag": float(mag), "path": "Sum of selected"}
                    )
            except Exception:
                pass

        df_k = pd.DataFrame(rows_k)
        df_r = pd.DataFrame(rows_r)

        kw_title = f"k^{kw}χ(k)" if kw > 0 else "χ(k)"
        import altair as alt

        chart_k = (
            alt.Chart(df_k)
            .mark_line()
            .encode(
                x=alt.X("k:Q", title="k (Å⁻¹)"),
                y=alt.Y("k_chi:Q", title=kw_title),
                color=alt.Color("path:N", title="Path"),
                tooltip=[
                    "path:N",
                    alt.Tooltip("k:Q", format=".2f"),
                    alt.Tooltip("k_chi:Q", format=".4f"),
                ],
            )
            .properties(width=400, height=260, title=f"Scattering paths {kw_title}")
            .interactive()
        )

        chart_r = (
            alt.Chart(df_r)
            .mark_line()
            .encode(
                x=alt.X("r:Q", title="R (Å)"),
                y=alt.Y("chir_mag:Q", title="|χ(R)|"),
                color=alt.Color("path:N", title="Path"),
                tooltip=[
                    "path:N",
                    alt.Tooltip("r:Q", format=".2f"),
                    alt.Tooltip("chir_mag:Q", format=".4f"),
                ],
            )
            .properties(width=400, height=260, title=f"|χ(R)| (k-weight {kw})")
            .interactive()
        )

        self.charts_output.clear_output()
        with self.charts_output:
            display(chart_k | chart_r)  # noqa: F821

    def _compute_chi(self, group: dict, k_grid: np.ndarray) -> np.ndarray:
        """Recompute χ(k) from averaged FEFF parameters using smooth parameter interpolation."""
        reff = float(group.get("r_eff", 0.0))
        degen = float(group.get("degeneracy", 1.0))
        sig2 = float(group.get("sig2", 0.0))

        if "amp" in group and "pha" in group and "lam" in group and "rep" in group:
            k_src = np.asarray(group.get("k_param", group.get("k", [])))
            return compute_chi_from_params(
                k_grid,
                np.asarray(group["amp"]),
                np.asarray(group["pha"]),
                np.asarray(group["lam"]),
                np.asarray(group["rep"]),
                reff,
                degen,
                k_src,
                sigma2=sig2,
            )
        elif "feff_data" in group and group["feff_data"] is not None:
            fd = np.asarray(group["feff_data"])
            if fd.ndim == 2 and fd.shape[1] >= 6:
                amp = fd[:, 1] * fd[:, 3]
                pha = fd[:, 0] + fd[:, 2]
                lam = fd[:, 4]
                rep = fd[:, 5]
                k_src = np.asarray(group["k"])
                return compute_chi_from_params(
                    k_grid, amp, pha, lam, rep, reff, degen, k_src, sigma2=sig2
                )

        # Fallback if raw parameters are unavailable: interpolate coarse chi
        if "chi" in group and "k" in group:
            return np.interp(k_grid, group["k"], group["chi"], left=0.0, right=0.0)
        return np.zeros_like(k_grid)


def compute_chi_from_params(
    k_grid: np.ndarray,
    amp: np.ndarray,
    pha: np.ndarray,
    lam: np.ndarray,
    rep: np.ndarray,
    reff: float,
    degen: float,
    k_param: np.ndarray,
    sigma2: float = 0.0,
) -> np.ndarray:
    """Recompute χ(k) from averaged FEFF raw parameters on an arbitrary fine grid.

    Linearly interpolates smooth raw FEFF parameters (amp, pha, lam, rep) from
    the native coarse FEFF grid (k_param) onto k_grid, then evaluates the
    complex-momentum EXAFS equation matching Larch / Path Explorer notebook.
    This avoids interpolating oscillatory chi(k) directly or suffering cubic spline ringing.
    """
    amp_i = np.interp(k_grid, k_param, amp)
    pha_i = np.interp(k_grid, k_param, pha)
    lam_i = np.interp(k_grid, k_param, lam)
    rep_i = np.interp(k_grid, k_param, rep)

    q = k_grid
    pp = (rep_i + 1j / np.clip(lam_i, 1e-6, None)) ** 2
    p = np.sqrt(pp)

    # Full EXAFS equation with complex momentum and Debye-Waller sigma^2
    cchi = np.exp(-2.0 * reff * p.imag - 2.0 * pp * float(sigma2) + 1j * (2.0 * q * reff + pha_i))
    with np.errstate(divide="ignore", invalid="ignore"):
        cchi = float(degen) * amp_i * cchi / (q * (reff**2))
    chi = np.asarray(cchi.imag, dtype=np.float64)
    chi[~np.isfinite(chi)] = 0.0
    return chi

    def set_structure(self, structure_node):
        """Set an optional structure for the 3-D viewer."""
        try:
            ase_atoms = (
                structure_node.get_ase() if hasattr(structure_node, "get_ase") else structure_node
            )
            if ase_atoms is not None and len(ase_atoms) > 0:
                self.structure_output.clear_output()
                from weas_widget import WeasWidget

                self.structure_viewer = WeasWidget(from_ase=ase_atoms)
                self.structure_viewer.layout = ipw.Layout(height="400px", width="100%")
                with self.structure_output:
                    display(self.structure_viewer)
        except Exception as exc:  # noqa: BLE001
            with self.structure_output:
                print(f"Could not load structure: {exc}")
