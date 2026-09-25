"""Resources and review step for the AiiDAlab FEFF app (Review & run)."""

from __future__ import annotations

import contextlib
import datetime

import ipywidgets as ipw
from aiida import orm
from aiida.orm import Code, Computer, QueryBuilder
from alc_aiidalab_widgets.widgets.code_setup import CodeSetupWidget
from alc_aiidalab_widgets.widgets.status import Status

from aiidalab_feff.models import InputModel, WorkflowModel


class ResourcesWidget(ipw.VBox):
    """Review configuration and select compute environment for execution."""

    def __init__(self, model: WorkflowModel, input_model: InputModel | None = None):
        self.model = model
        self.input_model = input_model

        self.header = ipw.HTML("<h2>Review & run</h2>")

        # Prefilled run label field
        self.label_input = ipw.Text(
            value="",
            placeholder="e.g. Cu_K_2026-09-24",
            description="Run label:",
            tooltip="Descriptive label for this calculation in the Runs table (default: Material_Edge_Date).",
            style={"description_width": "initial"},
            layout={"width": "320px"},
        )
        self.label_input.observe(self._on_label_change, names="value")

        # Read-only review card
        self.review_card = ipw.HTML()
        self.review_card.add_class("feff-card")

        # Where to run selector (lead with Where to run)
        self.run_local = ipw.RadioButtons(
            options=[("This machine", True), ("Remote cluster (SCARF)", False)],
            value=True,
            description="Where to run:",
            style={"description_width": "initial"},
        )
        self.run_local.observe(self._on_run_local_change, names="value")

        self.computer_selector = ipw.Dropdown(
            options=[],
            description="Cluster:",
            style={"description_width": "initial"},
            layout={"width": "280px"},
        )
        self.computer_selector.observe(self._on_computer_change, names="value")

        self.code_selector = ipw.Dropdown(
            options=[],
            description="FEFF code:",
            style={"description_width": "initial"},
            layout={"width": "340px"},
        )
        self.code_selector.observe(self._on_code_change, names="value")

        self.refresh_button = ipw.Button(
            description="Refresh",
            icon="refresh",
            tooltip="Refresh available computers and codes",
            layout={"width": "auto", "min_width": "90px"},
        )
        self.refresh_button.add_class("feff-btn-secondary")
        self.refresh_button.on_click(self._refresh)

        self.walltime = ipw.IntText(
            value=3600,
            description="Walltime (s):",
            style={"description_width": "initial"},
            layout={"width": "180px"},
        )
        self.num_nodes = ipw.IntText(
            value=1,
            description="Nodes:",
            style={"description_width": "initial"},
            layout={"width": "140px"},
        )
        self.walltime.observe(self._on_walltime_change, names="value")
        self.num_nodes.observe(self._on_num_nodes_change, names="value")

        self.model.walltime_seconds = self.walltime.value
        self.model.num_nodes = self.num_nodes.value

        self.remote_box = ipw.VBox(
            [
                ipw.HBox(
                    [self.computer_selector, self.code_selector, self.refresh_button],
                    layout=ipw.Layout(align_items="center", grid_gap="8px", flex_flow="row wrap"),
                ),
                ipw.HBox([self.walltime, self.num_nodes], layout=ipw.Layout(grid_gap="8px")),
            ]
        )
        self.remote_box.layout.display = "none"

        # Secondary configure button (only shown when remote selected)
        self.configure_button = ipw.Button(
            description="Configure compute environment...",
            icon="cog",
            tooltip="Set up an AiiDA computer and code",
            layout={"width": "auto", "min_width": "220px", "display": "none"},
        )
        self.configure_button.add_class("feff-btn-secondary")
        self.configure_button.on_click(self._configure_code)

        # Advanced options (Batch size, workers, streaming, python code)
        self.batch_toggle = ipw.Checkbox(
            value=False,
            description="Group frames into batch jobs",
            tooltip="Group multiple (frame, site) pairs into a single Slurm job.",
            indent=False,
        )
        self.batch_toggle.observe(self._on_batch_toggle, names="value")

        self.batch_size = ipw.IntText(
            value=50,
            description="Batch size:",
            style={"description_width": "initial"},
            layout={"width": "180px"},
        )
        self.n_workers = ipw.IntText(
            value=8,
            description="Workers per batch:",
            style={"description_width": "initial"},
            layout={"width": "200px"},
        )
        self.python_code_selector = ipw.Dropdown(
            options=[],
            description="Python interpreter:",
            style={"description_width": "initial"},
            layout={"width": "340px"},
        )
        self.python_code_selector.observe(self._on_python_code_change, names="value")

        self.clean_scratch = ipw.Checkbox(
            value=True,
            description="Clean scratch on the fly",
            tooltip="Delete frame scratch on the fly to bound disk and inode usage.",
            indent=False,
        )
        self.clean_scratch.observe(self._on_clean_scratch_change, names="value")

        self.stream_chunk_size = ipw.IntText(
            value=256,
            description="Stream chunk size:",
            tooltip="Number of frames to process before unlinking scratch.",
            style={"description_width": "initial"},
            layout={"width": "200px"},
        )
        self.stream_chunk_size.observe(self._on_stream_chunk_size_change, names="value")

        self.batch_box = ipw.VBox(
            [
                ipw.HBox([self.batch_size, self.n_workers], layout=ipw.Layout(grid_gap="8px")),
                ipw.HBox(
                    [self.clean_scratch, self.stream_chunk_size], layout=ipw.Layout(grid_gap="8px")
                ),
                self.python_code_selector,
            ]
        )
        self.batch_box.layout.display = "none"

        advanced_content = ipw.VBox(
            [
                self.batch_toggle,
                self.batch_box,
            ],
            layout=ipw.Layout(padding="8px 0"),
        )
        self.advanced_accordion = ipw.Accordion(children=[advanced_content])
        self.advanced_accordion.set_title(
            0, "Advanced compute options (batching, streaming, scratch)"
        )
        self.advanced_accordion.selected_index = None

        self.code_setup = CodeSetupWidget()
        self.code_setup_panel = ipw.Accordion(children=[self.code_setup])
        self.code_setup_panel.set_title(0, "Compute environment setup")
        self.code_setup_panel.selected_index = None
        self.code_setup_panel.observe(self._on_code_setup_panel_change, names="selected_index")

        # Backward compatibility alias
        self.scheduler_box = self.remote_box

        self.status = Status()

        super().__init__(
            [
                self.header,
                self.label_input,
                self.review_card,
                ipw.HTML("<h3 style='margin-top:14px;'>Compute environment</h3>"),
                self.run_local,
                self.remote_box,
                self.configure_button,
                self.advanced_accordion,
                self.code_setup_panel,
                self.status,
            ]
        )

        try:
            self.model.computer = orm.load_computer("localhost")
            self.computer_selector.value = "localhost"
        except Exception:
            pass

        self._refresh()
        self.update_review_card()

    def _on_label_change(self, change):
        self.model.label = change["new"].strip()

    def update_review_card(self):
        """Update the read-only summary card with current parameters and run estimates."""
        material = "Unknown structure"
        n_frames = 1
        is_md = False
        n_absorbers = 1
        absorber_element = ""

        if self.input_model is not None:
            if self.input_model.trajectory is not None:
                is_md = True
                selected_indices = self.input_model.selected_indices or []
                n_frames = len(selected_indices)
                try:
                    material = (
                        self.input_model.trajectory.get_step_structure(0).get_formula()
                        if hasattr(self.input_model.trajectory, "get_step_structure")
                        else "MD trajectory"
                    )
                except Exception:
                    material = "MD trajectory"
            elif self.input_model.structure is not None:
                material = self.input_model.structure.get_formula()
                n_frames = 1
            elif self.input_model.structures:
                n_frames = len(self.input_model.structures)
                first_st = next(iter(self.input_model.structures.values()))
                material = (
                    first_st.get_formula() if hasattr(first_st, "get_formula") else "Ensemble"
                )

            n_absorbers = len(self.input_model.absorbing_atoms or [0])
            symbols = None
            if self.input_model.trajectory is not None:
                symbols = getattr(self.input_model.trajectory, "symbols", None)
            elif self.input_model.structure is not None:
                from aiidalab_feff.utils import get_symbols

                symbols = get_symbols(self.input_model.structure)
            if symbols and self.input_model.absorbing_atoms:
                idx = self.input_model.absorbing_atoms[0]
                if 0 <= idx < len(symbols):
                    absorber_element = symbols[idx]

        params = self.model.parameters or {}
        edge = params.get("edge", "K")
        radius = params.get("radius", 5.5)
        nleg = params.get("nleg", 6)
        s02 = params.get("s02", 1.0)
        precompute = (
            "Yes (reused across frames)"
            if self.model.precompute_potentials
            else "No (computed per frame)"
        )

        target = (
            "This machine (Local)"
            if self.run_local.value
            else (f"Remote cluster ({self.computer_selector.value or 'not selected'})")
        )
        total_runs = n_frames * n_absorbers
        frame_noun = "frames" if is_md else "structures"
        absorber_noun = "absorber" if n_absorbers == 1 else "absorbers"

        # Default label prefilling
        today_str = datetime.date.today().isoformat()
        clean_mat = material.replace(" ", "")
        default_label = f"{clean_mat}_{edge}_{today_str}"
        if not self.label_input.value:
            self.label_input.value = default_label
            self.model.label = default_label

        self.review_card.value = (
            "<div style='background:var(--feff-surface, #F4F6F8);border:1px solid var(--feff-rule, #D5DBE1);"
            "border-radius:6px;padding:12px 16px;margin:8px 0;'>"
            "<div style='font-size:14px;font-weight:600;margin-bottom:8px;color:var(--feff-ink, #1F2933);'>"
            "📋 Calculation summary"
            "</div>"
            "<div style='display:grid;grid-template-columns:repeat(auto-fit, minmax(200px, 1fr));gap:10px;font-size:13px;'>"
            f"<div><span style='color:var(--feff-ink-muted, #666);'>Material:</span> <strong>{material}</strong></div>"
            f"<div><span style='color:var(--feff-ink-muted, #666);'>Input frames:</span> <strong>{n_frames} {frame_noun}</strong></div>"
            f"<div><span style='color:var(--feff-ink-muted, #666);'>Absorber:</span> <strong>{n_absorbers} {absorber_element} {absorber_noun} ({edge}-edge)</strong></div>"
            f"<div><span style='color:var(--feff-ink-muted, #666);'>Parameters:</span> R={radius} Å · NLEG={nleg} · S₀²={s02}</div>"
            f"<div><span style='color:var(--feff-ink-muted, #666);'>Precompute potentials:</span> {precompute}</div>"
            f"<div><span style='color:var(--feff-ink-muted, #666);'>Execution target:</span> <strong>{target}</strong></div>"
            "</div>"
            "<div style='margin-top:10px;padding-top:8px;border-top:1px solid var(--feff-rule-light, #E4E7EB);"
            "font-size:13.5px;font-weight:600;color:var(--feff-accent, #1B5E9B);'>"
            f"Total calculations: {n_frames} {frame_noun} × {n_absorbers} {absorber_noun} = {total_runs} FEFF runs"
            "</div>"
            "</div>"
        )

    def _on_run_local_change(self, change):
        is_local = change["new"]
        self.remote_box.layout.display = "none" if is_local else "block"
        self.configure_button.layout.display = "none" if is_local else "inline-block"
        if is_local:
            try:
                self.model.computer = orm.load_computer("localhost")
                self.computer_selector.value = "localhost"
            except Exception:
                self.model.computer = None
                self.computer_selector.value = None
        self._refresh()
        self.update_review_card()

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
        self._refresh_python_codes()
        self.update_review_card()

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

    def _on_clean_scratch_change(self, change):
        self.model.clean_scratch = change["new"]

    def _on_stream_chunk_size_change(self, change):
        self.model.stream_chunk_size = change["new"]

    def _on_batch_toggle(self, change):
        self.batch_box.layout.display = "block" if change["new"] else "none"
        if not change["new"]:
            self.model.batch_size = None
            self.model.n_workers = None
        else:
            self.model.batch_size = self.batch_size.value
            self.model.n_workers = self.n_workers.value
            self.model.clean_scratch = self.clean_scratch.value
            self.model.stream_chunk_size = self.stream_chunk_size.value

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
            assert isinstance(computer, Computer)
            query.append(Computer, filters={"uuid": computer.uuid}, tag="computer")
            query.append(Code, with_computer="computer")
        else:
            query.append(Code)
        all_codes = query.all(flat=True)
        feff_options = []
        other_options = []
        for code in all_codes:
            if isinstance(code, Code) and code.label:
                lbl = code.label.lower()
                plugin = getattr(code, "default_calc_job_plugin", None) or ""
                if "feff" in lbl or plugin.startswith("feff"):
                    feff_options.append((code.label, code.uuid))
                elif "python" not in lbl:
                    other_options.append((code.label, code.uuid))
        options = feff_options or other_options
        self.code_selector.options = [("", None)] + options
        if options and (
            self.code_selector.value is None
            or self.code_selector.value not in [opt[1] for opt in options]
        ):
            self.code_selector.value = options[0][1]
            self.model.code = orm.load_code(options[0][1])

    def _refresh_python_codes(self):
        query = QueryBuilder()
        computer = self.model.computer
        if computer is not None:
            assert isinstance(computer, Computer)
            query.append(Computer, filters={"uuid": computer.uuid}, tag="computer")
            query.append(Code, with_computer="computer")
        else:
            query.append(Code)
        all_codes = query.all(flat=True)
        python_options = []
        other_options = []
        for code in all_codes:
            if isinstance(code, Code) and code.label:
                lbl = code.label.lower()
                plugin = getattr(code, "default_calc_job_plugin", None) or ""
                exe = ""
                with contextlib.suppress(Exception):
                    exe = (code.get_executable() or "").lower()
                if "python" in lbl or "python" in exe or plugin == "feff.feff_batch":
                    python_options.append((code.label, code.uuid))
                elif "feff" not in lbl:
                    other_options.append((code.label, code.uuid))
        options = python_options or other_options
        self.python_code_selector.options = [("", None)] + options
        if options and (
            self.python_code_selector.value is None
            or self.python_code_selector.value not in [opt[1] for opt in options]
        ):
            self.python_code_selector.value = options[0][1]
            self.model.python_code = orm.load_code(options[0][1])

    def _configure_code(self, _):
        """Open the shared GUI for configuring an AiiDA computer and code."""
        self.code_setup_panel.selected_index = 0
        self.status.value = (
            "Choose a resource and complete its setup below. "
            "Close this panel when configuration finishes to refresh the selectors."
        )

    def _on_code_setup_panel_change(self, change):
        """Refresh selectable resources after the setup panel is closed."""
        if change["old"] == 0 and change["new"] is None:
            self._refresh()
            self.status.value = "Resources refreshed. Select the configured computer and code."
            self.update_review_card()

    def validate(self) -> list[str]:
        """Return a list of validation error messages."""
        errors = []
        if not self.run_local.value and self.model.computer is None:
            errors.append("Select a computer for remote execution.")
        if self.model.code is None:
            errors.append("Select a FEFF code.")
        if self.model.path_cw_threshold >= 0 and self.model.python_code is None:
            errors.append("Path storage (threshold >= 0) requires a Python interpreter code.")
        if self.batch_toggle.value:
            if self.model.python_code is None:
                errors.append(
                    "Batch mode requires a Python interpreter code (to run batch jobs on the compute machine)."
                )
            if self.batch_size.value <= 1:
                errors.append("Batch size must be greater than 1.")
            if self.n_workers.value <= 0:
                errors.append("Workers per batch must be greater than 0.")
            if self.clean_scratch.value and self.stream_chunk_size.value <= 0:
                errors.append("Stream chunk size must be greater than 0.")
        return errors

    def reset(self):
        self.run_local.value = True
        self.label_input.value = ""
        self.computer_selector.value = None
        self.code_selector.value = None
        self.walltime.value = 3600
        self.num_nodes.value = 1
        self.model.walltime_seconds = 3600
        self.model.num_nodes = 1
        self.batch_toggle.value = False
        self.batch_size.value = 50
        self.n_workers.value = 8
        self.clean_scratch.value = True
        self.stream_chunk_size.value = 256
        self.python_code_selector.value = None
        self.status.value = ""
        self.model.reset()
        self.update_review_card()
