"""Widgets for importing and selecting experimental XAS spectra."""

from __future__ import annotations

from io import BytesIO

import ipywidgets as ipw
from aiida import orm
from aiida_feff.calcfunctions.experimental import (
    import_experimental_spectrum,
    list_experimental_groups,
)
from aiida_feff.data.xasdata import XasData
from alc_aiidalab_widgets.widgets.file_handling import FileUploadWidget
from alc_aiidalab_widgets.widgets.file_viewer import SinglefileDataViewer
from alc_aiidalab_widgets.widgets.status import Status

from aiidalab_feff.common.database import ProjectedQueryWidget
from aiidalab_feff.models import ResultsModel


class ExperimentalXasDatabaseQueryWidget(ProjectedQueryWidget):
    """Database selector that exposes only Larch-imported experimental XAS.

    The import adapter tags nodes with ``source_kind``, on either the attributes
    or the extras depending on when they were written. Selecting on that in SQL
    keeps the scan proportional to the handful of experimental spectra rather
    than to every XasData in the range.
    """

    extra_filters = {
        "or": [
            {"attributes.source_kind": "experimental"},
            {"extras.source_kind": "experimental"},
        ]
    }


class ExperimentalSpectrumWidget(ipw.VBox):
    """Store Larch-readable experimental data and select it for comparison."""

    def __init__(self, results_model: ResultsModel):
        """Initialize the experimental spectrum upload and selection widget."""
        self.results_model = results_model
        self.source: orm.SinglefileData | None = None
        self.file_upload_widget = FileUploadWidget(description="Spectrum:")
        self.file_upload_widget.file_upload.accept = ".prj,.ath,.athena,.xdi,.csv,.dat,.txt"
        self.file_upload = self.file_upload_widget.file_upload
        self.file_upload_widget.observe(self._on_file_uploaded, names="file")

        self.data_kind = ipw.Dropdown(
            options=[
                ("Auto-detect with Larch", "auto"),
                ("χ(k): k, χ columns", "chi"),
                ("μ(E): energy, μ columns", "mu"),
                ("Specify column labels", "custom"),
            ],
            value="auto",
            description="Columns:",
            style={"description_width": "initial"},
        )
        self.data_kind.observe(self._on_data_kind_change, names="value")
        self.column_labels = ipw.Text(
            value="",
            placeholder="e.g. k,chi or energy,mu[,mu0]",
            description="Column labels:",
            disabled=True,
            style={"description_width": "initial"},
            layout={"width": "320px"},
        )
        self.group = ipw.Dropdown(
            options=[("Default spectrum", "")],
            description="Athena group:",
            disabled=True,
            style={"description_width": "initial"},
        )
        self.import_button = ipw.Button(
            description="Store experimental spectrum",
            icon="database",
            disabled=True,
        )
        self.import_button.on_click(self._on_import)
        self.clear_button = ipw.Button(
            description="Clear reference",
            icon="times",
            tooltip="Clear loaded experimental reference spectrum",
            layout=ipw.Layout(width="auto", min_width="120px"),
        )
        self.clear_button.add_class("feff-btn-secondary")
        self.clear_button.on_click(self._on_clear)

        self.database_query = ExperimentalXasDatabaseQueryWidget(
            title="Select a stored experimental spectrum",
            query=[XasData],
        )
        self.database_query.observe(self._on_database_select, names="data_object")
        self.status = Status()

        self.file_preview_accordion = ipw.Accordion(children=[ipw.HTML("<em>No file loaded</em>")])
        self.file_preview_accordion.set_title(0, "Raw file content preview")
        self.file_preview_accordion.selected_index = None

        super().__init__(
            [
                ipw.HTML(
                    "<p>Upload a file readable by Larch, including Athena projects, "
                    "or select a previously imported experimental spectrum.</p>"
                ),
                self.file_upload_widget,
                self.file_preview_accordion,
                ipw.HBox([self.data_kind, self.column_labels]),
                ipw.HBox([self.group, self.import_button, self.clear_button]),
                self.status,
                self.database_query,
            ]
        )

    def _update_file_preview(self, node: orm.SinglefileData):
        try:
            viewer = SinglefileDataViewer(node)
            self.file_preview_accordion.children = [viewer]
            self.file_preview_accordion.set_title(0, f"Raw file preview ({node.filename})")
        except Exception:
            pass

    def _on_file_uploaded(self, change):
        file_node = change["new"]
        if file_node is None:
            return
        filename = self.file_upload_widget.filename()
        content_io = self.file_upload_widget.get_file_contents()
        if content_io is None:
            return
        self.source = orm.SinglefileData(file=content_io, filename=filename)
        self.source.label = f"Experimental source: {filename}"
        self.source.store()
        self.import_button.disabled = False
        self._update_file_preview(self.source)
        try:
            groups = list_experimental_groups(self.source)
        except Exception as exc:  # noqa: BLE001
            self.group.options = [("Default spectrum", "")]
            self.group.disabled = True
            self.status.warning(
                f"Stored source file {filename}. Athena groups could not be read: {exc}"
            )
            return
        if groups:
            self.group.options = [(name, name) for name in groups]
            self.group.disabled = False
            self.status.success(f"Stored {filename}; select an Athena group to import.")
        else:
            self.group.options = [("Default spectrum", "")]
            self.group.disabled = True
            self.status.success(f"Stored source file {filename}; ready to import with Larch.")

    def _on_upload(self, change):
        if not change["new"]:
            return
        file_info = _uploaded_file(change["new"])
        filename = file_info["name"]
        self.source = orm.SinglefileData(
            file=BytesIO(bytes(file_info["content"])), filename=filename
        )
        self.source.label = f"Experimental source: {filename}"
        self.source.store()
        self.import_button.disabled = False
        self._update_file_preview(self.source)
        try:
            groups = list_experimental_groups(self.source)
        except Exception as exc:  # noqa: BLE001
            self.group.options = [("Default spectrum", "")]
            self.group.disabled = True
            self.status.warning(
                f"Stored source file {filename}. Athena groups could not be read: {exc}"
            )
            return
        if groups:
            self.group.options = [(name, name) for name in groups]
            self.group.disabled = False
            self.status.success(f"Stored {filename}; select an Athena group to import.")
        else:
            self.group.options = [("Default spectrum", "")]
            self.group.disabled = True
            self.status.success(f"Stored source file {filename}; ready to import with Larch.")

    def _on_data_kind_change(self, change):
        """Enable explicit labels only when the user selects that import mode."""
        self.column_labels.disabled = change["new"] != "custom"

    def _on_import(self, _):
        if self.source is None:
            return
        labels = {"chi": ["k", "chi"], "mu": ["energy", "mu"]}.get(self.data_kind.value)
        if self.data_kind.value == "custom":
            labels = [
                label.strip() for label in self.column_labels.value.split(",") if label.strip()
            ]
            if not labels:
                self.status.value = (
                    "<span style='color: red'>Specify comma-separated column labels.</span>"
                )
                return
        parameters = {"autobk": True, "group": self.group.value}
        if labels:
            parameters["labels"] = labels
        try:
            spectrum = import_experimental_spectrum(self.source, orm.Dict(dict=parameters))
            spectrum.label = f"Experimental: {self.source.filename}"
            self.results_model.experimental_xas = spectrum
            self.status.value = (
                f"Imported experimental spectrum PK {spectrum.pk} from {self.source.filename}."
            )
        except Exception as exc:  # noqa: BLE001
            self.results_model.experimental_xas = None
            self.status.value = f"<span style='color: red'>Import failed: {exc}</span>"

    def _on_database_select(self, change):
        spectrum = change["new"]
        if not spectrum:
            return
        if not isinstance(spectrum, XasData):
            self.status.failure("Selected node is not an XAS spectrum.")
            return
        self.results_model.experimental_xas = spectrum
        self.status.success(f"Selected stored experimental spectrum PK {spectrum.pk}.")

    def _on_clear(self, _):
        """Clear active experimental reference spectrum."""
        self.results_model.experimental_xas = None
        self.status.value = "Cleared experimental reference."
        self.database_query.results.value = False

    def reset(self):
        """Reset experimental spectrum selection and file upload state."""
        self.source = None
        self.file_upload.value = () if isinstance(self.file_upload.value, tuple) else {}
        self.file_upload_widget.file = None
        self.file_upload_widget.file_handle.value = ""
        self.file_preview_accordion.children = [ipw.HTML("<em>No file loaded</em>")]
        self.file_preview_accordion.set_title(0, "Raw file content preview")
        self.file_preview_accordion.selected_index = None
        self.data_kind.value = "auto"
        self.column_labels.value = ""
        self.group.options = [("Default spectrum", "")]
        self.group.disabled = True
        self.import_button.disabled = True
        self.status.clear()
        self.database_query.results.value = False


def _uploaded_file(value):
    """Return one upload record across ipywidgets 7 and 8 formats."""
    if isinstance(value, tuple):
        return value[0]
    filename = next(iter(value))
    return {"name": filename, "content": value[filename]["content"]}
