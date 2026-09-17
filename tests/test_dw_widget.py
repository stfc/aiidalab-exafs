"""Tests for DebyeWallerScreeningWidget and PathContributionsExplorer (ADR 0005, ADR 0007)."""

import numpy as np
from ase.build import bulk
from md_exafs.paths import PathResult

from aiidalab_feff.dw_widget import DebyeWallerScreeningWidget
from aiidalab_feff.widgets.paths_explorer import PathContributionsExplorer


class DummyModel:
    def __init__(self, structures):
        self._structures = structures

    def get_structures(self):
        return {f"frame_{i}": s for i, s in enumerate(self._structures)}


def test_dw_screening_widget(capsys):
    # 3 frames of Cu with small displacements in a supercell
    rng = np.random.default_rng(0)
    s1 = bulk("Cu", "fcc", a=3.61) * (2, 2, 2)
    s2 = s1.copy()
    s2.positions += rng.normal(0, 0.02, s2.positions.shape)
    s3 = s1.copy()
    s3.positions += rng.normal(0, 0.02, s3.positions.shape)

    model = DummyModel([s1, s2, s3])
    widget = DebyeWallerScreeningWidget(model)
    widget.absorber.value = "Cu"
    widget.max_r.value = 4.0
    widget._on_run(None)
    captured = capsys.readouterr()
    assert "Calculated" in captured.out
    assert "Mean isotropic B-factor" in captured.out


def test_dw_screening_widget_with_trajectory_model(capsys):
    rng = np.random.default_rng(1)
    s1 = bulk("Cu", "fcc", a=3.61) * (2, 2, 2)
    s2 = s1.copy()
    s2.positions += rng.normal(0, 0.02, s2.positions.shape)

    class DummyTrajectory:
        symbols = list(s1.get_chemical_symbols())

        def get_arraynames(self):
            return ["positions", "cells"]

        def get_array(self, name):
            if name == "positions":
                return np.array([s1.positions, s2.positions])
            if name == "cells":
                return np.array([s1.cell.array, s2.cell.array])
            return None

        def get_stepids(self):
            return [0, 1]

    class MockInputModel:
        trajectory = DummyTrajectory()
        absorbing_atoms = [0]
        selected_indices = None

    model = MockInputModel()
    widget = DebyeWallerScreeningWidget(model)
    widget._on_run(None)
    captured = capsys.readouterr()
    assert "Calculated" in captured.out
    assert "Mean isotropic B-factor" in captured.out


def test_paths_explorer_widget():
    class DummyStore:
        def iter_paths(self):
            yield PathResult(
                frame_idx=0,
                site_idx=0,
                r_eff=2.5,
                nlegs=2,
                degeneracy=12.0,
                scatterer="Cu",
                cw_ratio=100.0,
                k=np.linspace(0, 20, 10),
                feff_data=np.ones((10, 6)),
            )

    explorer = PathContributionsExplorer(DummyStore())
    assert len(explorer.path_groups) == 1
    assert explorer.path_groups[0]["scatterer"] == "Cu"
