"""Live overview of running FEFF ensemble workflows."""

from __future__ import annotations

from collections.abc import Callable
from typing import NamedTuple

import ipywidgets as ipw
from aiida import orm
from aiida.orm import QueryBuilder, WorkChainNode, load_node
from alc_aiidalab_widgets.widgets.status import Status


def _table_cell(value: str, width: str) -> ipw.HTML:
    """Return an escaped, clipped table cell."""
    import html

    escaped_value = html.escape(str(value))
    return ipw.HTML(
        (
            f'<span title="{escaped_value}" '
            'style="display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">'
            f"{escaped_value}</span>"
        ),
        layout={"width": width},
    )


#: process_label of the FEFF ensemble workchain submitted by this app.
WORKCHAIN_LABEL = "EnsembleExafsWorkChain"

#: Child process labels that represent FEFF fan-out jobs.
_JOB_LABELS = ("FeffCalculation", "FeffBatchCalculation")

#: Process states that count as still in flight.
_ACTIVE_STATES = frozenset({"created", "running", "waiting"})

#: Process states that mean the workchain is no longer running.
_TERMINAL_STATES = ("finished", "excepted", "killed")


def _is_running_workflow(node: object) -> bool:
    """Return True if node is an unfinished EnsembleExafsWorkChain."""
    if not isinstance(node, WorkChainNode):
        return False
    if node.process_label != WORKCHAIN_LABEL:
        return False
    return not node.is_terminated


def _state_value(node) -> str:
    """Return a node's process state as a plain lowercase string."""
    state = getattr(node, "process_state", None)
    value = getattr(state, "value", None)
    if value is not None:
        return str(value)
    return str(state) if state is not None else ""


def _count_batch_snaps(node) -> int | None:
    """Return how many (frame, site) results a finished batch job produced."""
    try:
        xas = node.outputs.xas_data
    except Exception:  # noqa: BLE001
        return None
    return sum(1 for key in dir(xas) if key.startswith("snap_"))


class BatchLinkMaps(NamedTuple):
    """Batched link lookup caches used by _job_record to prevent N+1 queries."""

    has_frame_idx: set[int]
    frame_counts: dict[int, int]
    snap_counts: dict[int, int]


def _batch_link_maps(child_pks: list[int]) -> BatchLinkMaps:
    """Resolve, in three queries, the per-child link facts ``_job_record`` needs.

    Doing this per child is an N+1: ``"frame_idx" in child.inputs``,
    ``child.inputs.frame_indices`` and ``dir(child.outputs.xas_data)`` each issue
    their own link query, which measured 1.9 s for a 68-child run. Returns
    ``BatchLinkMaps(has_frame_idx, frame_counts, snap_counts)``.
    """
    has_frame_idx: set[int] = set()
    frame_counts: dict[int, int] = {}
    snap_counts: dict[int, int] = {}
    if not child_pks:
        return BatchLinkMaps(has_frame_idx, frame_counts, snap_counts)

    # Inputs labelled ``frame_idx`` (marks a real per-snapshot FeffCalculation).
    qb = QueryBuilder()
    qb.append(orm.Node, filters={"id": {"in": child_pks}}, tag="job", project=["id"])
    qb.append(orm.Data, with_outgoing="job", edge_filters={"label": "frame_idx"}, project=["id"])
    for pk, _ in qb.all():
        has_frame_idx.add(int(pk))

    # ``frame_indices`` input lists (how many snapshots a batch job covers).
    qb = QueryBuilder()
    qb.append(orm.Node, filters={"id": {"in": child_pks}}, tag="job", project=["id"])
    qb.append(
        orm.List,
        with_outgoing="job",
        edge_filters={"label": "frame_indices"},
        project=["attributes.list"],
    )
    for pk, values in qb.all():
        frame_counts[int(pk)] = len(values or [])

    # ``xas_data__snap_*`` outputs (how many results a batch job actually produced).
    qb = QueryBuilder()
    qb.append(orm.Node, filters={"id": {"in": child_pks}}, tag="job", project=["id"])
    qb.append(
        orm.Data,
        with_incoming="job",
        edge_filters={"label": {"like": "xas\\_data\\_\\_snap\\_%"}},
        project=["id"],
    )
    for pk, _ in qb.all():
        snap_counts[int(pk)] = snap_counts.get(int(pk), 0) + 1

    return BatchLinkMaps(has_frame_idx, frame_counts, snap_counts)


def _job_record(child, link_maps: BatchLinkMaps | tuple | None = None) -> dict | None:
    """Summarize one child FEFF job for progress accounting.

    Returns None for jobs that do not represent a (frame, site) calculation,
    such as potentials-only precompute runs.

    ``link_maps`` is the batched ``BatchLinkMaps`` result. When omitted the
    per-child link lookups are done directly (slower, but keeps this function
    usable on its own).
    """
    label = str(getattr(child, "label", "") or "")
    if label.startswith("pot_"):
        return None
    process_label = getattr(child, "process_label", None)
    is_batch = process_label == "FeffBatchCalculation"
    pk = getattr(child, "pk", None)
    has_frame_idx = (
        link_maps.has_frame_idx
        if hasattr(link_maps, "has_frame_idx")
        else (link_maps[0] if link_maps else None)
    )
    frame_counts = (
        link_maps.frame_counts
        if hasattr(link_maps, "frame_counts")
        else (link_maps[1] if link_maps else None)
    )
    snap_counts = (
        link_maps.snap_counts
        if hasattr(link_maps, "snap_counts")
        else (link_maps[2] if link_maps else None)
    )
    if process_label == "FeffCalculation":
        # Potentials-only jobs carry no frame index; skip if we can tell.
        try:
            if has_frame_idx is not None:
                if pk not in has_frame_idx:
                    return None
            elif "frame_idx" not in child.inputs:
                return None
        except Exception:  # noqa: BLE001
            pass

    state = _state_value(child)
    ok = bool(getattr(child, "is_finished_ok", False)) if state == "finished" else None

    if is_batch:
        try:
            if frame_counts is not None:
                covered = frame_counts.get(pk, 0)
            else:
                covered = len(child.inputs.frame_indices.get_list())
        except Exception:  # noqa: BLE001
            covered = 0
        done_snaps = None
        if state == "finished":
            if ok:
                count = (
                    snap_counts.get(pk, 0) if snap_counts is not None else _count_batch_snaps(child)
                )
                done_snaps = count if count else covered
            else:
                done_snaps = 0
    else:
        covered = 1
        done_snaps = 1 if ok else (0 if state == "finished" else None)

    return {
        "label": label,
        "state": state,
        "ok": ok,
        "covered": covered,
        "done_snaps": done_snaps,
    }


def _aggregate_jobs(jobs: list[dict]) -> dict:
    """Aggregate per-job records into done/failed/pending calculation counts."""
    agg = {"done": 0, "failed": 0, "pending": 0, "jobs": 0}
    for job in jobs:
        if job["label"].startswith("pot_"):
            continue
        agg["jobs"] += 1
        covered = int(job["covered"] or 0)
        state = job["state"]
        if state in _ACTIVE_STATES:
            agg["pending"] += covered
        elif state == "finished" and job["ok"]:
            done = job["done_snaps"]
            done = int(done if done is not None else covered)
            agg["done"] += done
            agg["failed"] += max(covered - done, 0)
        else:
            # Finished with errors, excepted, or killed.
            agg["failed"] += covered
    return agg


def _collect_jobs(process_node) -> list[dict]:
    """Fetch child FEFF job records for a workchain."""
    if getattr(process_node, "pk", None) is None:
        return []
    try:
        qb = QueryBuilder()
        qb.append(WorkChainNode, filters={"pk": process_node.pk}, tag="wc")
        qb.append(
            orm.ProcessNode,
            with_incoming="wc",
            filters={"attributes.process_label": {"in": list(_JOB_LABELS)}},
            project=["*"],
        )
        children = list(qb.all(flat=True))
    except Exception:  # noqa: BLE001
        children = [
            child
            for child in getattr(process_node, "called", [])
            if getattr(child, "process_label", None) in _JOB_LABELS
        ]

    try:
        link_maps = _batch_link_maps([c.pk for c in children if getattr(c, "pk", None)])
    except Exception:  # noqa: BLE001
        link_maps = None  # fall back to per-child lookups inside _job_record

    return [record for child in children if (record := _job_record(child, link_maps)) is not None]


def _int_like_site_count(spec) -> int | None:
    """Return the site count for int-like absorber specs, None otherwise."""
    if isinstance(spec, bool):
        return None
    if isinstance(spec, int):
        return 1 if spec >= 0 else None
    if isinstance(spec, (list, tuple)):
        if not spec:
            return 0
        if all(isinstance(x, int) and not isinstance(x, bool) and x >= 0 for x in spec):
            return len(spec)
        return None
    return None


def _count_absorber_sites(spec, structure) -> int | None:
    """Return the number of absorber sites for a parameters spec, if resolvable."""
    count = _int_like_site_count(spec)
    if count is not None:
        return count
    # Element symbol / "Cu:0,1" spec: needs a reference structure.
    if structure is None:
        return None
    from aiida_feff.workflows.ensemble import _resolve_absorber_sites

    try:
        return len(_resolve_absorber_sites(structure, spec))
    except Exception:  # noqa: BLE001
        return None


def _count_structures(inputs) -> int | None:
    """Return the number of snapshot structures a workchain will process."""
    structures_namespace = getattr(inputs, "structures", None)
    if structures_namespace is not None and len(structures_namespace) > 0:
        return len(structures_namespace)
    trajectory = getattr(inputs, "trajectory", None)
    if trajectory is None:
        return None
    step_ids = getattr(inputs, "step_ids", None)
    if step_ids is not None:
        return len(step_ids.get_list())
    interval = 1
    sample = getattr(inputs, "sample_interval", None)
    if sample is not None:
        interval = max(int(sample.value), 1)
    n_steps = len(trajectory.get_array("positions"))
    return len(range(0, n_steps, interval))


def _reference_structure(inputs):
    """Return one structure from the workchain inputs, if available."""
    structures_namespace = getattr(inputs, "structures", None)
    if structures_namespace is not None and len(structures_namespace) > 0:
        keys = sorted(structures_namespace.keys())
        return structures_namespace[keys[-1]]
    trajectory = getattr(inputs, "trajectory", None)
    if trajectory is None:
        return None
    step_ids = getattr(inputs, "step_ids", None)
    if step_ids is not None and step_ids.get_list():
        step_id = step_ids.get_list()[0]
    else:
        stepids = trajectory.get_stepids()
        if not stepids:
            return None
        step_id = stepids[0]
    return trajectory.get_step_structure(trajectory.get_index_from_stepid(step_id))


def _estimate_expected_calculations(node) -> int | None:
    """Best-effort total number of (frame, site) FEFF calculations from inputs."""
    try:
        inputs = node.inputs
        params = inputs.parameters.get_dict()
        spec = params.get("absorbing_atoms")
        if spec is None:
            spec = params.get("absorbing_atom")
        if spec is None:
            return None
        structure = None
        n_sites = _count_absorber_sites(spec, structure)
        if n_sites is None:
            structure = _reference_structure(inputs)
            n_sites = _count_absorber_sites(spec, structure)
        if n_sites is None:
            return None
        n_structures = _count_structures(inputs)
        if n_structures is None:
            return None
        return n_structures * n_sites
    except Exception:  # noqa: BLE001
        return None


def _progress_bar_html(done: int, failed: int, total: int) -> str:
    """Return an inline-styled progress bar with green/red segments."""
    total = max(total, done + failed, 1)
    done_pct = min(100, int(round(100 * done / total)))
    fail_pct = min(100 - done_pct, int(round(100 * failed / total)))
    return (
        '<div style="display:flex;width:150px;height:12px;background:#e9ecef;'
        'border-radius:3px;overflow:hidden;">'
        f'<div style="width:{done_pct}%;background:#28a745;"></div>'
        f'<div style="width:{fail_pct}%;background:#dc3545;"></div>'
        "</div>"
    )


def _counts_text(done: int, failed: int, pending: int, expected: int | None) -> str:
    """Return a compact done/failed/left summary for one workflow."""
    if expected is not None:
        left = max(expected - done - failed, 0)
        return f"{done}/{expected} done · {failed} failed · {left} left"
    return f"{done} done · {failed} failed · {pending} pending"


class RunningTasksWidget(ipw.VBox):
    """List running FEFF ensemble workflows with per-calculation progress."""

    def __init__(
        self,
        submission_model=None,
        on_open: Callable[[WorkChainNode], None] | None = None,
        on_refreshed: Callable[[int], None] | None = None,
    ):
        self.submission_model = submission_model
        self.on_open = on_open
        self.on_refreshed = on_refreshed
        self.last_count: int | None = None

        self.header = ipw.HTML("<h2>Running FEFF tasks</h2>")
        self.description = ipw.HTML(
            "Unfinished FEFF ensemble workflows with per-calculation progress. "
            "Open one to monitor it in the New calculation tab. "
            "● marks the workflow submitted in this session."
        )
        self.refresh_button = ipw.Button(description="Refresh", button_style="info", icon="refresh")
        self.refresh_button.on_click(self.refresh)
        self.tasks_table = ipw.VBox(
            layout={
                "width": "760px",
                "max_height": "420px",
                "overflow": "auto",
                "border": "1px solid #ddd",
            }
        )
        self.status = Status()

        super().__init__(
            [
                self.header,
                self.description,
                ipw.HBox([self.refresh_button]),
                self.tasks_table,
                self.status,
            ]
        )
        self.refresh()

    def refresh(self, _=None):
        """Re-query running workflows and re-render the task table."""
        try:
            nodes = self._query_running()
            records = [self._summarize(node) for node in nodes]
        except Exception as exc:  # noqa: BLE001
            self.status.failure(f"Could not query running workflows: {exc}")
            return
        records.sort(key=lambda record: record["ctime"], reverse=True)
        current_pk = None
        if self.submission_model is not None:
            process_node = getattr(self.submission_model, "process_node", None)
            current_pk = getattr(process_node, "pk", None)
        self.tasks_table.children = _build_table_rows(records, current_pk, self._open)
        self.last_count = len(records)
        if not records:
            self.status.value = "No running FEFF workflows."
        else:
            self.status.value = f"{len(records)} running FEFF workflow(s)."
        if self.on_refreshed is not None:
            self.on_refreshed(self.last_count)

    def _query_running(self) -> list[WorkChainNode]:
        """Return unfinished EnsembleExafsWorkChain nodes, newest first."""
        qb = QueryBuilder()
        qb.append(
            WorkChainNode,
            filters={
                "attributes.process_label": WORKCHAIN_LABEL,
                "attributes.process_state": {"!in": list(_TERMINAL_STATES)},
            },
            project=["*"],
        )
        qb.order_by({WorkChainNode: {"ctime": "desc"}})
        return list(qb.all(flat=True))

    def _summarize(self, node: WorkChainNode) -> dict:
        """Aggregate progress counts for one running workflow."""
        agg = _aggregate_jobs(_collect_jobs(node))
        return {
            "pk": node.pk,
            "ctime": node.ctime,
            "state": _state_value(node),
            "done": agg["done"],
            "failed": agg["failed"],
            "pending": agg["pending"],
            "expected": _estimate_expected_calculations(node),
        }

    def _open(self, pk: int):
        """Open a running workflow via the on_open callback."""
        if self.on_open is None:
            return
        try:
            node = load_node(pk)
        except Exception:  # noqa: BLE001
            self.status.failure(f"Could not load Process {pk}.")
            return
        self.on_open(node)


def _build_table_rows(
    records: list[dict], current_pk: int | None, on_open: Callable[[int], None]
) -> tuple:
    """Build column-aligned rows for the running-tasks browser."""
    columns = [
        ("PK", "65px"),
        ("State", "85px"),
        ("Progress", "340px"),
        ("Started", "120px"),
        ("", "75px"),
    ]
    header = ipw.HBox(
        [
            ipw.HTML(f"<strong>{title}</strong>", layout={"width": width})
            for title, width in columns
        ],
        layout={"padding": "4px 8px", "border_bottom": "1px solid #ddd"},
    )
    if not records:
        return (header, ipw.HTML("<em>No running FEFF workflows.</em>"))

    rows = [header]
    for record in records:
        button = ipw.Button(
            description="Open",
            icon="arrow-right",
            layout={"width": "75px"},
        )
        button.on_click(lambda _, pk=record["pk"]: on_open(pk))
        expected = record["expected"]
        total = (
            expected
            if expected is not None
            else (record["done"] + record["failed"] + record["pending"])
        )
        pk_label = str(record["pk"])
        if current_pk is not None and record["pk"] == current_pk:
            pk_label += " ●"
        rows.append(
            ipw.HBox(
                [
                    _table_cell(pk_label, "65px"),
                    _table_cell(record["state"], "85px"),
                    ipw.VBox(
                        [
                            ipw.HTML(_progress_bar_html(record["done"], record["failed"], total)),
                            ipw.HTML(
                                _counts_text(
                                    record["done"],
                                    record["failed"],
                                    record["pending"],
                                    expected,
                                )
                            ),
                        ],
                        layout={"width": "340px"},
                    ),
                    _table_cell(record["ctime"].strftime("%Y-%m-%d %H:%M"), "120px"),
                    button,
                ],
                layout={
                    "padding": "4px 8px",
                    "border_bottom": "1px solid #eee",
                    "align_items": "center",
                },
            )
        )
    return tuple(rows)
