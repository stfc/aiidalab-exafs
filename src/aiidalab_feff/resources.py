"""Resources selection step for the AiiDAlab FEFF app."""

from __future__ import annotations

import ipywidgets as ipw
from aiida import orm
from aiida.orm import Code, Computer, QueryBuilder
from alc_aiidalab_widgets.widgets.status import Status

from aiidalab_feff.models import WorkflowModel


class ResourcesWidget(ipw.VBox):
    """Widget for selecting computer, code, scheduler and batch options."""

    def __init__(self, model: WorkflowModel):
        self.model = model

        self.run_local = ipw.RadioButtons(
            options=[("Local", True), ("Remote", False)],
            value=True,
            description="Run on:",
        )
        self.run_local.observe(self._on_run_local_change, names="value")

        self.computer_selector = ipw.Dropdown(
            options=[],
            description="Computer:",
            layout={"width": "300px"},
        )
        self.computer_selector.observe(self._on_computer_change, names="value")

        self.code_selector = ipw.Dropdown(
            options=[],
            description="FEFF code:",
            layout={"width": "400px"},
        )
        self.code_selector.observe(self._on_code_change, names="value")

        self.refresh_button = ipw.Button(
            description="Refresh codes/computers",
            icon="refresh",
        )
        self.refresh_button.on_click(self._refresh)

        self.walltime = ipw.IntText(
            value=3600,
            description="Walltime (s):",
            layout={"width": "200px"},
        )
        self.num_nodes = ipw.IntText(
            value=1,
            description="Nodes:",
            layout={"width": "150px"},
        )
        self.walltime.observe(self._on_walltime_change, names="value")
        self.num_nodes.observe(self._on_num_nodes_change, names="value")

        # Initialize model values
        self.model.walltime_seconds = self.walltime.value
        self.model.num_nodes = self.num_nodes.value

        self.scheduler_box = ipw.HBox([self.walltime, self.num_nodes])
        self.scheduler_box.layout.display = "none"

        self.batch_toggle = ipw.Checkbox(
            value=False,
            description="Use batch mode",
            tooltip="Group multiple (frame, site) pairs into a single Slurm job.",
        )
        self.batch_toggle.observe(self._on_batch_toggle, names="value")

        self.batch_size = ipw.IntText(
            value=50,
            description="Batch size:",
            layout={"width": "180px"},
        )
        self.n_workers = ipw.IntText(
            value=8,
            description="Workers per batch:",
            layout={"width": "200px"},
        )
        self.python_code_selector = ipw.Dropdown(
            options=[],
            description="Python code:",
            layout={"width": "400px"},
        )
        self.python_code_selector.observe(self._on_python_code_change, names="value")

        self.batch_box = ipw.VBox(
            [
                ipw.HBox([self.batch_size, self.n_workers]),
                self.python_code_selector,
            ]
        )
        self.batch_box.layout.display = "none"

        self.scarf_button = ipw.Button(
            description="Import SCARF preset",
            button_style="info",
            icon="cloud-download",
            layout={"display": "none"},
        )
        self.scarf_button.on_click(self._import_scarf_preset)

        self.configure_button = ipw.Button(
            description="Configure code",
            button_style="warning",
            icon="cog",
        )
        self.configure_button.on_click(self._configure_code)

        self.status = Status()

        super().__init__(
            [
                ipw.HTML("<h2>Resources</h2>"),
                self.run_local,
                ipw.HBox([self.computer_selector, self.code_selector, self.refresh_button]),
                self.scheduler_box,
                self.batch_toggle,
                self.batch_box,
                ipw.HBox([self.configure_button, self.scarf_button]),
                self.status,
            ]
        )

        self._refresh()

    def _on_run_local_change(self, change):
        is_local = change["new"]
        self.scheduler_box.layout.display = "none" if is_local else "block"
        self.batch_toggle.layout.display = "none" if is_local else "block"
        if is_local:
            self.batch_toggle.value = False
            self.model.computer = None
        self._refresh()

    def _on_walltime_change(self, change):
        self.model.walltime_seconds = change["new"]

    def _on_num_nodes_change(self, change):
        self.model.num_nodes = change["new"]

    def _on_computer_change(self, change):
        if change["new"] is None:
            self.model.computer = None
        else:
            self.model.computer = orm.load_computer(change["new"])
        self._refresh_codes()
        self._update_scarf_button()

    def _on_code_change(self, change):
        if change["new"] is None:
            self.model.code = None
        else:
            self.model.code = orm.load_code(change["new"])

    def _on_python_code_change(self, change):
        if change["new"] is None:
            self.model.python_code = None
        else:
            self.model.python_code = orm.load_code(change["new"])

    def _on_batch_toggle(self, change):
        self.batch_box.layout.display = "block" if change["new"] else "none"
        if not change["new"]:
            self.model.batch_size = None
            self.model.n_workers = None
            self.model.python_code = None
        else:
            self.model.batch_size = self.batch_size.value
            self.model.n_workers = self.n_workers.value

    def _refresh(self, _=None):
        self._refresh_computers()
        self._refresh_codes()
        self._refresh_python_codes()

    def _refresh_computers(self):
        query = QueryBuilder()
        query.append(Computer, project=["label"])
        options = [(label, label) for (label,) in query.all()]
        self.computer_selector.options = [("", None)] + options

    def _refresh_codes(self):
        computer = self.model.computer
        query = QueryBuilder()
        if computer is not None:
            query.append(Computer, filters={"uuid": computer.uuid}, tag="computer")
            query.append(Code, with_computer="computer")
        else:
            query.append(Code)
        options = []
        for code in query.all(flat=True):
            if isinstance(code, Code) and code.label:
                options.append((code.label, code.uuid))
        self.code_selector.options = [("", None)] + options
        self.python_code_selector.options = [("", None)] + options

    def _refresh_python_codes(self):
        query = QueryBuilder()
        query.append(Code)
        options = []
        for code in query.all(flat=True):
            if code.label:
                options.append((code.label, code.uuid))
        self.python_code_selector.options = [("", None)] + options

    def _update_scarf_button(self):
        if self.model.computer is not None and self.model.computer.label.lower() == "scarf":  # type: ignore[attr-defined]
            self.scarf_button.layout.display = "block"
        else:
            self.scarf_button.layout.display = "none"

    def _import_scarf_preset(self, _):
        # Placeholder for SCARF preset import logic.
        self.status.value = "SCARF preset import not yet implemented in this app."

    def _configure_code(self, _):
        if self.model.computer is not None and self.model.computer.label.lower() == "scarf":  # type: ignore[attr-defined]
            self._import_scarf_preset(None)
        else:
            self.status.value = (
                "Configure a FEFF code via `verdi code create` or the AiiDA code setup UI."
            )

    def validate(self) -> list[str]:
        """Return a list of validation error messages."""
        errors = []
        if not self.run_local.value and self.model.computer is None:
            errors.append("Select a computer for remote execution.")
        if self.model.code is None:
            errors.append("Select a FEFF code.")
        if self.model.path_cw_threshold >= 0 and self.model.python_code is None:
            errors.append(
                "Path CW threshold >= 0 requires a Python interpreter code (for path aggregation)."
            )
        if self.batch_toggle.value:
            if self.model.python_code is None:
                errors.append("Batch mode requires a Python interpreter code.")
            if self.batch_size.value <= 0:
                errors.append("Batch size must be greater than 0.")
            if self.n_workers.value <= 0:
                errors.append("Workers per batch must be greater than 0.")
        return errors

    def reset(self):
        self.run_local.value = True
        self.computer_selector.value = None
        self.code_selector.value = None
        self.walltime.value = 3600
        self.num_nodes.value = 1
        self.model.walltime_seconds = 3600
        self.model.num_nodes = 1
        self.batch_toggle.value = False
        self.batch_size.value = 50
        self.n_workers.value = 8
        self.python_code_selector.value = None
        self.status.value = ""
        self.model.reset()
