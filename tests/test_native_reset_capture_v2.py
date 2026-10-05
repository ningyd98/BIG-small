"""SOFTWARE_ONLY event controls; no backend reset/step/renderer is executed."""

import hashlib
import json
from dataclasses import replace
from importlib import import_module, util

import pytest

from cloud_edge_robot_arm.simulation.mujoco.backend import BackendOperationBoundary
from cloud_edge_robot_arm.vision.raw_recorder_v3 import _plain
from tests.test_raw_episode_v3 import state
from tests.test_visual_raw_recorder_v3 import recorder_fixture


def api():
    name = "cloud_edge_robot_arm.research.native_reset_capture_v2"
    assert util.find_spec(name), "source-only RESET tee is missing"
    return import_module(name)


def recorder(tmp_path):
    base, backend, capture, executor, *_ = recorder_fixture(tmp_path)
    result = api().VisualResetClockRecorderV2(
        backend,
        capture,
        executor,
        directory=tmp_path / "prefix",
        source_root=base.source_root,
        source_hashes=base.source_hashes,
    )
    return result, backend


def event(kind, phase, episode="software-new", op=1, step=0, result=None, error=None):
    return BackendOperationBoundary(
        op,
        kind,
        phase,
        episode,
        step,
        step / 240,
        {"requested": {}},
        result,
        "RuntimeError" if error else None,
        error,
    )


def reset_events(rec, backend, old=None):
    backend._episode_id = old
    scenario = _plain(backend._scenario)
    begin = replace(event("RESET", "BEGIN", old), parameters={"requested": scenario})
    rec._on_boundary(begin)
    backend._episode_id = "software-new"
    payload = state(0)
    payload["episode_id"] = "software-new"
    result = {
        "physics_state": payload,
        "initial_controller_targets": {"joints_rad": [0] * 7, "fingers_m": [0.039, 0.039]},
        "physics_dt_s": 1 / 240,
        "actuator_delay_steps": 0,
    }
    rec._on_boundary(event("RESET", "END", result=result))


@pytest.mark.parametrize("old", [None, "software-old"])
def test_one_observer_exact_clock_tee_and_old_begin_new_end_keep_raw_sequence(tmp_path, old):
    rec, backend = recorder(tmp_path)
    with rec:
        assert backend._operation_observer.__self__ is rec
        with pytest.raises(RuntimeError):
            with backend.observe_operation_boundaries(lambda _: None):
                pass
        returned = rec._clock_pair()
        assert rec.clock_pair_originals[-1]["sequence"] == returned[0]
        assert rec.clock_pair_originals[-1]["mono_before_ns"] == returned[1]
        assert rec.clock_pair_originals[-1]["utc_at"] == returned[2].isoformat()
        reset_events(rec, backend, old)
        assert rec._record_seq == 0
        snapshot = rec.freeze_unbound_prefix().to_payload()
        assert len(snapshot["reset_journal"]) == 2
        assert snapshot["reset_journal"][0]["event"]["episode_id"] == old
        assert snapshot["reset_journal"][1]["event"]["episode_id"] == "software-new"
        assert snapshot["raw_source_binding"] == "UNBOUND"
        assert rec._identity is None
        assert len(snapshot["clock_pairs"]) == 3
        assert all(r["mono_before_ns"] <= r["mono_after_ns"] for r in snapshot["reset_journal"])


def test_snapshot_detaches_aliases_and_retains_failed_reset_and_late_events(tmp_path):
    rec, backend = recorder(tmp_path)
    with rec:
        rec._on_boundary(event("RESET", "BEGIN", None))
        rec._on_boundary(event("RESET", "END", None, error="reset source failed"))
        frozen = rec.freeze_unbound_prefix()
        public = frozen.to_payload()
        public["reset_journal"].clear()
        assert len(frozen.to_payload()["reset_journal"]) == 2
        assert frozen.to_payload()["reset_journal"][1]["event"]["error"] == "reset source failed"
        rec._on_boundary(event("CONTROL", "BEGIN", op=2))
        assert rec.late_event_count == 1
        with pytest.raises(RuntimeError):
            rec.freeze_unbound_prefix()
        exported = rec.export_unbound_prefix()
        assert exported["late_event_count"] == 1
        assert exported["source_consistency"] != "COMPLETE"
        assert (rec.directory / "late-events.json").is_file()


def test_cached_capture_denominator_and_failed_frame_are_exported_without_bound_owner(tmp_path):
    rec, backend = recorder(tmp_path)
    with rec:
        reset_events(rec, backend)
        rec._on_boundary(event("CAPTURE", "BEGIN", op=2))
        rec._on_boundary(event("CAPTURE", "END", op=2, error="cached camera failed"))
        rec.freeze_unbound_prefix()
        exported = rec.export_unbound_prefix()
        assert exported["cached_capture_allocations"] == 1
        assert exported["explicit_acquisitions"] == 0
        assert exported["allocated_actions"] == 0
        rows = json.loads((rec.directory / "unbound-frames.json").read_text())
        assert len(rows) == 1 and rows[0]["observation_payload"] is None
        pairs = json.loads((rec.directory / "clock-pairs.json").read_text())
        assert len(pairs) == 4
        assert not (rec.directory / "raw-envelope.json").exists()
        assert not (rec.directory / "raw-records.json").exists()
        for name, digest in exported["file_hashes"].items():
            assert hashlib.sha256((rec.directory / name).read_bytes()).hexdigest() == digest


def test_upcoming_control_n_is_retained_with_physics_n_not_previous_step(tmp_path):
    rec, backend = recorder(tmp_path)
    with rec:
        reset_events(rec, backend)
        control = {"physics_step": 1, "episode_id": "software-new"}
        rec._on_boundary(event("CONTROL", "BEGIN", op=2, step=0))
        rec._on_boundary(event("CONTROL", "END", op=2, step=0, result={"control_state": control}))
        rec._on_boundary(event("PHYSICS", "BEGIN", op=3, step=0))
        post = state(1)
        post["episode_id"] = "software-new"
        rec._on_boundary(event("PHYSICS", "END", op=3, step=1, result={"physics_state": post}))
        result = rec.freeze_unbound_prefix().to_payload()
        assert len(result["physics"]) == 1
        assert result["physics"][0]["physics_step"] == 1
        assert result["physics"][0]["control_payload"]["physics_step"] == 1
        seqs = [r["record_seq"] for r in result["intervals"] + result["physics"]]
        assert sorted(seqs) == [1, 2, 3]
