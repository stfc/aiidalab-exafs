"""Structure input step for the AiiDAlab FEFF app."""

from __future__ import annotations

from html import escape

import ipywidgets as ipw
from aiida.orm import StructureData, TrajectoryData
from alc_aiidalab_widgets.widgets.status import Status
from alc_aiidalab_widgets.widgets.structure import StructureViewWidget

from aiidalab_feff.absorber import AbsorberSelectorWidget
from aiidalab_feff.common.database import ProjectedQueryWidget
from aiidalab_feff.common.file_handling import (
    build_step_indices,
    read_cif_xyz_to_structure_data,
    read_file_list_to_structures,
    read_xyz_to_trajectory_data,
)
from aiidalab_feff.common.lazy import LazyWidget
from aiidalab_feff.models import InputModel
from aiidalab_feff.utils import validate_trajectory_size


class StructureInputWidget(ipw.VBox):
    """Single-structure upload / builder."""

    def __init__(self, model: InputModel):
        """Create the single-structure input widget."""
        self.model = model

        self.file_upload = ipw.FileUpload(
            multiple=False,
            description="Upload Structure File",
            button_style="primary",
        )
        self.file_upload.observe(self._on_upload, names="value")

        self.status = Status()
        self.viewer = StructureViewWidget()

        super().__init__(
            [
                ipw.HTML("<h3>Upload a single structure</h3>"),
                self.file_upload,
                self.status,
                self.viewer,
            ]
        )

    def _on_upload(self, change):
        if not change["new"]:
            return
        # Handle both ipywidgets 8 (tuple of dicts) and ipywidgets 7 (dict)
        if isinstance(change["new"], tuple):
            file_info = change["new"][0]
            content = bytes(file_info["content"])
            filename = file_info["name"]
        else:
            filename = next(iter(change["new"].keys()))
            content = bytes(change["new"][filename]["content"])
        try:
            structure = read_cif_xyz_to_structure_data(content, filename)
            self.model.structure = structure
            self.viewer.assign_structure_from_structuredata(structure)
            self.status.success(f"Loaded {filename} ({len(structure.sites)} atoms).")
        except Exception as exc:  # noqa: BLE001
            self.status.value = _upload_error_message(filename, "structure", exc)
            self.model.structure = None

    def reset(self):
        self.file_upload.value = () if isinstance(self.file_upload.value, tuple) else {}
        self.status.clear()
        self.model.structure = None
        self.viewer.children = [self.viewer.message]


def _ordinal(n: int) -> str:
    """Return the ordinal suffix for an integer (e.g. 1st, 2nd, 3rd, 10th)."""
    if 11 <= (n % 100) <= 13:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


class TrajectoryInputWidget(ipw.VBox):
    """Trajectory upload with stride / index sampling."""

    def __init__(self, model: InputModel):
        self.model = model
        self.filename = ""

        self.file_upload = ipw.FileUpload(
            multiple=False,
            description="Upload Trajectory File",
            button_style="primary",
        )
        self.file_upload.observe(self._on_upload, names="value")

        self.subsample_mode = ipw.ToggleButtons(
            options=[("Every Nth frame", "stride"), ("Custom index range", "custom")],
            value="stride",
            description="Frames to use:",
            style={"description_width": "initial", "button_width": "auto"},
            layout={"margin": "6px 0 4px 0"},
        )
        self.subsample_mode.observe(self._on_subsample_mode_change, names="value")

        self.stride = ipw.IntSlider(
            value=10,
            min=1,
            max=100,
            step=1,
            description="Stride:",
            continuous_update=False,
            style={"description_width": "initial"},
            layout={"width": "320px"},
        )
        self.stride.observe(self._on_stride_change, names="value")

        self.indices_text = ipw.Text(
            value="",
            placeholder="e.g. 0:100:10 or 0, 10, 20, 30",
            description="Indices:",
            style={"description_width": "initial"},
            layout={"width": "340px", "display": "none"},
        )
        self.indices_text.observe(self._on_indices_change, names="value")

        self.decorrelation_note = ipw.HTML(
            "<div style='font-size:12px;color:var(--feff-ink-muted, #52606D);margin-top:2px;'>"
            "Subsampling MD frames avoids calculating statistically correlated configurations and saves compute time."
            "</div>"
        )

        self.frame_count = ipw.HTML()
        self.status = Status()
        self.viewer = StructureViewWidget()

        sampling_box = ipw.VBox(
            [
                self.subsample_mode,
                ipw.HBox([self.stride, self.indices_text]),
                self.decorrelation_note,
            ],
            layout=ipw.Layout(margin="4px 0 8px 0"),
        )

        super().__init__(
            [
                ipw.HTML("<h3>Upload an MD trajectory</h3>"),
                self.file_upload,
                sampling_box,
                self.frame_count,
                self.status,
                self.viewer,
            ]
        )

    def _on_subsample_mode_change(self, change):
        if change["new"] == "stride":
            self.stride.layout.display = "block"
            self.indices_text.layout.display = "none"
            self._update_indices()
        else:
            self.stride.layout.display = "none"
            self.indices_text.layout.display = "block"
            if self.indices_text.value.strip():
                self._update_indices_from_text(self.indices_text.value)

    def _on_upload(self, change):
        if not change["new"]:
            return
        # Handle both ipywidgets 8 (tuple of dicts) and ipywidgets 7 (dict)
        if isinstance(change["new"], tuple):
            file_info = change["new"][0]
            content = bytes(file_info["content"])
            filename = file_info["name"]
        else:
            filename = next(iter(change["new"].keys()))
            content = bytes(change["new"][filename]["content"])
        self.filename = filename
        try:
            trajectory = read_xyz_to_trajectory_data(content, filename)
            validate_trajectory_size(trajectory)
            self.model.trajectory = trajectory
            self.viewer.assign_structure_from_trajectorydata(trajectory)
            self._update_indices()
            self.status.clear()
        except Exception as exc:  # noqa: BLE001
            self.status.value = _upload_error_message(filename, "trajectory", exc)
            self.model.trajectory = None
            self.model.selected_indices = None
            self.model.structures = {}
            self.frame_count.value = ""

    def _on_stride_change(self, change):
        if self.subsample_mode.value == "stride":
            self.indices_text.value = ""
            self._update_indices()

    def _on_indices_change(self, change):
        if self.subsample_mode.value == "custom" and change["new"].strip():
            self._update_indices_from_text(change["new"])

    def _update_indices(self):
        trajectory = self.model.trajectory
        if trajectory is None:
            self.frame_count.value = ""
            return False
        if not isinstance(trajectory, TrajectoryData):
            self.status.value = (
                "<span style='color: red'>Error: uploaded object is not a trajectory.</span>"
            )
            return False
        step_ids = list(trajectory.get_stepids())
        if not step_ids:
            step_ids = list(range(len(trajectory.get_array("positions"))))
        total_frames = len(step_ids)
        self.stride.max = max(100, total_frames)
        stride_val = self.stride.value
        indices = build_step_indices(total_frames, stride_val)
        self.model.selected_indices = [step_ids[i] for i in indices]
        self.model.structures = {}
        using_count = len(self.model.selected_indices)

        stride_text = (
            "every frame" if stride_val == 1 else f"every {stride_val}{_ordinal(stride_val)}"
        )
        file_part = f"<strong>{self.filename}</strong> · " if self.filename else ""
        self.frame_count.value = (
            f"<div style='font-size:13px;color:var(--feff-ink, #222);margin:4px 0;'>"
            f"{file_part}{total_frames} frames · using <strong>{using_count}</strong> ({stride_text})"
            f"</div>"
        )
        return True

    def _update_indices_from_text(self, text: str):
        if self.model.trajectory is None:
            return
        try:
            indices = _parse_indices(text)
            self.model.selected_indices = indices
            self.model.structures = {}
            step_ids = list(self.model.trajectory.get_stepids()) or list(
                range(len(self.model.trajectory.get_array("positions")))
            )
            total_frames = len(step_ids)
            file_part = f"<strong>{self.filename}</strong> · " if self.filename else ""
            self.frame_count.value = (
                f"<div style='font-size:13px;color:var(--feff-ink, #222);margin:4px 0;'>"
                f"{file_part}{total_frames} frames · using <strong>{len(indices)}</strong> (custom range)"
                f"</div>"
            )
            self.status.clear()
        except Exception as exc:  # noqa: BLE001
            self.status.value = f"<span style='color: red'>Invalid indices: {exc}</span>"

    def reset(self):
        self.file_upload.value = () if isinstance(self.file_upload.value, tuple) else {}
        self.indices_text.value = ""
        self.frame_count.value = ""
        self.filename = ""
        self.status.clear()
        self.subsample_mode.value = "stride"
        self.stride.layout.display = "block"
        self.indices_text.layout.display = "none"
        self.viewer.children = [self.viewer.message]
        self.stride.unobserve(self._on_stride_change, names="value")
        self.stride.value = 10
        self.stride.observe(self._on_stride_change, names="value")
        self.model.trajectory = None
        self.model.selected_indices = None
        self.model.structures = {}


class FileListInputWidget(ipw.VBox):
    """Upload multiple CIF/XYZ files as an ensemble."""

    def __init__(self, model: InputModel):
        self.model = model

        self.file_upload = ipw.FileUpload(
            accept=".cif,.xyz",
            multiple=True,
            description="Upload CIF/XYZ files",
            button_style="primary",
        )
        self.file_upload.observe(self._on_upload, names="value")
        self.frame_count = ipw.HTML()
        self.status = Status()

        super().__init__(
            [
                ipw.HTML("<h3>Upload multiple structures</h3>"),
                self.file_upload,
                self.frame_count,
                self.status,
            ]
        )

    def _on_upload(self, change):
        if not change["new"]:
            return
        # Handle both ipywidgets 8 (tuple of dicts) and ipywidgets 7 (dict)
        if isinstance(change["new"], tuple):
            files = [
                (file_info["name"], bytes(file_info["content"])) for file_info in change["new"]
            ]
        else:
            files = [(name, bytes(info["content"])) for name, info in change["new"].items()]
        try:
            structures = read_file_list_to_structures(files)
            self.model.structures = structures
            self.frame_count.value = f"Loaded {len(structures)} structures."
            self.status.success(f"Loaded {len(structures)} structures.")
        except Exception as exc:  # noqa: BLE001
            self.status.value = _upload_error_message("selected files", "structure", exc)
            self.model.structures = {}

    def reset(self):
        self.file_upload.value = () if isinstance(self.file_upload.value, tuple) else {}
        self.frame_count.value = ""
        self.status.clear()
        self.model.structures = {}


class DatabaseInputWidget(ipw.VBox):
    """Select a stored structure or trajectory from the AiiDA database."""

    def __init__(self, model: InputModel):
        self.model = model
        self.node_type_selector = ipw.RadioButtons(
            options=[
                ("Structures and trajectories", "both"),
                ("Single structures", "structure"),
                ("Trajectories", "trajectory"),
            ],
            value="both",
            description="Search for:",
            style={"description_width": "initial"},
        )
        self.node_type_selector.observe(self._on_node_type_change, names="value")
        self.database_query = ProjectedQueryWidget(
            title="Select an AiiDA structure or trajectory",
            query=[StructureData, TrajectoryData],
        )
        self.database_query.observe(self._on_node_change, names="data_object")

        self.stride = ipw.IntSlider(
            value=10,
            min=1,
            max=100,
            step=1,
            description="Stride:",
            continuous_update=False,
            disabled=True,
            style={"description_width": "initial"},
            layout={"width": "300px"},
        )
        self.stride.observe(self._on_stride_change, names="value")
        self.indices_text = ipw.Text(
            value="",
            placeholder="e.g. 0:100:10 or 0, 10, 20, 30",
            description="Indices:",
            style={"description_width": "initial"},
            layout={"width": "300px"},
            disabled=True,
        )
        self.indices_text.observe(self._on_indices_change, names="value")
        self.frame_count = ipw.HTML()
        self.status = Status()
        self.viewer = StructureViewWidget()

        super().__init__(
            [
                ipw.HTML("<h3>Use a stored structure or trajectory</h3>"),
                self.node_type_selector,
                self.database_query,
                ipw.HBox([self.stride, self.indices_text]),
                self.frame_count,
                self.status,
                self.viewer,
            ]
        )

    def _on_node_type_change(self, change):
        query_types = {
            "both": (StructureData, TrajectoryData),
            "structure": (StructureData,),
            "trajectory": (TrajectoryData,),
        }
        self.database_query.results.value = False
        self.database_query.query_type = query_types[change["new"]]
        self.database_query.search()
        self._clear_selected_input()

    def _on_node_change(self, change):
        node = change["new"]
        if node is None:
            return
        try:
            if isinstance(node, StructureData):
                self.model.structure = node
                self.model.trajectory = None
                self.model.selected_indices = None
                self.model.structures = {}
                self._set_trajectory_controls_enabled(False)
                self.frame_count.value = "Selected frames: 1"
                self.viewer.assign_structure_from_structuredata(node)
                self.status.success(f"Selected stored structure PK {node.pk}.")
            elif isinstance(node, TrajectoryData):
                validate_trajectory_size(node)
                self.model.structure = None
                self.model.trajectory = node
                self._set_trajectory_controls_enabled(True)
                self._update_indices()
                self.viewer.assign_structure_from_trajectorydata(node)
                self.status.success(f"Selected stored trajectory PK {node.pk}.")
            else:
                self.status.failure("Selected node is not a structure or trajectory.")
        except Exception as exc:  # noqa: BLE001
            self.status.failure(f"Error: {exc}")
            self.model.structure = None
            self.model.trajectory = None
            self.model.selected_indices = None
            self.model.structures = {}

    def _set_trajectory_controls_enabled(self, enabled: bool):
        self.stride.disabled = not enabled
        self.indices_text.disabled = not enabled

    def _clear_selected_input(self):
        self._set_trajectory_controls_enabled(False)
        self.frame_count.value = ""
        self.status.clear()
        self.viewer.children = [self.viewer.message]
        self.model.structure = None
        self.model.trajectory = None
        self.model.selected_indices = None
        self.model.structures = {}

    def _on_stride_change(self, _):
        if self.model.trajectory is None:
            return
        self.indices_text.value = ""
        self._update_indices()

    def _on_indices_change(self, change):
        if change["new"].strip():
            self._update_indices_from_text(change["new"])

    def _update_indices(self):
        trajectory = self.model.trajectory
        if trajectory is None:
            self.frame_count.value = ""
            return False
        if not isinstance(trajectory, TrajectoryData):
            self.status.value = (
                "<span style='color: red'>Error: selected object is not a trajectory.</span>"
            )
            return False
        step_ids = list(trajectory.get_stepids())
        if not step_ids:
            step_ids = list(range(len(trajectory.get_array("positions"))))
        total_frames = len(step_ids)
        self.stride.max = max(100, total_frames)
        indices = build_step_indices(total_frames, self.stride.value)
        self.model.selected_indices = [step_ids[i] for i in indices]
        self.model.structures = {}
        using_count = len(self.model.selected_indices)
        stride_val = self.stride.value
        stride_text = (
            "every frame" if stride_val == 1 else f"every {stride_val}{_ordinal(stride_val)}"
        )
        self.frame_count.value = (
            f"<div style='font-size:13px;color:var(--feff-ink, #222);margin:4px 0;'>"
            f"Stored trajectory PK {getattr(trajectory, 'pk', '')} · {total_frames} frames · using <strong>{using_count}</strong> ({stride_text})"
            f"</div>"
        )
        return True

    def _update_indices_from_text(self, text: str):
        if self.model.trajectory is None:
            return
        try:
            indices = _parse_indices(text)
            self.model.selected_indices = indices
            self.model.structures = {}
            step_ids = list(self.model.trajectory.get_stepids()) or list(
                range(len(self.model.trajectory.get_array("positions")))
            )
            total_frames = len(step_ids)
            self.frame_count.value = (
                f"<div style='font-size:13px;color:var(--feff-ink, #222);margin:4px 0;'>"
                f"Stored trajectory PK {getattr(self.model.trajectory, 'pk', '')} · {total_frames} frames · using <strong>{len(indices)}</strong> (custom range)"
                f"</div>"
            )
        except Exception as exc:  # noqa: BLE001
            self.status.value = f"<span style='color: red'>Invalid indices: {exc}</span>"

    def reset(self):
        self.database_query.results.value = False
        self.node_type_selector.value = "both"
        self.stride.unobserve(self._on_stride_change, names="value")
        self.stride.value = 1
        self.stride.observe(self._on_stride_change, names="value")
        self.indices_text.value = ""
        self._set_trajectory_controls_enabled(False)
        self._clear_selected_input()


class InputWidget(ipw.VBox):
    """Main input step widget combining single and ensemble sources."""

    TAB_STRUCTURE = 0
    TAB_TRAJECTORY = 1
    TAB_FILE_LIST = 2
    TAB_DATABASE = 3

    def __init__(self, model: InputModel):
        self.model = model

        self.structure_widget = StructureInputWidget(model)
        self.trajectory_widget = TrajectoryInputWidget(model)
        self.file_list_widget = FileListInputWidget(model)
        # Tab 3 is not the default tab, and DatabaseInputWidget queries the
        # database from its constructor (9 s of app startup), so it is built
        # the first time that tab is selected.
        self._database_lazy = LazyWidget(
            lambda: DatabaseInputWidget(model), placeholder="<em>Loading…</em>"
        )

        self.tabs = ipw.Tab(
            children=[
                self.structure_widget,
                self.trajectory_widget,
                self.file_list_widget,
                self._database_lazy,
            ]
        )
        self.tabs.set_title(self.TAB_STRUCTURE, "Single structure")
        self.tabs.set_title(self.TAB_TRAJECTORY, "MD trajectory")
        self.tabs.set_title(self.TAB_FILE_LIST, "File list")
        self.tabs.set_title(self.TAB_DATABASE, "AiiDA database")
        self.tabs.observe(self._on_tab_change, names="selected_index")

        self.absorber_selector = AbsorberSelectorWidget(model)

        self.status = Status()
        self.frame_count = ipw.HTML()
        self.cost_preview = ipw.HTML()

        super().__init__(
            [
                ipw.HTML("<h2>Input structures</h2>"),
                self.tabs,
                self.cost_preview,
                self.absorber_selector,
                self.status,
            ]
        )

        self.model.observe(self._on_model_structures, names="structures")
        self.model.observe(self._on_model_structures, names="structure")
        self.model.observe(self._on_model_structures, names="trajectory")
        self.model.observe(self._on_model_structures, names="selected_indices")
        self.model.observe(self._on_model_structures, names="absorbing_atoms")

    def _on_model_structures(self, _=None):
        self._update_cost_preview()

    def _update_cost_preview(self):
        n_absorbers = len(self.model.absorbing_atoms or [])
        is_md = self.model.trajectory is not None
        if is_md:
            selected_indices = self.model.selected_indices or []
            n_frames = len(selected_indices)
            noun = "frame" if n_frames == 1 else "frames"
        else:
            structures = self.model.get_structures() or {}
            n_frames = len(structures)
            noun = "structure" if n_frames == 1 else "structures"

        if n_frames > 0 and n_absorbers > 0:
            total_runs = n_frames * n_absorbers
            absorber_noun = "absorber" if n_absorbers == 1 else "absorbers"
            self.cost_preview.value = (
                f"<div class='feff-cost-callout'>"
                f"<strong>Scope:</strong> {n_frames} {noun} × {n_absorbers} {absorber_noun} = "
                f"<strong>{total_runs} FEFF runs</strong>"
                f"</div>"
            )
            self.frame_count.value = ""
        elif n_frames > 0:
            self.cost_preview.value = (
                f"<div style='font-size:12.5px;color:var(--feff-ink-muted, #666);margin:6px 0;'>"
                f"{n_frames} {noun} ready · select absorbing atoms below to calculate run count"
                f"</div>"
            )
            self.frame_count.value = ""
        else:
            self.cost_preview.value = ""
            self.frame_count.value = ""

    @property
    def database_widget(self):
        """The AiiDA-database input tab, constructed on first access."""
        return self._database_lazy.build()

    def _on_tab_change(self, change):
        source_map = {
            self.TAB_STRUCTURE: "none",
            self.TAB_TRAJECTORY: "trajectory",
            self.TAB_FILE_LIST: "file_list",
            self.TAB_DATABASE: "database",
        }
        if change["new"] == self.TAB_DATABASE:
            self._database_lazy.build()
        self.model.ensemble_source = source_map.get(change["new"], "none")
        self._clear_non_active_source(change["new"])
        self._update_cost_preview()

    def _clear_non_active_source(self, active_index: int):
        """Reset all input widgets except the currently active one."""
        widgets = [
            self.structure_widget,
            self.trajectory_widget,
            self.file_list_widget,
            self._database_lazy,
        ]
        for i, widget in enumerate(widgets):
            if i != active_index:
                widget.reset()

    def reset(self):
        self.structure_widget.reset()
        self.trajectory_widget.reset()
        self.file_list_widget.reset()
        self._database_lazy.reset()
        self.absorber_selector.reset()
        self.model.reset()
        self.tabs.selected_index = self.TAB_STRUCTURE
        self.cost_preview.value = ""
        self.frame_count.value = ""


def _parse_indices(text: str) -> list[int]:
    """Parse a comma-separated list or slice notation into frame indices."""
    text = text.strip()
    if not text:
        return []
    if ":" in text:
        parts = text.split(":")
        if len(parts) == 2:
            start, stop = (int(parts[0]) if parts[0] else 0), (int(parts[1]) if parts[1] else None)
            return list(range(start, stop)) if stop is not None else list(range(start, 100000))
        if len(parts) == 3:
            start = int(parts[0]) if parts[0] else 0
            stop = int(parts[1]) if parts[1] else None
            step = int(parts[2]) if parts[2] else 1
            if stop is not None:
                return list(range(start, stop, step))
            return list(range(start, 100000, step))
    return [int(x.strip()) for x in text.split(",") if x.strip()]


def _upload_error_message(filename: str, file_kind: str, error: Exception) -> str:
    """Build an accessible, actionable alert for a failed file upload."""
    escaped_filename = escape(filename)
    escaped_error = escape(str(error))
    return (
        "<div role='alert' style='margin: 8px 0; padding: 10px 12px; "
        "border-left: 4px solid #d32f2f; background: #ffebee; color: #7f0000;'>"
        f"<strong>Could not load {escaped_filename}.</strong><br>"
        f"Check that it is a valid {file_kind} file, then try uploading it again."
        "<details style='margin-top: 6px;'>"
        "<summary>Show technical details</summary>"
        f"<code style='white-space: pre-wrap;'>{escaped_error}</code>"
        "</details></div>"
    )
