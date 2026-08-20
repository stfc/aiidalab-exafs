"""Submission and monitoring step for the AiiDAlab FEFF app."""

from __future__ import annotations

import ipywidgets as ipw
from aiida import engine, orm
from aiida.engine import ProcessState
from aiida_feff.workflows.ensemble import EnsembleExafsWorkChain
from alc_aiidalab_widgets.widgets.status import Status

from aiidalab_feff.models import InputModel, ResultsModel, SubmissionModel, WorkflowModel


def build_workchain_builder(
    input_model: InputModel,
    workflow_model: WorkflowModel,
) -> engine.ProcessBuilder:
    """Build an EnsembleExafsWorkChain builder from the app models.

    Raises:
    ------
    ValueError
        If required input is missing or inconsistent.
    """
    structures = input_model.get_structures()
    if input_model.trajectory is None and not structures:
        msg = "No structures provided."
        raise ValueError(msg)
    if input_model.trajectory is not None and not input_model.selected_indices:
        msg = "No trajectory frames selected."
        raise ValueError(msg)

    parameters = workflow_model.parameters
    if parameters is None:
        msg = "No FEFF parameters provided."
        raise ValueError(msg)

    # Inject absorbing atom(s) from the input step into the FEFF parameters.
    param_dict = dict(parameters)
    if input_model.absorbing_atoms:
        param_dict["absorbing_atoms"] = input_model.absorbing_atoms

    from aiida_feff.data.parameters import FeffParameters

    parameters = FeffParameters(dict=param_dict)

    code = workflow_model.code
    if code is None:
        msg = "No FEFF code selected."
        raise ValueError(msg)

    builder = EnsembleExafsWorkChain.get_builder()
    if input_model.trajectory is not None:
        builder.trajectory = input_model.trajectory
        builder.step_ids = orm.List(list=input_model.selected_indices)
    else:
        assert structures is not None
        for label, structure in structures.items():
            builder.structures[label] = structure  # type: ignore[index]
    builder.parameters = parameters
    builder.code = code

    options: dict = {}
    if not workflow_model.is_local() and workflow_model.computer is not None:
        if workflow_model.walltime_seconds is not None:
            options["max_wallclock_seconds"] = workflow_model.walltime_seconds
        if workflow_model.num_nodes is not None:
            options["resources"] = {"num_machines": workflow_model.num_nodes}
            if workflow_model.is_batch() and workflow_model.n_workers is not None:
                options["resources"]["num_mpiprocs_per_machine"] = workflow_model.n_workers
    if options:
        builder.options = orm.Dict(dict=options)

    builder.path_cw_threshold = orm.Float(workflow_model.path_cw_threshold)

    builder.precompute_potentials = orm.Bool(workflow_model.precompute_potentials)

    if workflow_model.python_code is not None and (
        workflow_model.path_cw_threshold >= 0 or workflow_model.is_batch()
    ):
        builder.python_code = workflow_model.python_code

    if workflow_model.is_batch():
        builder.batch_size = orm.Int(workflow_model.batch_size)
        builder.n_workers = orm.Int(workflow_model.n_workers)

    return builder


class ProcessWidget(ipw.VBox):
    """Widget for submitting and monitoring the WorkChain."""

    def __init__(
        self,
        input_model: InputModel,
        workflow_model: WorkflowModel,
        submission_model: SubmissionModel,
        results_model: ResultsModel,
        on_process_loaded=None,
        on_results_loaded=None,
    ):
        self.input_model = input_model
        self.workflow_model = workflow_model
        self.submission_model = submission_model
        self.results_model = results_model
        self.on_process_loaded = on_process_loaded
        self.on_results_loaded = on_results_loaded

        self.header = ipw.HTML("<h2>Submit and monitor</h2>")
        self.submit_button = ipw.Button(
            description="Submit",
            button_style="success",
            icon="paper-plane",
        )
        self.submit_button.on_click(self._on_submit)

        self.explorer_button = ipw.Button(
            description="Open in aiida-explorer",
            button_style="info",
            icon="external-link",
            layout={"display": "none"},
        )
        self.explorer_button.on_click(self._on_open_explorer)

        self.status = Status()
        self.monitor_output = ipw.Output()

        super().__init__(
            [
                self.header,
                ipw.HBox([self.submit_button, self.explorer_button]),
                self.status,
                self.monitor_output,
            ]
        )

        self.submission_model.observe(self._on_process_node_change, names="process_node")

    def _on_submit(self, _):
        self.monitor_output.clear_output()
        try:
            builder = build_workchain_builder(self.input_model, self.workflow_model)
        except ValueError as exc:
            self.status.failure(str(exc))
            return

        self.status.value = "Submitting..."
        try:
            process_node = engine.submit(builder)
        except Exception as exc:  # noqa: BLE001
            self.status.failure(f"Submission failed: {exc}")
            return

        self.submission_model.process_node = process_node
        self.status.success(f"Submitted {process_node.pk}.")
        self.explorer_button.layout.display = "block"
        self._monitor_process()

    AIIDA_EXPLORER_REST_API_URL = "http://localhost:5050/api/v4"
    AIIDA_EXPLORER_APP_URL = "https://aiidateam.github.io/aiida-explorer/"

    def _open_aiida_explorer(self, uuid: str):
        """Open the node in the hosted aiida-explorer app in a new tab."""
        from urllib.parse import quote

        from IPython.display import Javascript, display

        api_url = quote(self.AIIDA_EXPLORER_REST_API_URL, safe="")
        query = f"api_url={api_url}&uuid={uuid}"
        url = f"{self.AIIDA_EXPLORER_APP_URL}?{query}"
        js = f"window.open('{url}', '_blank');"
        display(Javascript(js))

    def _on_open_explorer(self, _):
        process_node = self.submission_model.process_node
        if process_node is None:
            return
        assert isinstance(process_node, orm.ProcessNode)
        uuid = process_node.uuid
        if uuid:
            self._open_aiida_explorer(uuid)

    def _on_process_node_change(self, change):
        if change["new"] is not None:
            self.explorer_button.layout.display = "block"
            if self.on_process_loaded is not None:
                self.on_process_loaded()
            self._monitor_process()
        else:
            self.explorer_button.layout.display = "none"

    def _monitor_process(self):
        process_node = self.submission_model.process_node
        assert isinstance(process_node, orm.ProcessNode)
        if process_node is None:
            return

        # Re-load the node from the database so we observe the daemon's state
        # transitions. A ProcessNode obtained from engine.submit() in this
        # kernel caches its SQLAlchemy attributes dict in memory; the daemon
        # (a separate process) updates process_state in the DB, but this
        # kernel's cached dict is never refreshed, so is_terminated would
        # otherwise stay False forever and results would never load.
        process_node = orm.load_node(process_node.pk)
        self.submission_model.process_node = process_node

        with self.monitor_output:
            self.monitor_output.clear_output()
            print(f"Process {process_node.pk}: {process_node.process_state}")  # type: ignore[attr-defined]

        if process_node.is_terminated:  # type: ignore[attr-defined]
            self._on_finished(process_node)
            return

        # Simple polling: refresh every 2 seconds up to 5 minutes.
        # In a real app, use a background thread or AiiDAlab process monitor.
        import threading

        def _poll():
            import time

            for _ in range(150):
                time.sleep(2)
                current = self.submission_model.process_node
                if current is None:
                    return
                # Reload fresh from the DB each iteration (see note above).
                fresh = orm.load_node(current.pk)
                self.submission_model.process_node = fresh
                if fresh.is_terminated:  # type: ignore[attr-defined]
                    break
                with self.monitor_output:
                    self.monitor_output.clear_output()
                    print(f"Process {fresh.pk}: {fresh.process_state}")  # type: ignore[attr-defined]
            self._on_finished(self.submission_model.process_node)

        thread = threading.Thread(target=_poll, daemon=True)
        thread.start()

    def _on_finished(self, process_node):
        if process_node is None:
            return
        # Ensure we read the terminal state from the DB, not a stale cache.
        if not process_node.is_terminated and process_node.pk is not None:
            process_node = orm.load_node(process_node.pk)
        if not process_node.is_terminated:
            return

        state = process_node.process_state
        if state == ProcessState.FINISHED:
            self.status.success(f"Process {process_node.pk} finished.")
            try:
                self._populate_results(process_node)
            except Exception as exc:  # noqa: BLE001
                self.status.failure(f"Failed to load results: {exc}")
                return
            if self.on_results_loaded is not None:
                self.on_results_loaded()
        elif state == ProcessState.EXCEPTED:
            self.status.failure(f"Process {process_node.pk} excepted.")
        elif state == ProcessState.KILLED:
            self.status.failure(f"Process {process_node.pk} killed.")

    def _populate_results(self, process_node):
        outputs = process_node.outputs
        averaged_xas = {}
        for key in dir(outputs.averaged_xas):
            if key.startswith("site_") or key == "all":
                averaged_xas[key] = getattr(outputs.averaged_xas, key)

        # Build the per-(frame, site) XasData grid for subsampling/convergence
        # by walking each FeffCalculation / FeffBatchCalculation child for its
        # xas_data output. Only successful (finished_ok) children contribute.
        # Missing pairs are simply absent.
        xas_grid: dict[tuple[int, int], object] = {}
        for child in process_node.called:
            if not getattr(child, "is_finished_ok", False):
                continue
            proc_label = getattr(child, "process_label", None)
            if proc_label == "FeffCalculation" and "xas_data" in child.outputs:
                try:
                    xas_grid[(child.inputs.frame_idx.value, child.inputs.site_idx.value)] = (
                        child.outputs.xas_data
                    )
                except (KeyError, AttributeError):  # noqa: PERF203
                    continue
            elif proc_label == "FeffBatchCalculation" and hasattr(child.outputs, "xas_data"):
                try:
                    for snap_key in dir(child.outputs.xas_data):
                        if snap_key.startswith("snap_"):
                            parts = snap_key.split("_")
                            if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
                                frame_idx = int(parts[1])
                                site_idx = int(parts[2])
                                xas_grid[(frame_idx, site_idx)] = getattr(
                                    child.outputs.xas_data, snap_key
                                )
                except Exception:  # noqa: BLE001
                    continue

        # Extract absorber element + edge for plot titles/legends.
        edge = ""
        absorber_label = ""
        try:
            params = process_node.inputs.parameters.get_dict()
            edge = str(params.get("edge", "")).upper()
            atoms = params.get("absorbing_atoms", None) or []
            # Resolve element symbol(s) from the first input structure.
            if "trajectory" in process_node.inputs:
                trajectory = process_node.inputs.trajectory
                step_id = process_node.inputs.step_ids.get_list()[0]
                frame_index = trajectory.get_index_from_stepid(step_id)
                first_struct = trajectory.get_step_structure(frame_index)
            else:
                structures = process_node.inputs.structures
                first_struct = next(iter(structures.values()))
            from aiidalab_feff.utils import get_symbols

            symbols = get_symbols(first_struct)
            elements = sorted({symbols[i] for i in atoms if 0 <= i < len(symbols)})
            if len(elements) == 1:
                el = elements[0]
                if len(atoms) > 1:
                    absorber_label = f"{el} @ sites {','.join(str(a) for a in atoms)}"
                else:
                    absorber_label = el
            elif elements:
                absorber_label = "/".join(elements)
        except Exception:  # noqa: BLE001
            pass

        # Set the grid + metadata BEFORE averaged_xas: the ResultsWidget observes
        # ``averaged_xas`` and its callback (_render → _populate_conv_selectors)
        # reads xas_grid and edge/absorber_label, so they must be ready first.
        self.results_model.xas_grid = xas_grid or None
        self.results_model.edge = edge
        self.results_model.absorber_label = absorber_label
        self.results_model.is_ensemble = (
            len(self.input_model.selected_indices or []) > 1
            if self.input_model.trajectory is not None
            else len(self.input_model.get_structures() or {}) > 1
        )
        self.results_model.process_node = process_node
        self.results_model.n_failed = outputs.n_failed.value
        if hasattr(outputs, "path_contributions"):
            self.results_model.path_contributions = outputs.path_contributions
        self.results_model.averaged_xas = averaged_xas

    def reset(self):
        self.status.clear()
        self.monitor_output.clear_output()
        self.submission_model.reset()


def get_workchain_status(process_node) -> str:
    """Return a short status string for a process node."""
    if process_node is None:
        return "No process."
    return f"PK {process_node.pk}: {process_node.process_state}"
