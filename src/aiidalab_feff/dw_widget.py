"""Interactive In-Memory Debye-Waller / MSRD Trajectory Screening Widget (ADR 0005).

Runs directly on TrajectoryData positions in < 3 seconds without launching an HPC job,
allowing users to verify thermal disorder and B-factors before starting FEFF runs.
"""

from __future__ import annotations

from typing import Any

import ipywidgets as ipw
import numpy as np
import pandas as pd
from alc_aiidalab_widgets.widgets.loading import LoadingWidget
from IPython.display import display
from md_exafs.debye_waller import (
    calculate_grouped_msrd,
    compute_adp_results,
    unwrap_positions_pbc,
)
from md_exafs.viz import build_sigma2_chart


class DebyeWallerScreeningWidget(ipw.VBox):
    """In-memory disorder pre-screening widget for trajectories."""

    def __init__(self, input_model: Any | None = None):
        """Initialize DebyeWallerScreeningWidget."""
        self.input_model = input_model

        self._header = ipw.HTML(
            "<h4>Debye–Waller disorder screening</h4>"
            "<p>Analyze trajectory positions to preview path variances (σ²) "
            "and B-factors before launching calculations.</p>"
        )

        self.absorber = ipw.Text(
            value="",
            placeholder="e.g. Cu or 0",
            description="Absorber:",
            layout={"width": "250px"},
        )
        self.max_r = ipw.FloatSlider(
            value=5.0,
            min=2.0,
            max=10.0,
            step=0.5,
            description="Rmax (Å):",
            layout={"width": "350px"},
        )
        self.run_button = ipw.Button(
            description="Screen disorder",
            button_style="info",
            icon="bolt",
            layout={"width": "180px"},
        )
        self.run_button.on_click(self._on_run)

        onclick_js = "window.open('http://' + window.location.hostname + ':2718/?file=debye_waller.py', '_blank')"
        style_css = (
            "display: inline-flex; align-items: center; justify-content: center; "
            "height: 28px; padding: 0 12px; margin-left: 6px; text-decoration: none; "
            "background-color: #2b7a78; color: white; font-weight: 600; "
            "border-radius: 4px; box-shadow: 0 1px 2px rgba(0,0,0,0.1); cursor: pointer;"
        )
        self.marimo_link = ipw.HTML(
            f'<a href="javascript:void(0)" onclick="{onclick_js}" '
            f'class="jupyter-widgets jupyter-button widget-button" style="{style_css}" '
            'title="Open dedicated Marimo Debye-Waller notebook on port 2718">'
            '<span style="margin-right: 5px;">⚡</span> Open in Marimo ↗</a>'
        )

        self.results_output = ipw.Output()

        controls = ipw.HBox([self.absorber, self.max_r, self.run_button, self.marimo_link])

        super().__init__(
            [
                self._header,
                controls,
                self.results_output,
            ]
        )

    def _extract_structures(self) -> list[Any] | None:
        """Extract ASE Atoms list from the input model."""
        if self.input_model is None:
            return None

        # 1. TrajectoryData input
        if getattr(self.input_model, "trajectory", None) is not None:
            traj = self.input_model.trajectory
            try:
                import ase

                step_ids = getattr(self.input_model, "selected_indices", None)
                if not step_ids:
                    step_ids = list(traj.get_stepids()) if hasattr(traj, "get_stepids") else None
                if not step_ids:
                    step_ids = list(range(len(traj.get_array("positions"))))

                symbols = traj.symbols
                positions_all = traj.get_array("positions")
                has_cells = "cells" in traj.get_arraynames()
                cells_all = traj.get_array("cells") if has_cells else None
                pbc = getattr(traj, "pbc", (True, True, True))

                return [
                    ase.Atoms(
                        symbols=symbols,
                        positions=positions_all[idx],
                        cell=cells_all[idx] if has_cells else None,
                        pbc=pbc if has_cells else False,
                    )
                    for idx in step_ids
                ]
            except Exception as exc:  # noqa: BLE001
                print(f"Error reading trajectory: {exc}")
                return None

        raw_list = None
        if getattr(self.input_model, "structures", None):
            raw_list = list(self.input_model.structures.values())
        elif hasattr(self.input_model, "get_structures"):
            s_dict = self.input_model.get_structures()
            raw_list = list(s_dict.values()) if s_dict else None
        elif getattr(self.input_model, "structure", None) is not None:
            raw_list = [self.input_model.structure]

        if raw_list is not None:
            return [s.get_ase() if hasattr(s, "get_ase") else s for s in raw_list]

        return None

    def _on_run(self, _):
        self.results_output.clear_output()
        with self.results_output:
            display(LoadingWidget(message="Computing Debye–Waller MSRD and B-factors in-memory..."))
            ase_structures = self._extract_structures()

            if not ase_structures:
                print("No trajectory or structures loaded in Step 1.")
                return

            if len(ase_structures) < 2:
                print(
                    "Debye–Waller disorder screening requires a trajectory with at least 2 frames "
                    f"(got {len(ase_structures)} frame)."
                )
                return

            # Resolve central absorber indices and label
            spec = self.absorber.value.strip()
            central_indices: list[int] = []
            central_label = ""
            first_frame = ase_structures[0]

            if spec:
                parts = [p.strip() for p in spec.split(",")]
                if all(p.isdigit() for p in parts):
                    central_indices = [int(p) for p in parts if int(p) < len(first_frame)]
                    if central_indices:
                        central_label = first_frame[central_indices[0]].symbol
                else:
                    sym = spec.capitalize()
                    central_indices = [
                        i for i, a in enumerate(first_frame) if a.symbol.upper() == spec.upper()
                    ]
                    if central_indices:
                        central_label = sym

            if not central_indices and self.input_model is not None:
                abs_atoms = getattr(self.input_model, "absorbing_atoms", []) or []
                if abs_atoms:
                    central_indices = [int(i) for i in abs_atoms if int(i) < len(first_frame)]
                    if central_indices:
                        central_label = first_frame[central_indices[0]].symbol

            if not central_indices:
                central_indices = [0]
                central_label = first_frame[0].symbol

            if not self.absorber.value and central_label:
                self.absorber.value = central_label

            try:
                print(
                    f"Computing MSRD and B-factors in-memory for {central_label} "
                    f"({len(central_indices)} sites) over {len(ase_structures)} frames..."
                )
                cutoff_val = float(self.max_r.value)
                res_2b, res_3b = calculate_grouped_msrd(
                    ase_structures,
                    central_indices=central_indices,
                    central_label=central_label,
                    cutoff=cutoff_val,
                    cutoff_3body=cutoff_val,
                )

                unwrapped = unwrap_positions_pbc(ase_structures)
                adp_res = compute_adp_results(ase_structures, unwrapped)

                rows = []
                for p in res_2b:
                    scat = (
                        p.get("type", "").split("-")[-1]
                        if "-" in p.get("type", "")
                        else p.get("type", "2-body")
                    )
                    rows.append(
                        {
                            "path": f"{p.get('type', '2-body')} (N={p.get('count', 1)})",
                            "scatterer": scat,
                            "r_eff": float(p.get("reff", 0.0)),
                            "sigma2": float(p.get("sigma2", 0.0)),
                        }
                    )
                for p in res_3b:
                    scat = p.get("type", "").split("-")[1] if "-" in p.get("type", "") else "3-body"
                    rows.append(
                        {
                            "path": f"{p.get('type', '3-body')} (N={p.get('count', 1)})",
                            "scatterer": scat,
                            "r_eff": float(p.get("reff", 0.0)),
                            "sigma2": float(p.get("sigma2", 0.0)),
                        }
                    )

                if rows:
                    df = pd.DataFrame(rows)
                    chart = build_sigma2_chart(df, title=f"σ² vs R_eff ({central_label})")
                    display(chart)
                    print(
                        f"✓ Calculated {len(rows)} scattering path variances "
                        f"({len(res_2b)} 2-body, {len(res_3b)} 3-body)."
                    )
                else:
                    print("No paths found within cutoff radius.")

                # Display B-factor summary
                if "b_factors" in adp_res:
                    mean_b = float(np.mean(adp_res["b_factors"]))
                    abs_b = float(np.mean([adp_res["b_factors"][i] for i in central_indices]))
                    print(f"Mean isotropic B-factor (all atoms): {mean_b:.3f} Å²")
                    print(f"Mean isotropic B-factor ({central_label} absorbers): {abs_b:.3f} Å²")

            except Exception as err:  # noqa: BLE001
                print(f"Debye–Waller screening failed: {err}")


__all__ = [
    "DebyeWallerScreeningWidget",
]
