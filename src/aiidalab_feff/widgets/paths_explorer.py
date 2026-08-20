"""Path contributions explorer widget for the AiiDAlab FEFF app."""

from __future__ import annotations

from collections import defaultdict

import altair as alt
import ipywidgets as ipw
import numpy as np
import pandas as pd
from aiida_feff.data.pathcontributions import FEFF_DATA_COLS, PathContributionsData
from alc_aiidalab_widgets.widgets.status import Status
from IPython.display import display
from weas_widget.atoms_viewer import AtomsViewer


class PathContributionsExplorer(ipw.VBox):
    """Interactive explorer for PathContributionsData nodes.

    This is an ipywidgets-based widget (not a true anywidget) because the
    underlying visualisation libraries (altair, weas-widget) are already
    ipywidgets-compatible.
    """

    def __init__(self, path_contributions: PathContributionsData):
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
        self.structure_viewer = AtomsViewer()  # type: ignore[call-arg]

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
        """Load and group paths from the PathContributionsData node."""
        groups: dict[tuple[str, int, float], list[dict]] = defaultdict(list)
        for path in self.path_contributions.iter_paths():
            r_bin = round(path.r_eff / 0.1) * 0.1
            key = (path.scatterer, path.nlegs, r_bin)
            groups[key].append(
                {
                    "scatterer": path.scatterer,
                    "nlegs": path.nlegs,
                    "r_eff": path.r_eff,
                    "degeneracy": path.degeneracy,
                    "cw_ratio": path.cw_ratio,
                    "sig2": getattr(path, "sig2", 0.0),
                    "k": path.k,
                    "feff_data": path.feff_data,
                }
            )

        path_groups = []
        for (scatterer, nlegs, r_bin), items in groups.items():
            k = items[0]["k"]
            feff_data = np.mean([item["feff_data"] for item in items], axis=0)
            degen = np.mean([item["degeneracy"] for item in items])
            r_eff = np.mean([item["r_eff"] for item in items])
            cw_ratio = np.mean([item["cw_ratio"] for item in items])
            sig2 = np.mean([item.get("sig2", 0.0) for item in items])
            path_groups.append(
                {
                    "path_key": f"{scatterer}_{nlegs}_{r_bin:.2f}",
                    "scatterer": scatterer,
                    "nlegs": nlegs,
                    "r_eff": r_eff,
                    "degeneracy": degen,
                    "cw_ratio": cw_ratio,
                    "sig2": sig2,
                    "k": k,
                    "feff_data": feff_data,
                }
            )
        return sorted(path_groups, key=lambda x: x["r_eff"])

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

        # k-space plot
        df_k = pd.DataFrame(
            [
                {"k": k_val, "chi": chi_val, "path": row["path"]}
                for row in rows
                for k_val, chi_val in zip(row["k"], row["chi"], strict=False)
            ]
        )
        chart_k = (
            alt.Chart(df_k)
            .mark_line()
            .encode(
                x="k:Q",
                y="chi:Q",
                color="path:N",
            )
            .properties(width=400, height=250, title="χ(k)")
        )

        # R-space via larch
        df_r = pd.DataFrame()
        for row in rows:
            try:
                from aiida_feff.calcfunctions.larch import xftf_arrays

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

        chart_r = (
            alt.Chart(df_r)
            .mark_line()
            .encode(
                x="r:Q",
                y="chir_mag:Q",
                color="path:N",
            )
            .properties(width=400, height=250, title="|χ(R)|")
        )

        self.charts_output.clear_output()
        with self.charts_output:
            display(chart_k | chart_r)  # noqa: F821

    def _compute_chi(self, group: dict, k_grid: np.ndarray) -> np.ndarray:
        """Recompute χ(k) from averaged FEFF parameters using the canonical EXAFS equation."""
        from aiida_feff.calcfunctions.exafs import path_chi

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
