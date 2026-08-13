"""Trait-based models for the AiiDAlab FEFF app."""

from __future__ import annotations

from typing import Any

from aiida.orm import Code, Computer, ProcessNode, StructureData, TrajectoryData
from aiida_feff.data.pathcontributions import PathContributionsData
from aiida_feff.data.xasdata import XasData
from traitlets import Bool, Dict as TraitDict, Float, HasTraits, Instance, Int, List, Unicode


class InputModel(HasTraits):
    """Holds the structure input state and view-state for the input step."""

    structure = Instance(StructureData, allow_none=True)
    structures = TraitDict(allow_none=True)  # {label: StructureData}
    ensemble_source = Unicode(default_value="none")
    absorbing_atoms = List(Int(), default_value=[])
    # Trajectory source:
    trajectory = Instance(TrajectoryData, allow_none=True)
    stride = Int(default_value=1)
    selected_indices = Instance(list, default_value=None, allow_none=True)

    def is_single_structure(self) -> bool:
        """Return True if a single structure has been provided."""
        return self.structure is not None or (self.trajectory is not None and len(self.selected_indices or []) == 1) or (
            self.structures is not None and len(self.structures) == 1
        )

    def is_ensemble(self) -> bool:
        """Return True if an ensemble (or single structure) has been provided."""
        return self.structure is not None or self.trajectory is not None or bool(self.structures)

    def get_structures(self) -> dict[str, Any] | None:
        """Return the unified structures dict, or None if not set."""
        if self.structure is not None:
            return {"frame_0000": self.structure}
        if self.structures:
            return dict(self.structures)
        return None

    def reset(self):
        """Reset all input state."""
        self.structure = None
        self.structures = None
        self.ensemble_source = "none"
        self.absorbing_atoms = []
        self.trajectory = None
        self.stride = 1
        self.selected_indices = None


class WorkflowModel(HasTraits):
    """Holds the FEFF parameters and resource selection."""

    parameters = TraitDict(default_value=None, allow_none=True)
    path_cw_threshold = Float(default_value=-1.0)
    code = Instance(Code, allow_none=True)
    computer = Instance(Computer, allow_none=True)
    # Scheduler options (remote only):
    walltime_seconds = Int(allow_none=True)
    num_nodes = Int(allow_none=True)
    # Batch options (remote only, optional):
    batch_size = Int(allow_none=True)
    n_workers = Int(allow_none=True)
    python_code = Instance(Code, allow_none=True)
    precompute_potentials = Bool(default_value=False)

    def reset(self):
        """Reset all workflow state."""
        self.parameters = None
        self.path_cw_threshold = -1.0
        self.code = None
        self.computer = None
        self.walltime_seconds = None
        self.num_nodes = None
        self.batch_size = None
        self.n_workers = None
        self.python_code = None
        self.precompute_potentials = False

    def is_batch(self) -> bool:
        """Return True if batch submission is enabled."""
        return self.batch_size is not None and self.batch_size > 1

    def is_local(self) -> bool:
        """Return True if execution is local (no remote computer)."""
        return self.computer is None


class SubmissionModel(HasTraits):
    """Holds the submitted process node."""

    process_node = Instance(ProcessNode, allow_none=True)

    def reset(self):
        """Reset submission state."""
        self.process_node = None


class ResultsModel(HasTraits):
    """Holds the outputs driving the results page."""

    averaged_xas = TraitDict(allow_none=True)  # {label: XasData}
    n_failed = Int(allow_none=True)
    path_contributions = Instance(PathContributionsData, allow_none=True)
    is_ensemble = Bool(default_value=False)
    process_node = Instance(ProcessNode, allow_none=True)
    # Absorber / edge metadata for plot titles & legends, e.g. "Mn K-edge".
    edge = Unicode(default_value="")
    absorber_label = Unicode(default_value="")  # e.g. "Mn" or "Mn @ sites 0,2,4"
    # An uploaded or database-selected reference spectrum for live comparison.
    experimental_xas = Instance(XasData, allow_none=True)
    # Per-(frame, site) XasData grid for the convergence / sub-sampling view.
    # Stored as a Python dict keyed by (frame_idx:int, site_idx:int); built in
    # ProcessWidget._populate_results by walking the workchain's FeffCalculation
    # children. ``None`` when no run is loaded or no per-snapshot data exists.
    xas_grid = Instance(dict, allow_none=True)

    def reset(self):
        """Reset results state."""
        self.averaged_xas = None
        self.n_failed = None
        self.path_contributions = None
        self.is_ensemble = False
        self.process_node = None
        self.edge = ""
        self.absorber_label = ""
        self.experimental_xas = None
        self.xas_grid = None

    @property
    def spectrum_title(self) -> str:
        """A short title like 'Mn K-edge' (empty if metadata not populated)."""
        el = self.absorber_label
        if el and self.edge:
            return f"{el} {self.edge}-edge"
        if self.edge:
            return f"{self.edge}-edge"
        return el

    def has_path_contributions(self) -> bool:
        """Return True if path contributions are available."""
        return self.path_contributions is not None

    def has_path_contributions(self) -> bool:
        """Return True if path contributions are available."""
        return self.path_contributions is not None
