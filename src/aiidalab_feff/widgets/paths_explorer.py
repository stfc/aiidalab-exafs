"""Path contributions explorer widget for the AiiDAlab FEFF app (ADR 0007)."""

from __future__ import annotations

import ipywidgets as ipw
import numpy as np
import pandas as pd
from aiida_feff.data.archive import ExafsArchiveData
from aiida_feff.data.pathcontributions import PathContributionsData
from alc_aiidalab_widgets.widgets.status import Status
from IPython.display import display
from md_exafs.viz import build_chi_chart, build_chir_chart, group_path_results
from weas_widget import WeasWidget


class PathContributionsExplorer(ipw.VBox):
    """Interactive explorer for PathContributionsData and ExafsArchiveData nodes.

    Consumes md_exafs.viz for canonical grouping algorithms and Altair charts (ADR 0007).
    """

    def __init__(self, path_contributions: PathContributionsData | ExafsArchiveData):
        """Build the explorer from any node exposing ``iter_paths()``."""
        self.path_contributions = path_contributions
        self.path_groups = self._load_path_groups()

        self.status = Status()
        self.status.value = f"Loaded {len(self.path_groups)} path groups."

        self.table = self._build_table()

        self.kmin = ipw.FloatSlider(value=2.0, min=0.0, max=8.0, step=0.1, description="kmin")
        self.kmax = ipw.FloatSlider(value=14.0, min=5.0, max=20.0, step=0.5, description="kmax")
        self.kweight = ipw.Dropdown(options=[1, 2, 3], value=2, description="k-weight")
        self.dk = ipw.FloatSlider(value=1.0, min=0.0, max=4.0, step=0.1, description="dk")
        self.rmax = ipw.FloatSlider(value=8.0, min=2.0, max=20.0, step=0.5, description="Rmax")

        self.plot_button = ipw.Button(
            description="Plot selected",
            button_style="primary",
            icon="chart-line",
        )
        self.plot_button.on_click(self._on_plot)

        self.charts_output = ipw.Output()
        self.structure_viewer = WeasWidget()

        controls = ipw.VBox(
            [
                ipw.HBox([self.kmin, self.kmax, self.kweight]),
                ipw.HBox([self.dk, self.rmax]),
                self.plot_button,
            ]
        )

        super().__init__(
            [
                self.status,
                ipw.HTML("<h3>Path groups</h3>"),
                self.table,
                ipw.HTML("<h3>Fourier transform controls</h3>"),
                controls,
                self.charts_output,
                self.structure_viewer,
            ]
        )

    def _load_path_groups(self) -> list[dict]:
        """Load and group paths using canonical md_exafs.viz grouping."""
        paths = list(self.path_contributions.iter_paths())
        return group_path_results(paths, r_bin_width=0.1)

    def _build_table(self) -> ipw.SelectMultiple:
        """Build a selectable table of path groups."""
        options = [
            (f"{pg['path_key']}  R={pg['r_eff']:.2f}Å  CW={pg['cw_ratio']:.1f}", i)
            for i, pg in enumerate(self.path_groups)
        ]
        selector = ipw.SelectMultiple(
            options=options,
            description="Paths:",
            rows=10,
            layout={"width": "100%"},
        )
        return selector

    def _get_selected_indices(self) -> list[int]:
        """Return the indices of selected rows in the table."""
        return list(self.table.value)

    def _on_plot(self, _):
        selected = self._get_selected_indices()
        if not selected:
            self.charts_output.clear_output()
            with self.charts_output:
                print("Select one or more paths to plot.")
            return

        selected_groups = [self.path_groups[i] for i in selected if 0 <= i < len(self.path_groups)]
        self._plot_groups(selected_groups)

    def _plot_groups(self, groups: list[dict]):
        """Plot k-space and R-space χ for selected path groups."""
        k_new = np.arange(0.05, 20.0, 0.05)

        rows = []
        for group in groups:
            chi = self._compute_chi(group, k_new)
            rows.append(
                {
                    "path": group["path_key"],
                    "k": k_new,
                    "chi": chi,
                }
            )

        # k-space plot using md_exafs.viz
        df_k = pd.DataFrame(
            [
                {"k": k_val, "chi": chi_val, "path": row["path"]}
                for row in rows
                for k_val, chi_val in zip(row["k"], row["chi"], strict=False)
            ]
        )
        chart_k = build_chi_chart(df_k)

        # R-space via larch
        df_r = pd.DataFrame()
        for row in rows:
            try:
                from md_exafs.spectra import xftf_arrays

                res = xftf_arrays(
                    row["k"],
                    row["chi"],
                    {
                        "kmin": float(self.kmin.value),
                        "kmax": float(self.kmax.value),
                        "kweight": int(self.kweight.value),
                        "dk": float(self.dk.value),
                        "rmax": float(self.rmax.value),
                    },
                )
                df_r = pd.concat(
                    [
                        df_r,
                        pd.DataFrame(
                            {
                                "r": res["r"],
                                "chir_mag": res["chir_mag"],
                                "path": row["path"],
                            }
                        ),
                    ]
                )
            except ImportError:
                self.charts_output.clear_output()
                with self.charts_output:
                    print("larch is required for R-space plots.")
                return

        # R-space plot using md_exafs.viz
        chart_r = build_chir_chart(df_r)

        self.charts_output.clear_output()
        with self.charts_output:
            display(chart_k | chart_r)  # noqa: F821

    def _compute_chi(self, group: dict, k_grid: np.ndarray) -> np.ndarray:
        """Recompute χ(k) from averaged FEFF parameters using the canonical EXAFS equation."""
        from md_exafs.paths import path_chi

        return path_chi(
            k_native=group["k"],
            feff_data=group["feff_data"],
            r_eff=group["r_eff"],
            degeneracy=group["degeneracy"],
            k_out=k_grid,
            sigma2=float(group.get("sig2", 0.0)),
        )

    def set_structure(self, structure_node):
        """Set an optional structure for the 3-D viewer."""
        try:
            self.structure_viewer.from_ase(structure_node.get_ase())  # type: ignore[attr-defined]
        except Exception as exc:  # noqa: BLE001
            self.status.value = f"Could not load structure: {exc}"
