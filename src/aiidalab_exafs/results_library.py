"""Unified Runs browser for completed and active FEFF ensemble calculations (Screen 5)."""

from __future__ import annotations

import datetime
import html
from collections.abc import Callable

import ipywidgets as ipw
import numpy as np
from aiida import orm
from aiida.orm import QueryBuilder, StructureData, WorkChainNode, load_node
from alc_aiidalab_widgets.widgets.status import Status
from alc_aiidalab_widgets.widgets.structure import StructureViewWidget

from aiidalab_exafs.common.download import Download
from aiidalab_exafs.common.file_handling import find_combined_h5_node, get_combined_h5_bytes
from aiidalab_exafs.running_tasks import (
    _TERMINAL_STATES,
    WORKCHAIN_LABEL,
    _count_structures,
    _reference_structure,
)


def _format_duration(seconds: float) -> str:
    """Format duration into human readable string."""
    seconds = int(max(0, seconds))
    mins, secs = divmod(seconds, 60)
    hours, mins = divmod(mins, 60)
    if hours > 0:
        return f"{hours}h {mins}m {secs}s"
    if mins > 0:
        return f"{mins}m {secs}s"
    return f"{secs}s"


def _generate_chir_thumbnail_svg(node: WorkChainNode) -> str:
    """Generate a clean SVG sparkline of |chi(R)| for the details preview."""
    try:
        if not hasattr(node.outputs, "averaged_xas"):
            return ""
        xas_dict = node.outputs.averaged_xas
        site_keys = [k for k in dir(xas_dict) if k.startswith("site_") or k == "all"]
        if not site_keys:
            return ""
        key = "all" if "all" in site_keys else site_keys[0]
        xas_node = getattr(xas_dict, key)
        k = np.asarray(xas_node.get_array("k"), dtype=float)
        chi = np.asarray(xas_node.get_array("chi_k"), dtype=float)
        from aiida_feff.calcfunctions.larch import xftf_arrays

        kmax_val = min(14.0, float(k.max()))
        res = xftf_arrays(
            k, chi, {"kmin": 2.0, "kmax": kmax_val, "kweight": 2, "dk": 1.0, "rmax": 6.0}
        )
        r = np.asarray(res["r"])
        chir = np.asarray(res["chir_mag"])
        mask = (r >= 0.5) & (r <= 6.0)
        r_sub = r[mask]
        c_sub = chir[mask]
        if len(r_sub) < 5 or c_sub.max() <= 0:
            return ""
        width = 240
        height = 55
        x_scaled = (r_sub - r_sub.min()) / (r_sub.max() - r_sub.min()) * (width - 16) + 8
        y_scaled = height - 6 - (c_sub / c_sub.max()) * (height - 14)
        pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(x_scaled, y_scaled, strict=False))
        return (
            f"<div style='margin:10px 0 6px 0;background:var(--feff-surface-elevated, #fff);"
            f"border:1px solid var(--feff-rule-light, #E4E7EB);border-radius:4px;padding:6px;'>"
            f"<div style='font-size:11px;font-weight:600;color:var(--feff-ink-muted, #666);margin-bottom:2px;'>"
            f"|χ(R)| preview (k-weight=2)"
            f"</div>"
            f"<svg width='{width}' height='{height}' style='display:block;margin:0 auto;'>"
            f"<polyline fill='none' stroke='#0072B2' stroke-width='2' stroke-linecap='round' stroke-linejoin='round' points='{pts}' />"
            f"</svg>"
            f"</div>"
        )
    except Exception:
        return ""


class ResultsLibraryWidget(ipw.VBox):
    """Merged calculation runs browser for active and past workflows."""

    def __init__(
        self,
        on_open: Callable[[WorkChainNode], None],
        on_refreshed: Callable[[int], None] | None = None,
    ):
        """Initialize the unified calculation runs browser."""
        self.on_open = on_open
        self.on_refreshed = on_refreshed
        self._records: dict[int, dict] = {}
        self._selected_pk: int | None = None
        self.last_count: int | None = None

        self.header = ipw.HTML("<h2>Calculation runs</h2>")
        self.description = ipw.HTML(
            "<p style='color:var(--feff-ink-muted, #555);margin-top:0;'>"
            "Overview of all EXAFS calculation runs. Click a row to view its details and spectrum preview, "
            "or open it directly."
            "</p>"
        )

        default_start = datetime.date.today() - datetime.timedelta(days=60)
        self.start_date = ipw.Text(
            value=default_start.isoformat(),
            description="From:",
            style={"description_width": "initial"},
            layout={"width": "160px"},
        )
        self.end_date = ipw.Text(
            value=datetime.date.today().isoformat(),
            description="To:",
            style={"description_width": "initial"},
            layout={"width": "160px"},
        )
        self.material_filter = ipw.Text(
            placeholder="e.g. Cu or Fe2O3",
            description="Material:",
            style={"description_width": "initial"},
            layout={"width": "220px"},
        )
        self.status_filter = ipw.Dropdown(
            options=[
                ("All statuses", ""),
                ("Running", "running"),
                ("Done", "done"),
                ("Failed", "failed"),
            ],
            value="",
            description="Status:",
            style={"description_width": "initial"},
            layout={"width": "170px"},
        )
        self.search_button = ipw.Button(
            description="Refresh",
            icon="refresh",
            layout={"width": "auto", "min_width": "90px"},
        )
        self.search_button.add_class("feff-btn-secondary")
        self.search_button.on_click(self._search)

        self.results_table = ipw.VBox(
            layout=ipw.Layout(
                flex="1 1 800px",
                min_width="520px",
                max_height="480px",
                overflow="auto",
                border="1px solid #D5DBE1",
            )
        )

        self.preview = ipw.HTML("<em>Select a calculation run to inspect details.</em>")
        self.preview_thumbnail = ipw.HTML()
        self.structure_viewer = StructureViewWidget()
        self.structure_viewer.layout = ipw.Layout(width="100%", height="260px")

        self.open_button = ipw.Button(
            description="View results",
            button_style="primary",
            icon="bar-chart",
            disabled=True,
            layout=ipw.Layout(width="100%", margin="8px 0 4px 0"),
        )
        self.open_button.add_class("feff-btn-primary")
        self.open_button.on_click(self._open_selected)

        self.download_h5_output = ipw.Output(layout=ipw.Layout(display="none"))
        self.download_h5_button = Download(
            "feff-run-combined.h5",
            cb=self._download_selected_h5,
            output=self.download_h5_output,
            mimetype="application/x-hdf5",
            description="Download combined .h5",
            icon="download",
            disabled=True,
            layout=ipw.Layout(width="100%", margin="0 0 8px 0"),
        )
        self.download_h5_button.add_class("feff-btn-secondary")

        # Open by run ID (PK)
        self.pk_input = ipw.Text(
            placeholder="Run ID (PK)",
            description="Open run ID:",
            style={"description_width": "initial"},
            layout={"width": "200px"},
        )
        self.load_pk_button = ipw.Button(
            description="Open",
            icon="folder-open",
            layout=ipw.Layout(width="auto", min_width="80px"),
        )
        self.load_pk_button.add_class("feff-btn-secondary")
        self.load_pk_button.on_click(self._load_pk)
        self.load_pk_status = ipw.HTML()

        open_by_id_row = ipw.HBox(
            [self.pk_input, self.load_pk_button, self.load_pk_status],
            layout=ipw.Layout(align_items="center", grid_gap="8px", margin="8px 0"),
        )
        open_by_id_accordion = ipw.Accordion(children=[open_by_id_row])
        open_by_id_accordion.set_title(0, "Open calculation by run ID (PK)")
        open_by_id_accordion.selected_index = None

        self.status = Status()

        filters = ipw.HBox(
            [
                self.start_date,
                self.end_date,
                self.material_filter,
                self.status_filter,
                self.search_button,
            ],
            layout=ipw.Layout(
                flex_flow="row wrap",
                align_items="center",
                grid_gap="12px",
                padding="10px 14px",
                border="1px solid #D5DBE1",
                margin="0 0 14px 0",
            ),
        )

        details_sidebar = ipw.VBox(
            [
                self.preview,
                self.open_button,
                self.download_h5_button,
                self.preview_thumbnail,
                self.structure_viewer,
                self.download_h5_output,
            ],
            layout=ipw.Layout(
                width="340px",
                min_width="280px",
                padding="12px 14px",
                border="1px solid #D5DBE1",
            ),
        )

        table_and_details = ipw.HBox(
            [self.results_table, details_sidebar],
            layout=ipw.Layout(
                flex_flow="row wrap",
                align_items="flex-start",
                grid_gap="16px",
                width="100%",
            ),
        )

        super().__init__(
            [
                self.header,
                self.description,
                filters,
                table_and_details,
                open_by_id_accordion,
                self.status,
            ]
        )
        # The Runs tab is not the tab the app opens on, and building the table
        # summarises every workchain in the range (reading inputs, a reference
        # structure and a frame count per row, 7 s of app startup). At
        # construction we only need the badge count, which is one query; the
        # table is built when the tab is first selected, via refresh().
        self._count_running()

    def refresh(self, _=None):
        """Public alias for refresh."""
        self._search()

    def _count_running(self) -> None:
        """Set ``last_count`` from a single projection, without building the table."""
        try:
            query = QueryBuilder()
            query.append(
                WorkChainNode,
                filters={"attributes.process_label": WORKCHAIN_LABEL},
                project=["attributes.process_state"],
            )
            self.last_count = sum(
                1 for (state,) in query.all() if str(state or "") not in _TERMINAL_STATES
            )
        except Exception:  # noqa: BLE001
            self.last_count = None

    def _search(self, _=None):
        """Query and display both running and finished workflows."""
        try:
            start_date = datetime.datetime.strptime(self.start_date.value, "%Y-%m-%d")
            end_date = datetime.datetime.strptime(
                self.end_date.value, "%Y-%m-%d"
            ) + datetime.timedelta(days=1)
        except ValueError:
            self.status.failure("Use dates in YYYY-MM-DD format.")
            return

        query = QueryBuilder()
        query.append(
            WorkChainNode,
            filters={
                "attributes.process_label": WORKCHAIN_LABEL,
                "ctime": {">=": start_date, "<": end_date},
            },
            project=["*"],
        )
        query.order_by({WorkChainNode: {"ctime": "desc"}})

        material_needle = self.material_filter.value.strip().lower()
        status_filter_val = self.status_filter.value

        records = []
        running_count = 0
        for node in query.all(flat=True):
            rec = _summarize_workflow_unified(node)
            if rec["status_code"] == "running":
                running_count += 1
            if status_filter_val and rec["status_code"] != status_filter_val:
                continue
            searchable = f"{rec['formula']} {rec['label']} {rec['absorber']}".lower()
            if material_needle and material_needle not in searchable:
                continue
            records.append(rec)

        self._records = {r["pk"]: r for r in records}
        self._selected_pk = None
        self.results_table.children = _build_unified_table_rows(
            records, self._select_record, self.on_open
        )
        self.preview.value = "<em>Select a calculation run to inspect details.</em>"
        self.preview_thumbnail.value = ""
        self.open_button.disabled = True
        self.download_h5_button.disabled = True
        self.download_h5_button.description = "Download combined .h5"
        self.download_h5_button.tooltip = "Download combined .h5 file for the selected run"
        self.last_count = running_count

        total_runs = len(records)
        run_word = "runs" if total_runs != 1 else "run"
        running_part = f" ({running_count} running)" if running_count else ""
        self.status.value = f"Found {total_runs} calculation {run_word}{running_part}."

        if self.on_refreshed is not None:
            self.on_refreshed(running_count)

    def _select_record(self, pk: int):
        """Render details when a row is clicked."""
        self._selected_pk = pk
        record = self._records.get(pk)
        self.open_button.disabled = record is None
        if record is None:
            self.preview.value = "<em>Select a calculation run to inspect details.</em>"
            self.preview_thumbnail.value = ""
            self.structure_viewer.children = [self.structure_viewer.message]
            self.download_h5_button.disabled = True
            self.download_h5_button.description = "Download combined .h5"
            self.download_h5_button.tooltip = "Download combined .h5 file for the selected run"
            return

        status_badge = (
            f"<span class='{record['badge_class']}'>{html.escape(record['status_text'])}</span>"
        )
        label_html = (
            html.escape(record["label"]) if record["label"] != "—" else "<em>(No label)</em>"
        )

        failed_part = ""
        if record["n_failed"] is not None and record["n_failed"] > 0:
            failed_part = (
                f"<dt style='color:var(--feff-danger);'>Failed frames</dt>"
                f"<dd style='color:var(--feff-danger);font-weight:600;'>{record['n_failed']}</dd>"
            )

        self.preview.value = (
            "<div style='margin-bottom:8px;'>"
            f"<div style='font-size:15px;font-weight:600;color:var(--feff-ink);margin-bottom:2px;'>"
            f"{label_html}"
            f"</div>"
            f"<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;'>"
            f"<span style='font-size:12px;color:var(--feff-ink-muted);'>Run #{record['pk']}</span>"
            f"{status_badge}"
            f"</div>"
            "<dl style='display:grid;grid-template-columns:90px 1fr;row-gap:4px;font-size:12.5px;margin:0;'>"
            f"<dt style='color:var(--feff-ink-muted);'>Material</dt><dd><strong>{html.escape(record['formula'])}</strong></dd>"
            f"<dt style='color:var(--feff-ink-muted);'>Absorber</dt><dd>{html.escape(record['absorber'])}</dd>"
            f"<dt style='color:var(--feff-ink-muted);'>Scope</dt><dd>{record['frames_sites']} calculations</dd>"
            f"<dt style='color:var(--feff-ink-muted);'>Started</dt><dd>{record['ctime']:%Y-%m-%d %H:%M}</dd>"
            f"<dt style='color:var(--feff-ink-muted);'>Duration</dt><dd>{record['duration_str']}</dd>"
            f"{failed_part}"
            "</dl>"
            "</div>"
        )

        try:
            node = record["node"]
            self.preview_thumbnail.value = _generate_chir_thumbnail_svg(node)
            st = _reference_structure(node.inputs)
            if st is not None:
                self.structure_viewer.assign_structure_from_structuredata(st)
        except Exception:
            self.preview_thumbnail.value = ""

        # Update download button state
        try:
            node = record.get("node")
            h5_node = find_combined_h5_node(node)
            if h5_node is not None:
                self.download_h5_button.disabled = False
                self.download_h5_button.filename = f"feff-run-{pk}-combined.h5"
                self.download_h5_button.tooltip = f"Download combined .h5 file for Run #{pk}"
                self.download_h5_button.description = "Download combined .h5"
            else:
                self.download_h5_button.disabled = True
                self.download_h5_button.tooltip = f"No combined .h5 file available for Run #{pk}"
                self.download_h5_button.description = "Download combined .h5"
        except Exception:
            self.download_h5_button.disabled = True
            self.download_h5_button.description = "Download combined .h5"

    def _download_selected_h5(self) -> bytes:
        """Download callback for the selected run in ResultsLibraryWidget."""
        pk = self._selected_pk
        if pk is None:
            return b""
        record = self._records.get(pk)
        node = record.get("node") if record else pk
        return get_combined_h5_bytes(node) or b""

    def _open_selected(self, _):
        """Open the active selected calculation in the main app."""
        pk = self._selected_pk
        if pk is None:
            return
        node = load_node(pk)
        if isinstance(node, WorkChainNode):
            self.status.value = f"Loading results for Run #{pk}..."
            self.open_button.disabled = True
            self.open_button.description = "Loading..."
            try:
                self.on_open(node)
                self.status.value = f"Loaded calculation Run #{pk}."
            finally:
                self.open_button.disabled = False
                self.open_button.description = "View results"

    def _load_pk(self, _):
        """Open a workflow by run ID (PK)."""
        val = self.pk_input.value.strip()
        if not val:
            return
        try:
            pk = int(val)
            node = load_node(pk)
        except Exception:
            self.load_pk_status.value = "<span style='color:var(--feff-danger,#c52707);font-size:12px;'>Run ID not found.</span>"
            return

        if not isinstance(node, WorkChainNode) or node.process_label != WORKCHAIN_LABEL:
            self.load_pk_status.value = "<span style='color:var(--feff-danger,#c52707);font-size:12px;'>That process is not a FEFF workflow.</span>"
            return

        self.load_pk_status.value = f"<span style='color:var(--feff-success,#2e7d4f);font-size:12px;'>Loaded results for PK {pk}.</span>"
        self.on_open(node)


def _summarize_workflow_unified(node: WorkChainNode) -> dict:
    """Extract unified metadata for both running and finished workflows."""
    inputs = node.inputs
    parameters_node = getattr(inputs, "parameters", None)
    parameters = parameters_node.get_dict() if isinstance(parameters_node, orm.Dict) else {}

    structure = _reference_structure(inputs)
    formula = "Unknown material"
    if isinstance(structure, StructureData):
        formula = structure.get_formula(mode="hill")

    n_structures = _count_structures(inputs) or 1
    edge = str(parameters.get("edge", "")).upper()
    atoms = parameters.get("absorbing_atoms", [])
    if not isinstance(atoms, list):
        atoms = [atoms] if atoms else []
    n_sites = len(atoms) if atoms else 1

    absorber_el = ""
    if structure is not None and atoms:
        idx = atoms[0]
        if 0 <= idx < len(structure.sites):
            kind = structure.get_kind(structure.sites[idx].kind_name)
            absorber_el = str(kind.symbols[0]) if kind.symbols else ""

    absorber_text = f"{absorber_el} {edge}-edge".strip() if absorber_el else f"{edge}-edge"
    if n_sites > 1:
        absorber_text += f" ({n_sites} sites)"

    frames_sites = f"{n_structures} × {n_sites}" if n_sites > 1 else str(n_structures)

    # State
    is_term = bool(getattr(node, "is_terminated", False))
    state = getattr(node, "process_state", None)
    val = getattr(state, "value", str(state)).lower() if state else ""

    if not is_term:
        status_code = "running"
        status_text = "Running" if val in ("running", "waiting") else "Queued"
        badge_class = "feff-badge feff-badge-running"
    elif getattr(node, "is_finished_ok", False):
        status_code = "done"
        status_text = "Done"
        badge_class = "feff-badge feff-badge-done"
    elif node.is_finished and hasattr(node.outputs, "averaged_xas"):
        status_code = "done"
        failed_cnt = getattr(node.outputs, "n_failed", None)
        cnt_val = getattr(failed_cnt, "value", None)
        status_text = f"Done ({cnt_val} failed)" if cnt_val else "Done (warnings)"
        badge_class = "feff-badge feff-badge-done"
    else:
        status_code = "failed"
        status_text = "Failed"
        badge_class = "feff-badge feff-badge-failed"

    # Duration
    ctime = node.ctime
    mtime = getattr(node, "mtime", None)
    if ctime is not None:
        end_time = mtime if (is_term and mtime) else datetime.datetime.now(datetime.timezone.utc)
        if ctime.tzinfo is not None and end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=datetime.timezone.utc)
        elif ctime.tzinfo is None and end_time.tzinfo is not None:
            end_time = end_time.replace(tzinfo=None)
        elapsed_sec = max(0, (end_time - ctime).total_seconds())
        duration_str = _format_duration(elapsed_sec)
    else:
        duration_str = "—"

    n_failed = None
    failed_node = getattr(node.outputs, "n_failed", None)
    if isinstance(failed_node, orm.Int):
        n_failed = failed_node.value

    return {
        "pk": node.pk,
        "ctime": ctime,
        "label": node.label or "—",
        "formula": formula,
        "absorber": absorber_text,
        "frames_sites": frames_sites,
        "status_code": status_code,
        "status_text": status_text,
        "badge_class": badge_class,
        "duration_str": duration_str,
        "n_failed": n_failed,
        "node": node,
    }


def _build_unified_table_rows(
    records: list[dict],
    on_select: Callable[[int], None],
    on_open: Callable[[object], None] | None = None,
) -> tuple:
    """Build selectable table rows with aligned headers, action buttons, and hover tooltips."""
    cols = [
        ("", "28px"),
        ("Action", "68px"),
        ("Label", "140px"),
        ("Material", "85px"),
        ("Absorber", "105px"),
        ("Frames×sites", "90px"),
        ("Status", "110px"),
        ("Started", "120px"),
        ("Duration", "75px"),
    ]

    header_cells = [
        ipw.HTML(
            f"<div style='font-size:12px;font-weight:600;color:var(--feff-ink-muted,#52606D);'>{title}</div>",
            layout=ipw.Layout(width=w, min_width=w, max_width=w, overflow="hidden"),
        )
        for title, w in cols
    ]
    header = ipw.HBox(
        header_cells,
        layout=ipw.Layout(
            padding="6px 8px",
            border_bottom="2px solid var(--feff-rule,#D5DBE1)",
            align_items="center",
        ),
    )
    header.add_class("feff-table-header")

    if not records:
        return (
            header,
            ipw.HTML(
                "<div style='padding:12px;color:#888;'>No calculation runs match your filters.</div>"
            ),
        )

    rows = [header]
    for rec in records:
        badge_html = f"<span class='{rec['badge_class']}'>{html.escape(rec['status_text'])}</span>"
        date_str = rec["ctime"].strftime("%Y-%m-%d %H:%M") if rec["ctime"] else "—"

        inspect_btn = ipw.Button(
            description="",
            tooltip=f"Inspect details for Run #{rec['pk']} in sidebar",
            layout=ipw.Layout(width="24px", height="24px", padding="0", margin="0 4px 0 0"),
            icon="chevron-right",
        )
        inspect_btn.add_class("feff-btn-secondary")
        inspect_btn.on_click(lambda _, pk=rec["pk"]: on_select(pk))

        open_btn = ipw.Button(
            description="Open",
            icon="folder-open",
            tooltip=f"Load results for Run #{rec['pk']}",
            layout=ipw.Layout(width="64px", height="24px", padding="0 2px", margin="0 4px 0 0"),
        )
        open_btn.add_class("feff-btn-secondary")
        if on_open is not None:
            open_btn.on_click(
                lambda _, node=rec["node"], pk=rec["pk"]: (on_select(pk), on_open(node))
            )
        else:
            open_btn.on_click(lambda _, pk=rec["pk"]: on_select(pk))

        cells = [
            _cell(rec["label"], "140px", bold=True),
            _cell(rec["formula"], "85px"),
            _cell(rec["absorber"], "105px"),
            _cell(rec["frames_sites"], "90px", align="right"),
            ipw.HTML(
                badge_html,
                layout=ipw.Layout(
                    width="110px", min_width="110px", max_width="110px", overflow="hidden"
                ),
            ),
            _cell(date_str, "120px"),
            _cell(rec["duration_str"], "75px", align="right"),
        ]

        full_cells = [inspect_btn, open_btn, *cells]
        row_box = ipw.HBox(
            full_cells,
            layout=ipw.Layout(
                padding="4px 8px",
                border_bottom="1px solid var(--feff-rule-light, #E4E7EB)",
                align_items="center",
            ),
        )
        rows.append(row_box)

    return tuple(rows)


def _cell(text: str, width: str, bold: bool = False, align: str = "left") -> ipw.HTML:
    """Return an escaped, ellipsized cell HTML widget with hover tooltip."""
    escaped = html.escape(str(text))
    weight = "600" if bold else "normal"
    return ipw.HTML(
        f"<div title='{escaped}' style='box-sizing:border-box;max-width:100%;width:{width};"
        f"overflow:hidden;text-overflow:ellipsis;white-space:nowrap;"
        f"font-size:12.5px;font-weight:{weight};text-align:{align};font-variant-numeric:tabular-nums;'>"
        f"{escaped}</div>",
        layout=ipw.Layout(width=width, min_width=width, max_width=width, overflow="hidden"),
    )


# Backward compatibility aliases
RunsWidget = ResultsLibraryWidget
_table_cell = _cell


def _is_usable_workflow(node: object) -> bool:
    """Return True if node is an EnsembleExafsWorkChain with available results."""
    if not isinstance(node, WorkChainNode):
        return False
    if node.process_label != WORKCHAIN_LABEL:
        return False
    if node.is_finished_ok:
        return True
    return bool(node.is_finished and hasattr(node.outputs, "averaged_xas"))


def _summarize_workflow(node: WorkChainNode) -> dict:
    """Extract display metadata from a completed FEFF ensemble workflow."""
    rec = _summarize_workflow_unified(node)
    return {
        "pk": rec["pk"],
        "ctime": rec["ctime"],
        "label": rec["label"],
        "formula": rec["formula"],
        "absorber": rec["absorber"],
        "n_structures": rec["frames_sites"],
        "n_failed": rec["n_failed"],
    }
