"""FEFF parameters form for the AiiDAlab FEFF app."""

from __future__ import annotations

from typing import Any

import ipywidgets as ipw
from aiida_feff.data.parameters import VALID_EDGE_LABELS, FeffParameters

from aiidalab_feff.models import WorkflowModel


def _get_edge_options(absorber: str = "") -> list[tuple[str, str]]:
    """Return human-readable edge labels paired with FEFF edge codes."""
    prefix = f"{absorber} " if absorber else ""
    edges = [
        ("K-edge", "K"),
        ("L₁-edge", "L1"),
        ("L₂-edge", "L2"),
        ("L₃-edge", "L3"),
        ("M₁-edge", "M1"),
        ("M₂-edge", "M2"),
        ("M₃-edge", "M3"),
        ("M₄-edge", "M4"),
        ("M₅-edge", "M5"),
    ]
    return [(f"{prefix}{label}", code) for label, code in edges if code in VALID_EDGE_LABELS]


class FeffParametersWidget(ipw.VBox):
    """Widget for editing FEFF calculation parameters with presets and advanced cards."""

    def __init__(self, model: WorkflowModel, input_model: Any | None = None):
        self.model = model
        self.model.path_cw_threshold = -1.0
        self._input_model = input_model or getattr(model, "input_model", None)
        self._updating_preset = False

        self._header = ipw.HTML("<h2>FEFF parameters</h2>")

        # Preset segmented control
        self.preset_selector = ipw.ToggleButtons(
            options=["Quick look", "Standard", "Publication", "Custom"],
            value="Standard",
            description="Preset:",
            style={"description_width": "initial", "button_width": "auto"},
            layout={"margin": "4px 0 10px 0"},
        )
        self.preset_selector.observe(self._on_preset_change, names="value")

        self.preset_info = ipw.HTML(
            "<div style='font-size:12px;color:var(--feff-ink-muted, #555);margin-bottom:12px;'>"
            "Standard precision suitable for most EXAFS analysis (recommended default)."
            "</div>"
        )

        # Basic parameters
        self.edge = ipw.Dropdown(
            options=_get_edge_options(),
            value="K",
            description="Absorption edge:",
            style={"description_width": "initial"},
            layout={"width": "260px", "min_width": "200px"},
        )
        self.radius = ipw.FloatText(
            value=5.5,
            description="Cluster radius (Å):",
            tooltip="Cluster radius around the absorber in Ångströms (SCF and scattering path radius).",
            style={"description_width": "initial"},
            layout={"width": "220px"},
        )
        self.s02 = ipw.FloatText(
            value=1.0,
            description="S₀² (intrinsic):",
            tooltip="Intrinsic many-body amplitude reduction factor (typically 0.85–1.0).",
            style={"description_width": "initial"},
            layout={"width": "200px"},
        )
        self.nleg = ipw.IntText(
            value=6,
            description="Max legs (NLEG):",
            tooltip="Maximum number of scattering legs (2 = single scattering, 3 = double, etc.)",
            style={"description_width": "initial"},
            layout={"width": "200px"},
        )

        self.radius.observe(self._on_parameter_user_edit, names="value")
        self.nleg.observe(self._on_parameter_user_edit, names="value")

        # Checkboxes with short labels and help text
        self.precompute_potentials = ipw.Checkbox(
            value=False,
            description="Precompute potentials",
            indent=False,
            layout={"width": "auto"},
        )
        self.precompute_help = ipw.HTML(
            "<div style='font-size:12px;color:var(--feff-ink-muted, #666);margin-left:24px;margin-bottom:8px;line-height:1.3;'>"
            "Computes potentials once per site and reuses them across frames. Faster, but ignores frame-to-frame electronic variations (default: off)."
            "</div>"
        )
        self.precompute_potentials.observe(self._on_parameter_user_edit, names="value")

        self.store_paths = ipw.Checkbox(
            value=False,
            description="Store individual scattering paths",
            indent=False,
            layout={"width": "auto"},
        )
        self.store_paths_help = ipw.HTML(
            "<div style='font-size:12px;color:var(--feff-ink-muted, #666);margin-left:24px;margin-bottom:8px;line-height:1.3;'>"
            "Needed for the Path contributions tab. Auto-enabled when frame count is small (≤ 10 frames)."
            "</div>"
        )

        self.path_cw_threshold = ipw.FloatText(
            value=5.0,
            description="Amplitude ratio (%):",
            tooltip="Curved-wave amplitude ratio threshold relative to strongest path (0 = keep all).",
            style={"description_width": "initial"},
            layout={"width": "240px"},
        )
        self.path_cw_threshold.layout.display = "none"
        self.path_box = ipw.VBox(
            [
                ipw.HBox(
                    [self.store_paths, self.path_cw_threshold],
                    layout=ipw.Layout(align_items="center"),
                ),
                self.store_paths_help,
            ]
        )

        def _on_store_paths_change(change):
            if change["new"]:
                self.path_cw_threshold.layout.display = "block"
                self.model.path_cw_threshold = self.path_cw_threshold.value
            else:
                self.path_cw_threshold.layout.display = "none"
                self.model.path_cw_threshold = -1.0

        self.store_paths.observe(_on_store_paths_change, names="value")

        self.exclude_hydrogen = ipw.Checkbox(
            value=False,
            description="Exclude hydrogen",
            indent=False,
            layout={"width": "auto"},
        )
        self.exclude_hydrogen_help = ipw.HTML(
            "<div style='font-size:12px;color:var(--feff-ink-muted, #666);margin-left:24px;margin-bottom:12px;line-height:1.3;'>"
            "Omit light hydrogen scatterers from the FEFF cluster to speed up calculation."
            "</div>"
        )

        # Advanced card overrides
        field_style = {"description_width": "180px"}
        field_layout = ipw.Layout(width="380px")

        self.control = ipw.Text(
            value="",
            placeholder="Default: 1 1 1 1 1 1 (all)",
            description="CONTROL (def: 1 1 1 1 1 1):",
            tooltip="Module execution control flags: mphase mpath mfeff mchi. 1 = run, 0 = skip.",
            style=field_style,
            layout=field_layout,
        )
        self.print = ipw.Text(
            value="1 0 0 0 0 3",
            placeholder="Default: 1 0 0 0 0 3",
            description="PRINT (def: 1 0 0 0 0 3):",
            tooltip="Print levels for FEFF modules (ipr1..ipr6). 3 in last slot prints chi.dat.",
            style=field_style,
            layout=field_layout,
        )
        self.exchange = ipw.Text(
            value="0 0 0",
            placeholder="Default: 0 0 0",
            description="EXCHANGE (def: 0 0 0):",
            tooltip="Exchange model: ixc [vr0 vi0]. 0 = Hedin-Lundqvist, 1 = Dirac-Hara.",
            style=field_style,
            layout=field_layout,
        )
        self.scf = ipw.Text(
            value="",
            placeholder="Default: auto (from radius)",
            description="SCF (def: auto):",
            tooltip="Self-consistent field: r_scf [l_scf n_scf ca_scf nmix]. Auto-derived from cluster radius if left empty.",
            style=field_style,
            layout=field_layout,
        )
        self.criteria = ipw.Text(
            value="",
            placeholder="Default: 4.0 2.5",
            description="CRITERIA (def: 4.0 2.5):",
            tooltip="Path filter criteria: critcw critpw (percent of largest path amplitude).",
            style=field_style,
            layout=field_layout,
        )
        self.criteria.observe(self._on_parameter_user_edit, names="value")

        self.exafs = ipw.IntText(
            value=0,
            description="EXAFS k_max (def: auto):",
            tooltip="Maximum k (Å⁻¹) for EXAFS output. 0 uses FEFF default (~20 Å⁻¹).",
            style=field_style,
            layout=field_layout,
        )
        self.delete_tags = ipw.Text(
            value="",
            placeholder="e.g. STRUN, NOHOLE",
            description="Delete tags (def: none):",
            tooltip="Comma-separated card names to strip from generated feff.inp (COREHOLE is stripped automatically).",
            style=field_style,
            layout=ipw.Layout(width="560px"),
        )

        self.reset_advanced_button = ipw.Button(
            description="Reset to defaults",
            icon="undo",
            tooltip="Reset all advanced card fields to their standard defaults",
            layout=ipw.Layout(width="160px"),
        )
        self.reset_advanced_button.on_click(self.reset_advanced)

        self.advanced_info = ipw.HTML(
            "<div style='font-size: 12px; color: var(--feff-ink-muted, #555); margin-bottom: 6px;'>"
            "<b>Advanced FEFF Cards:</b> Optional overrides for <code>feff.inp</code>. "
            "Values showing <i>auto</i> are derived automatically from the cluster radius / FEFF standards. "
            "Leave blank or click <b>Reset to defaults</b> to use standard values."
            "</div>"
        )

        self.advanced_box = ipw.VBox(
            [
                self.advanced_info,
                ipw.HBox([self.control, self.print]),
                ipw.HBox([self.exchange, self.scf]),
                ipw.HBox([self.criteria, self.exafs]),
                ipw.HBox(
                    [self.delete_tags, self.reset_advanced_button],
                    layout=ipw.Layout(align_items="center"),
                ),
            ],
            layout=ipw.Layout(
                padding="10px 14px",
            ),
        )

        self.advanced_cards_accordion = ipw.Accordion(children=[self.advanced_box])
        self.advanced_cards_accordion.set_title(
            0, "Advanced FEFF cards (CONTROL, PRINT, EXCHANGE, SCF, etc.)"
        )
        self.advanced_cards_accordion.selected_index = None

        # Backward compatibility alias
        self.advanced_toggle = ipw.ToggleButton(value=False, layout={"display": "none"})

        # Debye-Waller pre-screening widget (G4: dropped "In-Memory")
        from aiidalab_feff.dw_widget import DebyeWallerScreeningWidget

        self.dw_screening = DebyeWallerScreeningWidget(self._input_model)
        self.dw_accordion = ipw.Accordion(children=[self.dw_screening])
        self.dw_accordion.set_title(
            0, "Debye–Waller screening (estimate thermal disorder before full calculation)"
        )
        self.dw_accordion.selected_index = None

        self.path_cw_threshold.observe(self._on_path_cw_threshold_change, names="value")
        self.precompute_potentials.observe(self._on_precompute_change, names="value")

        super().__init__(
            [
                self._header,
                self.preset_selector,
                self.preset_info,
                ipw.HBox(
                    [self.edge, self.radius, self.s02, self.nleg],
                    layout=ipw.Layout(flex_flow="row wrap", grid_gap="12px", margin="6px 0 12px 0"),
                ),
                self.precompute_potentials,
                self.precompute_help,
                self.path_box,
                self.exclude_hydrogen,
                self.exclude_hydrogen_help,
                ipw.HTML(
                    "<hr style='border:none;border-top:1px solid var(--feff-rule, #ddd);margin:12px 0;'>"
                ),
                self.advanced_cards_accordion,
                self.dw_accordion,
            ]
        )
        self._update_absorber_in_edge()

    def _on_preset_change(self, change):
        preset = change["new"]
        self.model.preset = preset
        self._updating_preset = True
        try:
            if preset == "Quick look":
                self.radius.value = 4.5
                self.nleg.value = 4
                self.criteria.value = "6.0 4.0"
                self.precompute_potentials.value = True
                self.preset_info.value = (
                    "<div style='font-size:12px;color:var(--feff-caution, #b26a00);margin-bottom:12px;'>"
                    "<strong>Quick look:</strong> Radius 4.5 Å, NLEG 4, precomputing potentials. Faster screening run."
                    "</div>"
                )
            elif preset == "Standard":
                self.radius.value = 5.5
                self.nleg.value = 6
                self.criteria.value = "4.0 2.5"
                self.precompute_potentials.value = False
                self.preset_info.value = (
                    "<div style='font-size:12px;color:var(--feff-ink-muted, #555);margin-bottom:12px;'>"
                    "<strong>Standard:</strong> Radius 5.5 Å, NLEG 6. Balanced accuracy for most EXAFS analyses."
                    "</div>"
                )
            elif preset == "Publication":
                self.radius.value = 6.5
                self.nleg.value = 8
                self.criteria.value = "2.0 1.0"
                self.precompute_potentials.value = False
                self.preset_info.value = (
                    "<div style='font-size:12px;color:var(--feff-success, #2e7d4f);margin-bottom:12px;'>"
                    "<strong>Publication:</strong> Radius 6.5 Å, NLEG 8, fine criteria. High-precision full simulation."
                    "</div>"
                )
            elif preset == "Custom":
                self.preset_info.value = (
                    "<div style='font-size:12px;color:var(--feff-ink-muted, #555);margin-bottom:12px;'>"
                    "<strong>Custom:</strong> User-modified parameters."
                    "</div>"
                )
        finally:
            self._updating_preset = False

    def _on_parameter_user_edit(self, _):
        if not self._updating_preset and self.preset_selector.value != "Custom":
            self.preset_selector.value = "Custom"

    def _update_absorber_in_edge(self):
        absorber = ""
        if self._input_model is not None:
            symbols = None
            if getattr(self._input_model, "trajectory", None) is not None:
                symbols = getattr(self._input_model.trajectory, "symbols", None)
            elif getattr(self._input_model, "structure", None) is not None:
                from aiidalab_feff.utils import get_symbols

                symbols = get_symbols(self._input_model.structure)
            if symbols and self._input_model.absorbing_atoms:
                idx = self._input_model.absorbing_atoms[0]
                if 0 <= idx < len(symbols):
                    absorber = symbols[idx]
        cur_val = self.edge.value
        self.edge.options = _get_edge_options(absorber)
        if cur_val in [opt[1] for opt in self.edge.options]:
            self.edge.value = cur_val

    @property
    def input_model(self) -> Any | None:
        """Return the current input model."""
        return self._input_model

    @input_model.setter
    def input_model(self, value: Any | None):
        """Update the input model and forward it to the Debye-Waller screening widget."""
        self._input_model = value
        if hasattr(self, "dw_screening"):
            self.dw_screening.input_model = value
        self._update_absorber_in_edge()

        # Auto-enable store_paths if frame count is small (<= 10 frames)
        if value is not None:
            n_frames = 1
            if getattr(value, "trajectory", None) is not None and getattr(
                value, "selected_indices", None
            ):
                n_frames = len(value.selected_indices)
            elif getattr(value, "structures", None):
                n_frames = len(value.structures)
            if n_frames <= 10:
                self.store_paths.value = True

    def _on_path_cw_threshold_change(self, change):
        if self.store_paths.value:
            self.model.path_cw_threshold = change["new"]
        else:
            self.model.path_cw_threshold = -1.0

    def _on_precompute_change(self, change):
        self.model.precompute_potentials = change["new"]

    def get_parameter_dict(self) -> dict:
        """Return the dictionary of FEFF parameters from the form values."""
        params: dict = {
            "edge": self.edge.value,
            "spectrum_type": "EXAFS",
            "radius": self.radius.value,
            "s02": self.s02.value,
            "nleg": self.nleg.value,
            "exclude_hydrogen": self.exclude_hydrogen.value,
            "exchange": self.exchange.value,
            "print": self.print.value,
        }

        if self.scf.value.strip():
            params["scf"] = self.scf.value.strip()
        if self.control.value.strip():
            params["control"] = self.control.value.strip()
        if self.exafs.value and self.exafs.value > 0:
            params["exafs"] = self.exafs.value
        if self.criteria.value.strip():
            params["criteria"] = self.criteria.value.strip()
        if self.delete_tags.value.strip():
            params["delete_tags"] = [
                t.strip() for t in self.delete_tags.value.split(",") if t.strip()
            ]

        return params

    def get_parameters(self) -> FeffParameters:
        """Return a validated FeffParameters node from the form values."""
        return FeffParameters(dict=self.get_parameter_dict())

    def get_path_cw_threshold(self) -> float:
        """Return the path CW threshold used by the process builder."""
        return self.path_cw_threshold.value if self.store_paths.value else -1.0

    def validate(self) -> list[str]:
        """Return a list of validation error messages."""
        errors = []
        if self.radius.value <= 0:
            errors.append("Radius (cluster radius) must be greater than 0.")
        if self.s02.value < 0:
            errors.append("S₀² must be greater than or equal to 0.")
        if self.nleg.value <= 0:
            errors.append("NLEG (max scattering legs) must be greater than 0.")
        try:
            params = self.get_parameter_dict()
            FeffParameters._validate_keys(params)
        except ValueError as exc:
            errors.append(str(exc))
        return errors

    def reset_advanced(self, _=None):
        """Reset all advanced card fields to their standard defaults."""
        self.control.value = ""
        self.print.value = "1 0 0 0 0 3"
        self.exchange.value = "0 0 0"
        self.scf.value = ""
        self.criteria.value = ""
        self.exafs.value = 0
        self.delete_tags.value = ""

    def reset(self):
        """Reset the form to defaults."""
        self.preset_selector.value = "Standard"
        self.edge.value = "K"
        self.radius.value = 5.5
        self.s02.value = 1.0
        self.nleg.value = 6
        self.exclude_hydrogen.value = False
        self.store_paths.value = False
        self.path_cw_threshold.value = 5.0
        self.path_cw_threshold.layout.display = "none"
        self.precompute_potentials.value = False
        self.model.path_cw_threshold = -1.0
        self.model.precompute_potentials = False
        self.model.preset = "standard"
        self.reset_advanced()
        self.advanced_cards_accordion.selected_index = None
        self.dw_accordion.selected_index = None
