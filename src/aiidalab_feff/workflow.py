"""FEFF parameters form for the AiiDAlab FEFF app."""

from __future__ import annotations

import ipywidgets as ipw
from aiida_feff.data.parameters import VALID_EDGE_LABELS, FeffParameters

from aiidalab_feff.models import WorkflowModel


class FeffParametersWidget(ipw.VBox):
    """Widget for editing FEFF calculation parameters."""

    def __init__(self, model: WorkflowModel):
        self.model = model
        self.model.path_cw_threshold = -1.0

        self._header = ipw.HTML("<h2>FEFF parameters</h2>")

        # Basic parameters
        self.edge = ipw.Dropdown(
            options=sorted(VALID_EDGE_LABELS),
            value="K",
            description="Edge:",
            layout={"width": "120px"},
        )
        self.radius = ipw.FloatText(
            value=5.5,
            description="Radius (Å):",
            layout={"width": "200px"},
        )
        self.s02 = ipw.FloatText(
            value=1.0,
            description="S₀²:",
            layout={"width": "200px"},
        )
        self.nleg = ipw.IntText(
            value=6,
            description="NLEG:",
            layout={"width": "200px"},
        )
        self.exclude_hydrogen = ipw.Checkbox(
            value=False,
            description="Exclude hydrogen",
            layout={"width": "200px"},
        )
        self.path_cw_threshold = ipw.FloatText(
            value=-1.0,
            description="Path CW threshold:",
            tooltip="Set ≥ 0 to collect per-path contributions for the paths explorer.",
            layout={"width": "250px"},
        )
        self.precompute_potentials = ipw.Checkbox(
            value=False,
            description="Precompute potentials (one FEFF run per site, "
            "reused across MD frames — skips SCF for each snapshot)",
            indent=False,
            layout={"width": "600px"},
        )

        # Advanced card overrides
        self.scf = ipw.Text(
            value="",
            placeholder="e.g. 4.0 0 30 0.2 1",
            description="SCF:",
            layout={"width": "300px"},
        )
        self.exchange = ipw.Text(
            value="0 0 0",
            description="EXCHANGE:",
            layout={"width": "300px"},
        )
        self.control = ipw.Text(
            value="",
            placeholder="e.g. 1 1 1 1 1 1",
            description="CONTROL:",
            layout={"width": "300px"},
        )
        self.print = ipw.Text(
            value="1 0 0 0 0 3",
            description="PRINT:",
            layout={"width": "300px"},
        )
        self.exafs = ipw.IntText(
            value=0,
            description="EXAFS k_max:",
            layout={"width": "200px"},
        )
        self.criteria = ipw.Text(
            value="",
            placeholder="e.g. 4.0 2.5",
            description="CRITERIA:",
            layout={"width": "300px"},
        )
        self.delete_tags = ipw.Text(
            value="",
            placeholder="Comma-separated card names",
            description="Delete tags:",
            layout={"width": "300px"},
        )

        self.advanced_toggle = ipw.ToggleButton(
            value=False,
            description="Show advanced cards",
            icon="wrench",
        )
        self.advanced_box = ipw.VBox(
            [
                ipw.HBox([self.scf, self.exchange, self.criteria]),
                ipw.HBox([self.control, self.print, self.exafs]),
                ipw.HBox([self.delete_tags]),
            ]
        )
        self.advanced_box.layout.display = "none"

        def _toggle_advanced(change):
            self.advanced_box.layout.display = "block" if change["new"] else "none"

        self.advanced_toggle.observe(_toggle_advanced, names="value")
        self.path_cw_threshold.observe(self._on_path_cw_threshold_change, names="value")
        self.precompute_potentials.observe(self._on_precompute_change, names="value")

        super().__init__(
            [
                self._header,
                ipw.HBox([self.edge, self.radius, self.s02]),
                ipw.HBox([self.nleg, self.exclude_hydrogen, self.path_cw_threshold]),
                self.precompute_potentials,
                self.advanced_toggle,
                self.advanced_box,
            ]
        )

    def _on_path_cw_threshold_change(self, change):
        self.model.path_cw_threshold = change["new"]

    def _on_precompute_change(self, change):
        self.model.precompute_potentials = change["new"]

    def get_parameters(self) -> FeffParameters:
        """Return a validated FeffParameters node from the form values."""
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

        return FeffParameters(dict=params)

    def get_path_cw_threshold(self) -> float:
        """Return the path CW threshold used by the process builder."""
        return self.path_cw_threshold.value

    def validate(self) -> list[str]:
        """Return a list of validation error messages."""
        errors = []
        if self.radius.value <= 0:
            errors.append("Radius must be greater than 0.")
        if self.s02.value < 0:
            errors.append("S₀² must be greater than or equal to 0.")
        if self.nleg.value <= 0:
            errors.append("NLEG must be greater than 0.")
        return errors

    def reset(self):
        """Reset the form to defaults."""
        self.edge.value = "K"
        self.radius.value = 5.5
        self.s02.value = 1.0
        self.nleg.value = 6
        self.exclude_hydrogen.value = False
        self.path_cw_threshold.value = -1.0
        self.precompute_potentials.value = False
        self.scf.value = ""
        self.exchange.value = "0 0 0"
        self.control.value = ""
        self.print.value = "1 0 0 0 0 3"
        self.exafs.value = 0
        self.criteria.value = ""
        self.delete_tags.value = ""
        self.advanced_toggle.value = False
