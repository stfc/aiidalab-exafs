"""Structure input step for the AiiDAlab FEFF app."""

from __future__ import annotations

import ipywidgets as ipw
from aiida import orm
from aiida.orm import Group, QueryBuilder, StructureData, TrajectoryData
from alc_aiidalab_widgets.widgets.status import Status

from aiidalab_feff.absorber import AbsorberSelectorWidget
from aiidalab_feff.common.file_handling import (
    build_step_indices,
    read_cif_xyz_to_structure_data,
    read_file_list_to_structures,
    read_xyz_to_trajectory_data,
)
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

        super().__init__(
            [
                ipw.HTML("<h3>Upload a single structure</h3>"),
                self.file_upload,
                self.status,
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
            self.status.value = f"Loaded {filename} ({len(structure.sites)} atoms)."
        except Exception as exc:  # noqa: BLE001
            self.status.value = f"<span style='color: red'>Error: {exc}</span>"
            self.model.structure = None

    def reset(self):
        self.file_upload.value = () if isinstance(self.file_upload.value, tuple) else {}
        self.status.value = ""
        self.model.structure = None


class TrajectoryInputWidget(ipw.VBox):
    """Trajectory upload with stride / index sampling.

    TODO: trajectory UX — pass the full list of snapshot structures (or the
    TrajectoryData itself) to a weas-widget visualiser so the user can inspect
    frames while choosing stride/indices.
    """

    def __init__(self, model: InputModel):
        self.model = model

        self.file_upload = ipw.FileUpload(
            multiple=False,
            description="Upload Trajectory File",
            button_style="primary",
        )
        self.file_upload.observe(self._on_upload, names="value")

        self.stride = ipw.IntSlider(
            value=1,
            min=1,
            max=100,
            step=1,
            description="Stride:",
            continuous_update=False,
        )
        self.stride.observe(self._on_stride_change, names="value")

        self.indices_text = ipw.Text(
            value="",
            placeholder="e.g. 0,10,20 or 0:100:10",
            description="Indices:",
            layout={"width": "300px"},
        )
        self.indices_text.observe(self._on_indices_change, names="value")

        self.frame_count = ipw.HTML()
        self.status = Status()

        super().__init__(
            [
                ipw.HTML("<h3>Upload an MD trajectory</h3>"),
                self.file_upload,
                ipw.HBox([self.stride, self.indices_text]),
                self.frame_count,
                self.status,
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
            trajectory = read_xyz_to_trajectory_data(content, filename)
            validate_trajectory_size(trajectory)
            self.model.trajectory = trajectory
            self._update_indices()
            self.status.value = f"Loaded {filename} with {len(trajectory.get_stepids())} frames."
        except Exception as exc:  # noqa: BLE001
            self.status.value = f"<span style='color: red'>Error: {exc}</span>"
            self.model.trajectory = None
            self.model.selected_indices = None
            self.model.structures = {}
            self.frame_count.value = "Selected frames: 0"

    def _on_stride_change(self, change):
        self.indices_text.value = ""
        self._update_indices()

    def _on_indices_change(self, change):
        if change["new"].strip():
            self._update_indices_from_text(change["new"])

    def _update_indices(self):
        trajectory = self.model.trajectory
        if trajectory is None:
            self.frame_count.value = "Selected frames: 0"
            return
        if not isinstance(trajectory, TrajectoryData):
            self.status.value = (
                "<span style='color: red'>Error: uploaded object is not a trajectory.</span>"
            )
            return
        step_ids = list(trajectory.get_stepids())
        if not step_ids:
            step_ids = list(range(len(trajectory.get_array("positions"))))
        indices = build_step_indices(len(step_ids), self.stride.value)
        self.model.selected_indices = [step_ids[i] for i in indices]
        self.frame_count.value = f"Selected frames: {len(self.model.selected_indices)}"
        self._split_trajectory()

    def _update_indices_from_text(self, text: str):
        if self.model.trajectory is None:
            return
        try:
            indices = _parse_indices(text)
            self.model.selected_indices = indices
            self.frame_count.value = f"Selected frames: {len(indices)}"
            self._split_trajectory()
        except Exception as exc:  # noqa: BLE001
            self.status.value = f"<span style='color: red'>Invalid indices: {exc}</span>"

    def _split_trajectory(self):
        from aiida_feff.utils import split_trajectory

        if self.model.trajectory is None or not self.model.selected_indices:
            self.model.structures = {}
            return
        params = orm.Dict(dict={"step_ids": self.model.selected_indices})
        self.model.structures = dict(split_trajectory(self.model.trajectory, params))

    def reset(self):
        self.file_upload.value = () if isinstance(self.file_upload.value, tuple) else {}
        self.indices_text.value = ""
        self.frame_count.value = ""
        self.status.value = ""
        # Avoid triggering _update_indices while the model is being cleared by
        # other widgets; reset will be followed by a model reset if needed.
        self.stride.unobserve(self._on_stride_change, names="value")
        self.stride.value = 1
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
            self.status.value = ""
        except Exception as exc:  # noqa: BLE001
            self.status.value = f"<span style='color: red'>Error: {exc}</span>"
            self.model.structures = {}

    def reset(self):
        self.file_upload.value = () if isinstance(self.file_upload.value, tuple) else {}
        self.frame_count.value = ""
        self.status.value = ""
        self.model.structures = {}


class GroupInputWidget(ipw.VBox):
    """Select an AiiDA Group containing StructureData nodes."""

    def __init__(self, model: InputModel):
        self.model = model

        self.refresh_button = ipw.Button(
            description="Refresh groups",
            icon="refresh",
        )
        self.refresh_button.on_click(self._refresh_groups)

        self.group_selector = ipw.Dropdown(
            options=[],
            description="Group:",
            layout={"width": "400px"},
        )
        self.group_selector.observe(self._on_group_change, names="value")

        self.frame_count = ipw.HTML()
        self.status = Status()

        super().__init__(
            [
                ipw.HTML("<h3>Select an AiiDA Group</h3>"),
                ipw.HBox([self.group_selector, self.refresh_button]),
                self.frame_count,
                self.status,
            ]
        )

    def _refresh_groups(self, _):
        query = QueryBuilder()
        query.append(Group, project=["label", "id"])
        query.append(StructureData, with_group=Group)
        options = []
        seen = set()
        for group_label, _ in query.all():
            if group_label not in seen:
                options.append((group_label, group_label))
                seen.add(group_label)
        self.group_selector.options = options

    def _on_group_change(self, change):
        if not change["new"]:
            return
        try:
            group = orm.Group.get(label=change["new"])
            structures = {
                f"struct_{node.pk}": node for node in group.nodes if isinstance(node, StructureData)
            }
            self.model.structures = structures
            self.frame_count.value = (
                f"Loaded {len(structures)} structures from group '{change['new']}'."
            )
        except Exception as exc:  # noqa: BLE001
            self.status.value = f"<span style='color: red'>Error: {exc}</span>"

    def reset(self):
        self.group_selector.options = []
        self.frame_count.value = ""
        self.status.value = ""
        self.model.structures = {}


class InputWidget(ipw.VBox):
    """Main input step widget combining single and ensemble sources."""

    def __init__(self, model: InputModel):
        self.model = model

        self.structure_widget = StructureInputWidget(model)
        self.trajectory_widget = TrajectoryInputWidget(model)
        self.file_list_widget = FileListInputWidget(model)
        self.group_widget = GroupInputWidget(model)

        self.tabs = ipw.Tab(
            children=[
                self.structure_widget,
                self.trajectory_widget,
                self.file_list_widget,
                self.group_widget,
            ]
        )
        self.tabs.set_title(0, "Single structure")
        self.tabs.set_title(1, "MD trajectory")
        self.tabs.set_title(2, "File list")
        self.tabs.set_title(3, "AiiDA Group")
        self.tabs.observe(self._on_tab_change, names="selected_index")

        self.absorber_selector = AbsorberSelectorWidget(model)

        self.status = Status()
        self.frame_count = ipw.HTML()

        super().__init__(
            [
                ipw.HTML("<h2>Input structures</h2>"),
                self.tabs,
                self.frame_count,
                self.absorber_selector,
                self.status,
            ]
        )

        self.model.observe(self._on_model_structures, names="structures")
        self.model.observe(self._on_model_structures, names="structure")

    def _on_model_structures(self, change):
        structures = self.model.get_structures()
        if structures:
            self.frame_count.value = f"Total structures ready: {len(structures)}"
        else:
            self.frame_count.value = ""

    def _on_tab_change(self, change):
        source_map = {0: "none", 1: "trajectory", 2: "file_list", 3: "group"}
        self.model.ensemble_source = source_map.get(change["new"], "none")
        self._clear_non_active_source(change["new"])

    def _clear_non_active_source(self, active_index: int):
        """Reset all input widgets except the currently active one."""
        widgets = [
            self.structure_widget,
            self.trajectory_widget,
            self.file_list_widget,
            self.group_widget,
        ]
        for i, widget in enumerate(widgets):
            if i != active_index:
                widget.reset()

    def reset(self):
        self.structure_widget.reset()
        self.trajectory_widget.reset()
        self.file_list_widget.reset()
        self.group_widget.reset()
        self.absorber_selector.reset()
        self.model.reset()
        self.tabs.selected_index = 0


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
