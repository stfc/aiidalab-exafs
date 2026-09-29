"""Tests for the running-tasks overview and breadcrumb navigation."""

from __future__ import annotations

from types import SimpleNamespace


def test_is_running_workflow():
    """_is_running_workflow accepts only unfinished EnsembleExafsWorkChains."""
    from unittest.mock import MagicMock

    from aiida.orm import WorkChainNode

    from aiidalab_feff.running_tasks import _is_running_workflow

    running = MagicMock(spec=WorkChainNode)
    running.process_label = "EnsembleExafsWorkChain"
    running.is_terminated = False
    assert _is_running_workflow(running)

    terminated = MagicMock(spec=WorkChainNode)
    terminated.process_label = "EnsembleExafsWorkChain"
    terminated.is_terminated = True
    assert not _is_running_workflow(terminated)

    wrong_label = MagicMock(spec=WorkChainNode)
    wrong_label.process_label = "OtherWorkChain"
    wrong_label.is_terminated = False
    assert not _is_running_workflow(wrong_label)

    assert not _is_running_workflow(object())


def test_aggregate_jobs_counts_snaps_and_skips_potentials():
    """Aggregation rolls job records into done/failed/pending snap counts."""
    from aiidalab_feff.running_tasks import _aggregate_jobs

    jobs = [
        # Serial (frame, site) jobs: one snap each.
        {
            "label": "feff_snap_0000_site_0000",
            "state": "finished",
            "ok": True,
            "covered": 1,
            "done_snaps": 1,
        },
        {
            "label": "feff_snap_0001_site_0000",
            "state": "finished",
            "ok": False,
            "covered": 1,
            "done_snaps": 0,
        },
        {
            "label": "feff_snap_0002_site_0000",
            "state": "running",
            "ok": None,
            "covered": 1,
            "done_snaps": None,
        },
        # Potentials-only precompute job: skipped entirely.
        {"label": "pot_site_0000", "state": "finished", "ok": True, "covered": 1, "done_snaps": 1},
        # Batch jobs: multiple snaps each.
        {"label": "batch_0000", "state": "finished", "ok": True, "covered": 4, "done_snaps": 4},
        {"label": "batch_0001", "state": "waiting", "ok": None, "covered": 4, "done_snaps": None},
        {"label": "batch_0002", "state": "finished", "ok": False, "covered": 3, "done_snaps": 0},
        # Finished-ok batch that lost one snap internally.
        {"label": "batch_0003", "state": "finished", "ok": True, "covered": 2, "done_snaps": 1},
    ]
    agg = _aggregate_jobs(jobs)
    # done: 1 serial + 4 batch + 1 partial batch = 6
    # failed: 1 serial + 3 failed batch + 1 lost snap = 5
    # pending: 1 serial running + 4 batch waiting = 5
    # jobs: 7 (pot skipped)
    assert agg == {"done": 6, "failed": 5, "pending": 5, "jobs": 7}


def test_estimate_expected_calculations_structures_namespace():
    """Expected total = number of structures × absorber sites."""
    from aiidalab_feff.running_tasks import _estimate_expected_calculations

    params = SimpleNamespace(get_dict=lambda: {"edge": "K", "absorbing_atoms": [0, 5]})
    structures = {"frame_0000": object(), "frame_0001": object(), "frame_0002": object()}
    inputs = SimpleNamespace(parameters=params, structures=structures, trajectory=None)
    node = SimpleNamespace(inputs=inputs)
    assert _estimate_expected_calculations(node) == 6


def test_estimate_expected_calculations_trajectory_with_step_ids():
    """Trajectory input honours explicit step_ids for the frame count."""
    from aiidalab_feff.running_tasks import _estimate_expected_calculations

    class FakeTrajectory:
        def get_stepids(self):
            return list(range(10))

        def get_index_from_stepid(self, step_id):
            return step_id

        def get_step_structure(self, index):
            return object()

    class FakeList:
        def get_list(self):
            return [0, 2, 4]

    params = SimpleNamespace(get_dict=lambda: {"absorbing_atoms": 3})
    inputs = SimpleNamespace(
        parameters=params,
        structures=None,
        trajectory=FakeTrajectory(),
        step_ids=FakeList(),
    )
    node = SimpleNamespace(inputs=inputs)
    # 3 selected frames × 1 absorber site (int spec).
    assert _estimate_expected_calculations(node) == 3


def test_estimate_expected_calculations_trajectory_with_sample_interval():
    """Trajectory input honours sample_interval when no step_ids are given."""
    from aiidalab_feff.running_tasks import _estimate_expected_calculations

    class FakeTrajectory:
        def get_array(self, name):
            return [None] * 10  # 10 frames

        def get_stepids(self):
            return list(range(10))

        def get_index_from_stepid(self, step_id):
            return step_id

        def get_step_structure(self, index):
            return object()

    params = SimpleNamespace(get_dict=lambda: {"absorbing_atoms": [1]})
    inputs = SimpleNamespace(
        parameters=params,
        structures=None,
        trajectory=FakeTrajectory(),
        sample_interval=SimpleNamespace(value=3),
    )
    node = SimpleNamespace(inputs=inputs)
    # range(0, 10, 3) = 4 frames × 1 site.
    assert _estimate_expected_calculations(node) == 4


def test_estimate_expected_calculations_returns_none_when_unresolvable():
    """Missing parameters or unresolvable absorber specs fall back to None."""
    from aiidalab_feff.running_tasks import _estimate_expected_calculations

    # No absorbing atom spec at all.
    params = SimpleNamespace(get_dict=lambda: {"edge": "K"})
    inputs = SimpleNamespace(
        parameters=params,
        structures={"frame_0000": object()},
        trajectory=None,
    )
    assert _estimate_expected_calculations(SimpleNamespace(inputs=inputs)) is None

    # Element-symbol spec but no structure available to resolve it against.
    params = SimpleNamespace(get_dict=lambda: {"absorbing_atoms": "Cu"})
    inputs = SimpleNamespace(parameters=params, structures=None, trajectory=None)
    assert _estimate_expected_calculations(SimpleNamespace(inputs=inputs)) is None

    # Broken inputs raise into the blanket handler.
    assert _estimate_expected_calculations(SimpleNamespace()) is None


def test_counts_text_and_progress_bar():
    """Summary text and bar reflect done/failed/left counts."""
    from aiidalab_feff.running_tasks import _counts_text, _progress_bar_html

    text = _counts_text(done=5, failed=1, pending=2, expected=10)
    assert "5/10 done" in text
    assert "1 failed" in text
    assert "4 left" in text

    text = _counts_text(done=2, failed=0, pending=3, expected=None)
    assert "2 done" in text
    assert "3 pending" in text

    bar = _progress_bar_html(done=5, failed=1, total=10)
    assert "width:50%" in bar
    assert "width:10%" in bar


def test_job_record_skips_potentials_and_requires_frame_idx():
    """Potentials-only jobs are excluded from progress accounting."""
    from aiidalab_feff.running_tasks import _job_record

    pot = SimpleNamespace(
        label="pot_site_0000",
        process_label="FeffCalculation",
        process_state=SimpleNamespace(value="finished"),
        is_finished_ok=True,
        inputs={},
    )
    assert _job_record(pot) is None

    no_frame = SimpleNamespace(
        label="",
        process_label="FeffCalculation",
        process_state=SimpleNamespace(value="running"),
        is_finished_ok=False,
        inputs={},  # no frame_idx
    )
    assert _job_record(no_frame) is None

    serial = SimpleNamespace(
        label="feff_snap_0000_site_0000",
        process_label="FeffCalculation",
        process_state=SimpleNamespace(value="finished"),
        is_finished_ok=True,
        inputs={"frame_idx": object()},
    )
    record = _job_record(serial)
    assert record is not None
    assert record["covered"] == 1
    assert record["done_snaps"] == 1
    assert record["ok"] is True


def test_job_record_uses_batched_link_maps_instead_of_per_child_queries():
    """With link maps supplied, _job_record must not touch child.inputs/outputs.

    The batched maps exist to kill an N+1 query; if _job_record silently fell
    back to per-child link access the speed-up would vanish unnoticed.
    """
    from aiidalab_feff.running_tasks import _job_record

    class Exploding:
        """Any attribute access means we hit the database per child."""

        def __getattr__(self, name):
            raise AssertionError(f"per-child link access: {name}")

        def __contains__(self, item):
            raise AssertionError(f"per-child link access: {item}")

    batch = SimpleNamespace(
        label="feff_batch_0000",
        process_label="FeffBatchCalculation",
        process_state=SimpleNamespace(value="finished"),
        is_finished_ok=True,
        pk=7,
        inputs=Exploding(),
        outputs=Exploding(),
    )
    # has_frame_idx, frame_counts (pk -> covered), snap_counts (pk -> produced)
    link_maps = (set(), {7: 10}, {7: 8})
    record = _job_record(batch, link_maps)
    assert record["covered"] == 10
    assert record["done_snaps"] == 8

    # A serial job whose pk is absent from has_frame_idx is potentials-only.
    serial = SimpleNamespace(
        label="",
        process_label="FeffCalculation",
        process_state=SimpleNamespace(value="finished"),
        is_finished_ok=True,
        pk=9,
        inputs=Exploding(),
        outputs=Exploding(),
    )
    assert _job_record(serial, ({}, {}, {})) is None
    assert _job_record(serial, ({9}, {}, {}))["covered"] == 1


def test_create_breadcrumbs_wires_clicks():
    """Breadcrumb buttons forward their step index to the callback."""
    from aiidalab_feff.common.navigation import create_breadcrumbs

    seen = []
    container, buttons = create_breadcrumbs(["1 A", "2 B", "3 C"], seen.append)
    assert len(buttons) == 3
    # Two separator spans between the three buttons.
    assert len(container.children) == 5
    buttons[2].click()
    assert seen == [2]


def test_running_tasks_widget_refresh_without_profile():
    """The widget constructs and refresh swallows query errors (no AiiDA profile)."""
    from aiidalab_feff.running_tasks import RunningTasksWidget

    widget = RunningTasksWidget()
    widget.refresh()
    assert widget.last_count is not None or widget.status.value
