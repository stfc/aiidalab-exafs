"""Browsable library of completed FEFF ensemble workflows."""

from __future__ import annotations

import datetime
import html
from collections.abc import Callable

import ipywidgets as ipw
from aiida import orm
from aiida.orm import QueryBuilder, StructureData, WorkChainNode, load_node
from alc_aiidalab_widgets.widgets.status import Status


class ResultsLibraryWidget(ipw.VBox):
    """Find, inspect, and open successful FEFF ensemble results."""

    def __init__(self, on_open: Callable[[WorkChainNode], None]):
        self.on_open = on_open
        self._records: dict[int, dict] = {}
        self._selected_pk: int | None = None

        self.header = ipw.HTML("<h2>Previous FEFF results</h2>")
        self.description = ipw.HTML(
            "Find completed calculations by material, absorber, or date, then inspect them before opening."
        )
        default_start = datetime.date.today() - datetime.timedelta(days=30)
        self.start_date = ipw.Text(
            value=default_start.isoformat(), description="From:", layout={"width": "190px"}
        )
        self.end_date = ipw.Text(
            value=datetime.date.today().isoformat(), description="To:", layout={"width": "190px"}
        )
        self.material_filter = ipw.Text(
            placeholder="e.g. Fe2O3 or sample label",
            description="Material:",
            layout={"width": "300px"},
        )
        self.absorber_filter = ipw.Text(
            placeholder="e.g. Fe",
            description="Absorber:",
            layout={"width": "190px"},
        )
        self.search_button = ipw.Button(description="Search", button_style="info", icon="search")
        self.search_button.on_click(self._search)

        self.results_table = ipw.VBox(
            layout={
                "width": "700px",
                "max_height": "360px",
                "overflow_y": "auto",
                "border": "1px solid #ddd",
            }
        )
        self.preview = ipw.HTML("<em>Select a result to view its details.</em>")
        self.open_button = ipw.Button(
            description="Open results",
            button_style="success",
            icon="bar-chart",
            disabled=True,
        )
        self.open_button.on_click(self._open_selected)
        self.pk_input = ipw.Text(placeholder="Process PK", description="Load PK:", layout={"width": "210px"})
        self.load_pk_button = ipw.Button(description="Load", icon="refresh")
        self.load_pk_button.on_click(self._load_pk)
        self.status = Status()

        advanced = ipw.Accordion(children=[ipw.HBox([self.pk_input, self.load_pk_button])])
        advanced.set_title(0, "Advanced: load a known process PK")
        advanced.selected_index = None

        filters = ipw.VBox(
            [
                ipw.HBox([self.start_date, self.end_date, self.search_button]),
                ipw.HBox([self.material_filter, self.absorber_filter]),
            ],
            layout={"padding": "0.75em", "border": "1px solid #ddd"},
        )
        super().__init__(
            [
                self.header,
                self.description,
                filters,
                ipw.HBox(
                    [
                        self.results_table,
                        ipw.VBox([self.preview, self.open_button], layout={"width": "300px"}),
                    ],
                    layout={"align_items": "flex-start"},
                ),
                advanced,
                self.status,
            ]
        )
        self._search()

    def _search(self, _=None):
        """Search and summarize successful ensemble workflows."""
        try:
            start_date = datetime.datetime.strptime(self.start_date.value, "%Y-%m-%d")
            end_date = datetime.datetime.strptime(self.end_date.value, "%Y-%m-%d") + datetime.timedelta(
                days=1
            )
        except ValueError:
            self.status.failure("Use dates in YYYY-MM-DD format.")
            return
        if start_date >= end_date:
            self.status.failure("The end date must be after the start date.")
            return

        query = QueryBuilder()
        query.append(
            WorkChainNode,
            filters={"ctime": {">=": start_date, "<": end_date}},
            tag="workflow",
        )
        material = self.material_filter.value.strip().lower()
        absorber = self.absorber_filter.value.strip().lower()
        records = []
        for node in query.all(flat=True):
            if node.process_label != "EnsembleExafsWorkChain" or not node.is_finished_ok:
                continue
            record = _summarize_workflow(node)
            searchable = f"{record['formula']} {record['label']}".lower()
            if material and material not in searchable:
                continue
            if absorber and absorber not in record["absorber"].lower():
                continue
            records.append(record)

        records.sort(key=lambda record: record["ctime"], reverse=True)
        self._records = {record["pk"]: record for record in records}
        self._selected_pk = None
        self.results_table.children = _build_table_rows(records, self._select_record)
        self.preview.value = "<em>Select a result to view its details.</em>"
        self.open_button.disabled = True
        self.status.value = f"Found {len(records)} successful FEFF workflow(s)."

    def _select_record(self, pk: int):
        """Render the selected workflow's metadata preview."""
        self._selected_pk = pk
        record = self._records.get(pk)
        self.open_button.disabled = record is None
        if record is None:
            self.preview.value = "<em>Select a result to view its details.</em>"
            return
        failed = record["n_failed"]
        failed_text = "Not recorded" if failed is None else str(failed)
        self.preview.value = (
            "<h3>Calculation details</h3>"
            "<dl>"
            f"<dt>Material</dt><dd>{html.escape(record['formula'])}</dd>"
            f"<dt>Absorber</dt><dd>{html.escape(record['absorber'])}</dd>"
            f"<dt>Structures</dt><dd>{record['n_structures']}</dd>"
            f"<dt>Completed workflow</dt><dd>PK {record['pk']}</dd>"
            f"<dt>Created</dt><dd>{record['ctime']:%Y-%m-%d %H:%M}</dd>"
            f"<dt>Failed snapshots</dt><dd>{failed_text}</dd>"
            f"<dt>Label</dt><dd>{html.escape(record['label'] or '—')}</dd>"
            "</dl>"
        )

    def _open_selected(self, _):
        """Open the selected workflow in the results view."""
        pk = self._selected_pk
        if pk is None:
            return
        node = load_node(pk)
        if isinstance(node, WorkChainNode) and node.is_finished_ok:
            self.on_open(node)

    def _load_pk(self, _):
        """Load a known successful FEFF workflow as an advanced fallback."""
        try:
            node = load_node(int(self.pk_input.value))
        except Exception:  # noqa: BLE001
            self.status.failure("No process was found for that PK.")
            return
        if not isinstance(node, WorkChainNode) or node.process_label != "EnsembleExafsWorkChain":
            self.status.failure("That PK is not a FEFF ensemble workflow.")
            return
        if not node.is_finished_ok:
            self.status.failure("That FEFF workflow did not finish successfully.")
            return
        self.on_open(node)


def _summarize_workflow(node: WorkChainNode) -> dict:
    """Extract display metadata from a completed FEFF ensemble workflow."""
    parameters_node = getattr(node.inputs, "parameters", None)
    parameters = parameters_node.get_dict() if isinstance(parameters_node, orm.Dict) else {}
    structures_namespace = getattr(node.inputs, "structures", None)
    structures = (
        [getattr(structures_namespace, key) for key in structures_namespace]
        if structures_namespace is not None
        else []
    )
    structure = structures[0] if structures else None
    formula = "Unknown material"
    absorber = f"Unknown {str(parameters.get('edge', '')).upper()}-edge".strip()
    if isinstance(structure, StructureData):
        formula = structure.get_formula(mode="hill")
        atoms = parameters.get("absorbing_atoms", [])
        if isinstance(atoms, int):
            atoms = [atoms]
        elements = sorted(
            {
                _site_element(structure, index)
                for index in atoms
                if isinstance(index, int) and 0 <= index < len(structure.sites)
            }
            - {""}
        )
        edge = str(parameters.get("edge", "")).upper()
        absorber = f"{'/'.join(elements) or 'Unknown'} {edge}-edge"
        if atoms:
            absorber += f" (sites {', '.join(str(index) for index in atoms)})"
    n_failed = None
    failed_node = getattr(node.outputs, "n_failed", None)
    if isinstance(failed_node, orm.Int):
        n_failed = failed_node.value
    return {
        "pk": node.pk,
        "ctime": node.ctime,
        "label": node.label,
        "formula": formula,
        "absorber": absorber,
        "n_structures": len(structures),
        "n_failed": n_failed,
    }


def _build_table_rows(records: list[dict], on_select: Callable[[int], None]) -> tuple:
    """Build column-aligned, selectable rows for the results browser."""
    columns = [
        ("Material", "120px"),
        ("Absorber / edge", "200px"),
        ("Structures", "85px"),
        ("Completed", "105px"),
        ("Label", "120px"),
        ("", "65px"),
    ]
    header = ipw.HBox(
        [
            ipw.HTML(f"<strong>{title}</strong>", layout={"width": width})
            for title, width in columns
        ],
        layout={"padding": "4px 8px", "border_bottom": "1px solid #ddd"},
    )
    if not records:
        return (header, ipw.HTML("<em>No matching successful workflows.</em>"))

    rows = [header]
    for record in records:
        button = ipw.Button(
            description="View",
            icon="info-circle",
            layout={"width": "65px"},
        )
        button.on_click(lambda _, pk=record["pk"]: on_select(pk))
        rows.append(
            ipw.HBox(
                [
                    _table_cell(record["formula"], "120px"),
                    _table_cell(record["absorber"], "200px"),
                    _table_cell(str(record["n_structures"]), "85px"),
                    _table_cell(record["ctime"].strftime("%Y-%m-%d"), "105px"),
                    _table_cell(record["label"] or "—", "120px"),
                    button,
                ],
                layout={
                    "padding": "3px 8px",
                    "border_bottom": "1px solid #eee",
                    "align_items": "center",
                },
            )
        )
    return tuple(rows)


def _table_cell(value: str, width: str) -> ipw.HTML:
    """Return an escaped, clipped table cell."""
    escaped_value = html.escape(value)
    return ipw.HTML(
        (
            f'<span title="{escaped_value}" '
            'style="display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">'
            f"{escaped_value}</span>"
        ),
        layout={"width": width},
    )


def _site_element(structure: StructureData, index: int) -> str:
    """Return the first chemical symbol for a structure site, if available."""
    kind = structure.get_kind(structure.sites[index].kind_name)
    return str(kind.symbols[0]) if kind.symbols else ""
