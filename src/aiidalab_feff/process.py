"""Submission and monitoring step for the AiiDAlab FEFF app."""

from __future__ import annotations

import datetime
import logging
from urllib.parse import quote

import ipywidgets as ipw
from aiida import engine, orm
from aiida.engine import ProcessState
from aiida_feff.workflows.ensemble import EnsembleExafsWorkChain
from alc_aiidalab_widgets.widgets.loading import LoadingWidget
from alc_aiidalab_widgets.widgets.process_node_view import ProcessNodeViewerWidget
from alc_aiidalab_widgets.widgets.status import Status
from IPython.display import Javascript, display

from aiidalab_feff.models import InputModel, ResultsModel, SubmissionModel, WorkflowModel
from aiidalab_feff.running_tasks import (
    _aggregate_jobs,
    _collect_jobs,
    _estimate_expected_calculations,
    _progress_bar_html,
)

logger = logging.getLogger(__name__)

#: How long the background monitor keeps polling a submitted process before giving up.
_MONITOR_TIMEOUT_SECONDS = 300.0

#: How long the monitor thread waits for the kernel's event loop to run one poll.
#: The loop is blocked while a cell executes, so a missed poll is normal; we skip it
#: rather than parking the thread until the kernel next goes idle.
_MONITOR_CALLBACK_TIMEOUT_SECONDS = 10.0


def _format_duration(seconds: float) -> str:
    """Format duration in seconds into human-readable string."""
    seconds = int(max(0, seconds))
    mins, secs = divmod(seconds, 60)
    hours, mins = divmod(mins, 60)
    if hours > 0:
        return f"{hours}h {mins}m {secs}s"
    if mins > 0:
        return f"{mins}m {secs}s"
    return f"{secs}s"


def _plain_state_info(process_node) -> tuple[str, str]:
    """Return plain English status and badge class for a process node."""
    if process_node is None:
        return "Not started", "feff-badge"
    state = getattr(process_node, "process_state", None)
    val = getattr(state, "value", str(state)).lower() if state else ""
    if val == "finished":
        if getattr(process_node, "is_finished_ok", False):
            return "Finished", "feff-badge feff-badge-done"
        return "Finished with warnings", "feff-badge feff-badge-failed"
    mapping = {
        "created": ("Queued", "feff-badge feff-badge-running"),
        "running": ("Running", "feff-badge feff-badge-running"),
        "waiting": ("Running", "feff-badge feff-badge-running"),
        "excepted": ("Failed", "feff-badge feff-badge-failed"),
        "killed": ("Cancelled", "feff-badge feff-badge-failed"),
    }
    return mapping.get(val, ("Running", "feff-badge feff-badge-running"))


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
        if hasattr(builder, "clean_scratch"):
            builder.clean_scratch = orm.Bool(workflow_model.clean_scratch)
        if hasattr(builder, "stream_chunk_size") and workflow_model.stream_chunk_size is not None:
            builder.stream_chunk_size = orm.Int(workflow_model.stream_chunk_size)

    if getattr(workflow_model, "label", None):
        builder.metadata.label = workflow_model.label

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

        self.header = ipw.HTML("<h2>Calculation progress</h2>")
        self.progress_panel = ipw.HTML()
        self.progress_panel.add_class("feff-card")

        self.submit_button = ipw.Button(
            description="Run calculation",
            button_style="primary",
            icon="play",
            layout={"min_width": "150px"},
        )
        self.submit_button.add_class("feff-btn-primary")
        self.submit_button.on_click(self._on_submit)

        self.explorer_button = ipw.Button(
            description="Open provenance (AiiDA)",
            icon="external-link",
            layout={"display": "none", "min_width": "190px"},
        )
        self.explorer_button.add_class("feff-btn-secondary")
        self.explorer_button.on_click(self._on_open_explorer)

        self.view_results_button = ipw.Button(
            description="View results",
            button_style="primary",
            icon="bar-chart",
            disabled=True,
            layout={"display": "none", "min_width": "140px"},
        )
        self.view_results_button.add_class("feff-btn-primary")
        self.view_results_button.on_click(self._on_view_results_click)

        self.status = Status()
        self.monitor_output = ipw.Output()

        self.details_accordion = ipw.Accordion(children=[self.monitor_output])
        self.details_accordion.set_title(0, "AiiDA process details (troubleshooting)")
        self.details_accordion.selected_index = None

        action_row = ipw.HBox(
            [self.explorer_button, self.view_results_button],
            layout=ipw.Layout(grid_gap="12px", align_items="center", margin="12px 0"),
        )

        super().__init__(
            [
                self.header,
                self.progress_panel,
                action_row,
                self.status,
                self.details_accordion,
            ]
        )

        self.submission_model.observe(self._on_process_node_change, names="process_node")

    def _render_process_view(self, process_node):
        """Render human-readable progress panel and background details."""
        if process_node is None:
            self.progress_panel.value = "<em>No calculation active.</em>"
            return

        label = getattr(process_node, "label", "") or "EXAFS calculation"
        pk = getattr(process_node, "pk", "")
        status_text, badge_class = _plain_state_info(process_node)

        # Child jobs progress
        agg = _aggregate_jobs(_collect_jobs(process_node))
        expected = _estimate_expected_calculations(process_node)
        total = expected if expected else max(agg["done"] + agg["failed"] + agg["pending"], 1)

        # Duration
        ctime = getattr(process_node, "ctime", None)
        mtime = getattr(process_node, "mtime", None)
        is_term = bool(getattr(process_node, "is_terminated", False))
        if ctime is not None:
            end_time = (
                mtime if (is_term and mtime) else datetime.datetime.now(datetime.timezone.utc)
            )
            if ctime.tzinfo is not None and end_time.tzinfo is None:
                end_time = end_time.replace(tzinfo=datetime.timezone.utc)
            elif ctime.tzinfo is None and end_time.tzinfo is not None:
                end_time = end_time.replace(tzinfo=None)
            elapsed_sec = max(0, (end_time - ctime).total_seconds())
            duration_str = _format_duration(elapsed_sec)
        else:
            duration_str = "—"

        bar_html = _progress_bar_html(agg["done"], agg["failed"], total)

        finish_banner = ""
        if is_term:
            if getattr(process_node, "is_finished_ok", False):
                finish_banner = (
                    "<div style='margin-top:12px;padding:8px 12px;background:#e8f5e9;border-radius:4px;color:#1b5e20;font-weight:600;'>"
                    "✓ Calculation complete! Click <strong>View results</strong> below to analyze spectra."
                    "</div>"
                )
            self.view_results_button.layout.display = "inline-block"
            self.view_results_button.disabled = False
        else:
            self.view_results_button.layout.display = "none"

        self.progress_panel.value = (
            "<div style='background:var(--feff-surface, #F4F6F8);border:1px solid var(--feff-rule, #D5DBE1);"
            "border-radius:6px;padding:16px;margin:8px 0;'>"
            "<div style='display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;margin-bottom:12px;'>"
            f"<div><h3 style='margin:0;font-size:16px;color:var(--feff-ink, #1F2933);'>{label}</h3>"
            f"<span style='font-size:12px;color:var(--feff-ink-muted, #666);'>Run #{pk}</span></div>"
            f"<div><span class='{badge_class}' style='font-size:13px;padding:4px 10px;'>{status_text}</span></div>"
            "</div>"
            f"<div style='margin:10px 0;'>{bar_html}</div>"
            "<div style='display:flex;justify-content:space-between;font-size:13px;color:var(--feff-ink-muted, #555);flex-wrap:wrap;gap:8px;'>"
            f"<div><strong>{agg['done']}</strong> of <strong>{total}</strong> frames complete "
            f"({agg['failed']} failed)</div>"
            f"<div>Elapsed: <strong>{duration_str}</strong></div>"
            "</div>"
            f"{finish_banner}"
            "</div>"
        )

        with self.monitor_output:
            self.monitor_output.clear_output()
            try:
                display(ProcessNodeViewerWidget(process_node))
            except Exception:
                print(f"Process {pk}: {status_text}")

    def _on_view_results_click(self, _):
        if self.on_results_loaded is not None:
            self.on_results_loaded()

    def _on_submit(self, _):
        self.submit_button.disabled = True
        self.submit_button.description = "Submitting..."
        self.monitor_output.clear_output()
        try:
            builder = build_workchain_builder(self.input_model, self.workflow_model)
        except ValueError as exc:
            self.status.failure(str(exc))
            self.submit_button.disabled = False
            self.submit_button.description = "Run calculation"
            return

        with self.monitor_output:
            self.monitor_output.clear_output()
            display(LoadingWidget(message="Submitting workflow..."))
        self.status.value = "Submitting..."
        try:
            process_node = engine.submit(builder)
        except Exception as exc:  # noqa: BLE001
            self.monitor_output.clear_output()
            self.status.failure(f"Submission failed: {exc}")
            self.submit_button.disabled = False
            self.submit_button.description = "Run calculation"
            return

        self.submission_model.process_node = process_node
        self.status.success("Calculation started.")
        self.explorer_button.layout.display = "inline-block"
        self._monitor_process()

    AIIDA_EXPLORER_REST_API_URL = "http://localhost:5050/api/v4"
    AIIDA_EXPLORER_APP_URL = "https://aiidateam.github.io/aiida-explorer/"

    def _open_aiida_explorer(self, uuid: str):
        """Open the node in the hosted aiida-explorer app in a new tab."""
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

        self._render_process_view(process_node)

        if process_node.is_terminated:  # type: ignore[attr-defined]
            self._on_finished(process_node)
            return

        # Poll in a background thread, but run every ORM access and widget
        # update back on the kernel's main thread: AiiDA's SQLAlchemy session
        # is thread-scoped (psql_dos uses scoped_session), so nodes loaded in
        # this thread would be detached when a widget callback later touches
        # them on the main thread — the first uncached lazy access raises
        # ``InvalidRequestError: Instance ... is not persistent within this
        # Session``. ``call_soon_threadsafe`` schedules onto the ipykernel
        # asyncio loop, which is where widget callbacks execute.
        import asyncio
        import threading
        import time

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # Not called from the kernel's loop (e.g. a plain script or a test).
            # Nothing will ever service call_soon_threadsafe, so don't pretend to poll.
            self.status.warning("No running event loop; process monitoring is disabled.")
            return

        poll_interval = 2.0
        deadline = time.monotonic() + _MONITOR_TIMEOUT_SECONDS

        def _poll():
            while time.monotonic() < deadline:
                time.sleep(poll_interval)
                done = threading.Event()
                outcome: dict[str, bool] = {}

                def _check(outcome=outcome, done=done):
                    try:
                        current = self.submission_model.process_node
                        if current is None:
                            outcome["stop"] = True
                            return
                        # Reload fresh from the DB each iteration (see note above).
                        fresh = orm.load_node(current.pk)
                        self.submission_model.process_node = fresh
                        self._render_process_view(fresh)
                        outcome["terminated"] = bool(fresh.is_terminated)  # type: ignore[attr-defined]
                    finally:
                        done.set()

                loop.call_soon_threadsafe(_check)
                # Bounded wait: the loop is blocked while the kernel executes a
                # cell, which is routine. Without a timeout this thread would
                # park until the kernel next goes idle, and the 5-minute budget
                # would silently become unbounded wall-clock time.
                if not done.wait(timeout=_MONITOR_CALLBACK_TIMEOUT_SECONDS):
                    continue
                if outcome.get("stop") or outcome.get("terminated"):
                    break

            # Re-read the node on the loop rather than handing one across threads.
            loop.call_soon_threadsafe(lambda: self._on_finished(self.submission_model.process_node))

        thread = threading.Thread(target=_poll, daemon=True, name="feff-process-monitor")
        thread.start()

    def _on_finished(self, process_node):
        if process_node is None:
            return
        # Ensure we read the terminal state from the DB, not a stale cache.
        if not process_node.is_terminated and process_node.pk is not None:
            process_node = orm.load_node(process_node.pk)
        if not process_node.is_terminated:
            return

        self._render_process_view(process_node)

        state = process_node.process_state
        if state == ProcessState.FINISHED:
            if process_node.is_finished_ok:
                self.status.success(f"Process {process_node.pk} finished.")
            elif hasattr(process_node.outputs, "averaged_xas"):
                exit_msg = (
                    getattr(process_node, "exit_message", None)
                    or f"exit status {process_node.exit_status}"
                )
                self.status.warning(
                    f"Process {process_node.pk} finished with warnings: {exit_msg}."
                )
            else:
                exit_msg = (
                    getattr(process_node, "exit_message", None)
                    or f"exit status {process_node.exit_status}"
                )
                self.status.failure(f"Process {process_node.pk} failed: {exit_msg}.")
                return

            try:
                self._populate_results(process_node)
            except Exception as exc:  # noqa: BLE001
                self.status.failure(f"Failed to load results: {exc}")
                return
            if self.on_results_loaded is not None:
                self.on_results_loaded()
        elif state == ProcessState.EXCEPTED:
            exit_msg = getattr(process_node, "exit_message", None) or "Process excepted."
            self.status.failure(f"Process {process_node.pk} excepted: {exit_msg}")
        elif state == ProcessState.KILLED:
            self.status.failure(f"Process {process_node.pk} killed.")

    def _populate_results(self, process_node):
        outputs = process_node.outputs
        averaged_xas = {}
        if hasattr(outputs, "averaged_xas"):
            for key in dir(outputs.averaged_xas):
                if key.startswith("site_") or key == "all":
                    averaged_xas[key] = getattr(outputs.averaged_xas, key)

        xas_grid = _extract_xas_grid(process_node)
        edge, absorber_label = _resolve_absorber_metadata(process_node, averaged_xas)

        # Set the grid + metadata BEFORE averaged_xas: the ResultsWidget observes
        # ``averaged_xas`` and its callback (_render → _populate_conv_selectors)
        # reads xas_grid and edge/absorber_label, so they must be ready first.
        self.results_model.xas_grid = xas_grid or None
        self.results_model.edge = edge
        self.results_model.absorber_label = absorber_label
        self.results_model.is_ensemble = (
            hasattr(process_node.inputs, "trajectory")
            or hasattr(process_node.inputs, "structures")
            or (
                len(self.input_model.selected_indices or []) > 1
                if self.input_model.trajectory is not None
                else len(self.input_model.get_structures() or {}) > 1
            )
        )
        self.results_model.process_node = process_node
        self.results_model.n_failed = outputs.n_failed.value if hasattr(outputs, "n_failed") else 0
        if hasattr(outputs, "path_contributions"):
            self.results_model.path_contributions = outputs.path_contributions
        if hasattr(outputs, "archive"):
            self.results_model.archive = outputs.archive
        self.results_model.averaged_xas = averaged_xas

    def reset(self):
        self.status.clear()
        self.monitor_output.clear_output()
        self.submission_model.reset()


def _extract_xas_grid(process_node) -> dict[tuple[int, int], object]:
    """Build the per-(frame, site) XasData grid from workchain children."""
    xas_grid: dict[tuple[int, int], object] = {}
    if not hasattr(process_node, "pk") or process_node.pk is None:
        return xas_grid

    # Fast path: QueryBuilder retrieves all child XasData outputs in a single SQL query
    try:
        from aiida_feff.data.xasdata import XasData

        qb = orm.QueryBuilder()
        qb.append(orm.WorkChainNode, filters={"pk": process_node.pk}, tag="wc")
        qb.append(orm.ProcessNode, with_incoming="wc", tag="calc")
        qb.append(
            XasData,
            with_incoming="calc",
            edge_project=["label"],
            project=["attributes.frame_index", "attributes.site_index", "*"],
        )
        for f, s, node, lbl in qb.all():
            if f is not None and s is not None:
                xas_grid[(int(f), int(s))] = node
            elif lbl and lbl.startswith("snap_"):
                parts = lbl.split("_")
                if len(parts) >= 4 and parts[1].isdigit() and parts[3].isdigit():
                    xas_grid[(int(parts[1]), int(parts[3]))] = node
                elif len(parts) >= 3 and parts[1].isdigit() and parts[2].isdigit():
                    xas_grid[(int(parts[1]), int(parts[2]))] = node
        if xas_grid:
            return xas_grid
    except Exception as exc:  # noqa: BLE001
        logger.warning("Fast xas_grid QueryBuilder query failed; falling back: %s", exc)

    # Fallback traversal if QueryBuilder matched nothing
    for child in getattr(process_node, "called", []):
        if not getattr(child, "is_finished_ok", False):
            continue
        proc_label = getattr(child, "process_label", None)
        if proc_label == "FeffCalculation" and "xas_data" in child.outputs:
            try:
                xas_grid[(child.inputs.frame_idx.value, child.inputs.site_idx.value)] = (
                    child.outputs.xas_data
                )
            except (KeyError, AttributeError):
                continue
        elif proc_label == "FeffBatchCalculation" and hasattr(child.outputs, "xas_data"):
            try:
                for snap_key in dir(child.outputs.xas_data):
                    if not snap_key.startswith("snap_"):
                        continue
                    parts = snap_key.split("_")
                    if (
                        len(parts) == 4
                        and parts[1].isdigit()
                        and parts[2] == "site"
                        and parts[3].isdigit()
                    ):
                        frame_idx = int(parts[1])
                        site_idx = int(parts[3])
                        xas_grid[(frame_idx, site_idx)] = getattr(child.outputs.xas_data, snap_key)
                    elif len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
                        frame_idx = int(parts[1])
                        site_idx = int(parts[2])
                        xas_grid[(frame_idx, site_idx)] = getattr(child.outputs.xas_data, snap_key)
            except Exception:  # noqa: BLE001
                continue
    return xas_grid


def _resolve_absorber_metadata(process_node, averaged_xas: dict) -> tuple[str, str]:
    """Extract absorber element + edge for plot titles and legends."""
    edge = ""
    absorber_label = ""
    try:
        params = process_node.inputs.parameters.get_dict()
        edge = str(params.get("edge", "")).upper()
        active_sites = [
            int(k.removeprefix("site_"))
            for k in averaged_xas
            if k.startswith("site_") and k.removeprefix("site_").isdigit()
        ]
        if active_sites:
            atoms = sorted(active_sites)
        else:
            atoms = params.get("absorbing_atoms", None) or []
            if not isinstance(atoms, list):
                atoms = [atoms] if atoms else []
            if not atoms and "absorbing_atom" in params:
                atoms = [params["absorbing_atom"]]
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
        n_sites = len(atoms)
        if len(elements) == 1:
            absorber_label = f"{elements[0]} ({n_sites} sites)" if n_sites > 1 else elements[0]
        elif elements:
            absorber_label = "/".join(elements)
            if n_sites > 1:
                absorber_label += f" ({n_sites} sites)"
    except Exception:  # noqa: BLE001
        pass
    return edge, absorber_label


def get_workchain_status(process_node) -> str:
    """Return a short status string for a process node."""
    if process_node is None:
        return "No process."
    status = f"PK {process_node.pk}: {process_node.process_state}"
    is_terminated = getattr(process_node, "is_terminated", False)
    exit_status = getattr(process_node, "exit_status", None)
    if is_terminated and exit_status is not None:
        status += f" [{exit_status}]"
        if getattr(process_node, "exit_message", None):
            status += f" — {process_node.exit_message}"
    return status
