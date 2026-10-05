"""Artifact-local, pure CPU XML/source checks. No MuJoCo or decoder calls."""

from __future__ import annotations

import importlib.util
import json
import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

import pytest

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
OLD = ROOT / "assets/robots/franka_panda/scene_pose_marker_outboard_v3.xml"


def api():
    path = HERE / "prepare.py"
    assert path.exists(), "v4 preparation implementation is missing"
    spec = importlib.util.spec_from_file_location("marker_v4_owned", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def markers():
    return [
        {
            "physics_step": n,
            "episode_id": "e",
            "sim_time_s": n / 240,
            "decode_status": "UNKNOWN" if n in {1, 3} else "OBSERVED",
            "marker": {"reason": "known_marker_not_observed"},
        }
        for n in range(5)
    ]


def state(step=0):
    return {
        "episode_id": "e",
        "physics_step": step,
        "sim_time_s": step / 240,
        "camera_state": {
            "sim_time_s": step / 240,
            "qpos": [0.0] * 37,
            "qvel": [0.0] * 33,
            "act": [],
            "ctrl": [0.0] * 9,
        },
    }


def test_candidate_is_deterministic_and_saved_bytes_match():
    m = api()
    original = OLD.read_bytes()
    result = m.build_v4(original)
    assert m.build_v4(original) == result
    assert (HERE / "scene_pose_marker_outboard_v4.xml").read_bytes() == result
    assert OLD.read_bytes() == original


def test_complete_nonmarker_topology_is_unchanged():
    m = api()
    before = ET.fromstring(OLD.read_bytes())
    after = ET.fromstring(m.build_v4(OLD.read_bytes()))
    assert m.nonmarker_tree(before) == m.nonmarker_tree(after)
    assert len(list(after.iter("body"))) == len(list(before.iter("body")))
    assert len(list(after.iter("joint"))) == len(list(before.iter("joint")))


def test_marker_pattern_size_attachment_and_visual_only_flags():
    m = api()
    old = m.marker_geoms(ET.fromstring(OLD.read_bytes()), "v3")
    new = m.marker_geoms(ET.fromstring(m.build_v4(OLD.read_bytes())), "v4")
    assert len(new) == 37
    assert {k: g.get("rgba") for k, g in old.items()} == {k: g.get("rgba") for k, g in new.items()}
    quiet = new["quiet"]
    assert m.vector(quiet, "pos") == pytest.approx([0.16, 0, 0.03502])
    assert m.vector(quiet, "size") == pytest.approx([0.05, 0.05, 0.00001])
    cells = [g for name, g in new.items() if name != "quiet"]
    assert min(m.vector(g, "pos")[0] - m.vector(g, "size")[0] for g in cells) == pytest.approx(
        0.1225
    )
    assert max(m.vector(g, "pos")[0] + m.vector(g, "size")[0] for g in cells) == pytest.approx(
        0.1975
    )
    for name, g in new.items():
        assert all(g.get(key) == "0" for key in ("mass", "density", "contype", "conaffinity"))
        assert m.vector(g, "pos")[2] == m.vector(old[name], "pos")[2]
        assert m.vector(g, "size")[2] == m.vector(old[name], "size")[2]


@pytest.mark.parametrize(
    "old", [b"<mujoco/>", OLD.read_bytes().replace(b'mass="0.08"', b'mass="0.09"')]
)
def test_source_drift_cannot_generate_candidate(old):
    with pytest.raises(ValueError, match="frozen v3"):
        api().build_v4(old)


@pytest.mark.parametrize(
    "change",
    [
        lambda b: b.replace(b'name="pose_marker_outboard_v4_quiet"', b'name="unexpected"'),
        lambda b: b.replace(b'mass="0"', b'mass="0.01"', 1),
        lambda b: b.replace(b'fovy="50"', b'fovy="55"'),
    ],
)
def test_changed_candidate_rejects(change):
    m = api()
    with pytest.raises(ValueError, match="candidate"):
        m.validate_candidate(OLD.read_bytes(), change(m.build_v4(OLD.read_bytes())))


def test_selection_retains_all_unknown_and_limited_deterministic_controls():
    result = api().select_steps(markers(), [0, 4], [2])
    assert result == {
        "failure_steps": [1, 3],
        "healthy_control_steps": [0, 2, 4],
        "selected_steps": [0, 1, 2, 3, 4],
    }


def test_failure_cannot_be_substituted_as_healthy_control():
    with pytest.raises(ValueError, match="healthy"):
        api().select_steps(markers(), [1], [])


def test_incomplete_pose_source_refuses_before_any_render_budget():
    result = api().preview_readiness([0, 1, 3, 4], {0: state(0), 4: state(4)}, "e")
    assert result["status"] == "UNAVAILABLE_MISSING_ORIGINAL_FULL_QPOS"
    assert result["missing_pose_steps"] == [1, 3]
    assert result["actual_model_constructions"] == result["actual_render_calls"] == 0
    assert result["render_pass_budget_available"] == 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("qpos", [0.0] * 16),
        ("qpos", [math.nan] * 37),
        ("qvel", [0.0] * 15),
        ("ctrl", [0.0] * 7),
        ("act", [1.0]),
    ],
)
def test_malformed_full_state_is_rejected(field, value):
    s = state()
    s["camera_state"][field] = value
    with pytest.raises(ValueError, match="full state"):
        api().preview_readiness([0], {0: s}, "e")


@pytest.mark.parametrize(
    "field,value", [("episode_id", "other"), ("physics_step", 99), ("sim_time_s", 99.0)]
)
def test_original_pose_identity_must_match(field, value):
    s = state()
    s[field] = value
    with pytest.raises(ValueError, match="identity"):
        api().preview_readiness([0], {0: s}, "e")


def pilot():
    path = HERE / "run_sparse_once.py"
    assert path.exists(), "fresh sparse pilot implementation is missing"
    spec = importlib.util.spec_from_file_location("marker_v4_pilot_owned", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class Observation:
    episode_id = "e"
    observation_id = "o"
    checksum_sha256 = "c"
    sim_time_s = 0.0

    def model_dump_json(self):
        return '{"observation_id":"o"}'


def test_sparse_recorder_does_not_invent_whole_step_frames_or_gap(tmp_path):
    m = pilot()
    calls = []

    def capture():
        calls.append(1)
        return Observation(), ["h", "h"]

    recorder = m.SparseRGBDRecorder(
        tmp_path / "sparse",
        capture,
        episode_id="e",
        selected_steps=[0, 3],
        max_sample_gap_s=0.005,
        expected_physics_steps=3,
    )
    for n in range(4):
        recorder.observe_step(episode_id="e", physics_step=n, sim_time_s=n / 240)
        if n in {0, 3}:
            Observation.sim_time_s = n / 240
            recorder.record_step(episode_id="e", physics_step=n, sim_time_s=n / 240)
    summary = recorder.finish(final_step=3, final_sim_time_s=3 / 240)
    assert summary["status"] == "COMPLETE"
    assert summary["scope"] == "SPARSE_PREDECLARED_STEPS_ONLY"
    assert summary["physical_callbacks"] == 4
    assert summary["saved_steps"] == [0, 3]
    assert summary["original_stability_gap_requirement_s"] == 0.005
    assert summary["sparse_max_gap_s"] == 3 / 240
    assert summary["continuous_visibility"] == "NOT_ESTABLISHED"
    assert len(calls) == 2
    Observation.sim_time_s = 0.0


def test_sparse_missing_selected_steps_retains_short_horizon(tmp_path):
    r = pilot().SparseRGBDRecorder(
        tmp_path / "s",
        lambda: (Observation(), ["h", "h"]),
        episode_id="e",
        selected_steps=[0, 3],
        max_sample_gap_s=0.005,
        expected_physics_steps=3,
    )
    r.observe_step(episode_id="e", physics_step=0, sim_time_s=0.0)
    r.record_step(episode_id="e", physics_step=0, sim_time_s=0.0)
    s = r.finish(final_step=0, final_sim_time_s=0.0)
    assert s["status"] == "INCOMPLETE"
    assert s["missing_selected_steps"] == [3]
    assert s["physical_callbacks"] == 1


def test_unplanned_step_cannot_capture(tmp_path):
    calls = []
    r = pilot().SparseRGBDRecorder(
        tmp_path / "s",
        lambda: calls.append(1),
        episode_id="e",
        selected_steps=[0, 3],
        max_sample_gap_s=0.005,
        expected_physics_steps=3,
    )
    r.observe_step(episode_id="e", physics_step=0, sim_time_s=0.0)
    with pytest.raises(ValueError, match="predeclared"):
        r.record_step(episode_id="e", physics_step=1, sim_time_s=1 / 240)
    assert not calls
    r.finish(final_step=0, final_sim_time_s=0.0)


@pytest.mark.parametrize("bad", ["step", "episode", "time"])
def test_physical_callback_identity_drift_rejects(tmp_path, bad):
    r = pilot().SparseRGBDRecorder(
        tmp_path / "s",
        lambda: None,
        episode_id="e",
        selected_steps=[0],
        max_sample_gap_s=0.005,
        expected_physics_steps=3,
    )
    with pytest.raises(ValueError, match="physical callback"):
        r.observe_step(
            episode_id="other" if bad == "episode" else "e",
            physics_step=1 if bad == "step" else 0,
            sim_time_s=-1.0 if bad == "time" else 0.0,
        )
    s = r.finish(final_step=0, final_sim_time_s=0.0)
    assert s["status"] == "INCOMPLETE"
    assert s["physical_callback_attempts"] == 1


@pytest.mark.parametrize(
    "failing_event", ["ACQUISITION_BEGIN", "ACQUISITION_END", "ACQUISITION_FAILED"]
)
def test_inherited_acquisition_journal_failures_keep_original_error_and_denominator(failing_event):
    base = pilot().load_frozen_runner()
    backend = SimpleNamespace(command_records=[])
    adapter = SimpleNamespace(last_capture=None)

    class Journal:
        last_control = last_physics = None

        def ensure(self, backend):
            pass

        def emit(self, event, **kw):
            if event == failing_event:
                raise OSError("publication")

    class Series:
        def record_step(self, **kw):
            if failing_event == "ACQUISITION_FAILED":
                raise ValueError("original camera")
            return {}

    c = base.AcquisitionCoordinator(
        backend, Journal(), Series(), SimpleNamespace(current=None), adapter
    )
    snapshot = SimpleNamespace(episode_id="e", physics_step=0, sim_time_s=0.0)
    with pytest.raises(ValueError if failing_event == "ACQUISITION_FAILED" else OSError) as caught:
        c.record(snapshot)
    assert c.allocated == 1 and c.failed == 1 and c.completed == 0
    assert c.stopped
    if failing_event == "ACQUISITION_FAILED":
        assert str(caught.value) == "original camera"
        assert c.failure_journal_errors and caught.value.__notes__


def test_fresh_specification_changes_only_asset_identity_and_group():
    m = pilot()
    base = m.load_frozen_runner()
    prior_scene, prior_config = base.specification()
    scene, config = m.specification(base)
    assert scene.scene_parameters == prior_scene.scene_parameters
    assert config.model_dump(exclude={"model_path"}) == prior_config.model_dump(
        exclude={"model_path"}
    )
    assert scene.asset_family_hash != prior_scene.asset_family_hash
    assert scene.group_id.startswith("dev-marker-v4-sparse-")
    assert scene.group_id != prior_scene.group_id


def test_frozen_source_drift_rejects_before_import(tmp_path):
    with pytest.raises(RuntimeError, match="frozen runner"):
        pilot().load_frozen_runner(path=tmp_path / "missing.py")


def test_protocol_path_resolves_relative_input_and_rejects_other_directory():
    m = pilot()
    relative = HERE.relative_to(ROOT) / "fix-round-1/pilot-protocol"
    assert m.protocol_directory(relative) == (HERE / "fix-round-1/pilot-protocol").resolve()
    with pytest.raises(RuntimeError, match="fresh pilot"):
        m.protocol_directory(OLD.parent)
    with pytest.raises(RuntimeError, match="fresh pilot"):
        m.protocol_directory(HERE / "pilot-protocol")


def test_new_sparse_coordinator_delegates_only_fixed_selected_steps(monkeypatch):
    m = pilot()
    base = m.configured_runner({"selected_steps": [0, 3], "expected_physics_steps": 4806})
    calls, observed = [], []
    parent = base.AcquisitionCoordinator.__mro__[1]
    monkeypatch.setattr(
        parent, "record", lambda self, snapshot: calls.append(snapshot.physics_step)
    )
    c = object.__new__(base.AcquisitionCoordinator)
    c.series = SimpleNamespace(observe_step=lambda **kw: observed.append(kw["physics_step"]))
    for n in range(4):
        c.record(SimpleNamespace(episode_id="e", physics_step=n, sim_time_s=n / 240))
    assert observed == [0, 1, 2, 3]
    assert calls == [0, 3]


@pytest.mark.parametrize("fail", [False, True])
def test_full_capture_state_is_recorded_without_second_camera_delegate(monkeypatch, fail):
    m = pilot()
    base = m.configured_runner({"selected_steps": [0], "expected_physics_steps": 4806})
    parent = base.CaptureAdapter.__mro__[1]
    calls = []

    def original(self):
        calls.append(1)
        self.last_capture = {"before_guard": "g", "after_guard": "g"}
        if fail:
            raise ValueError("camera")
        return Observation(), ["h", "h"]

    monkeypatch.setattr(parent, "__call__", original)
    adapter = object.__new__(base.CaptureAdapter)
    source = state()["camera_state"]
    adapter.backend = SimpleNamespace(
        _episode_id="e",
        total_physics_steps=0,
        get_sim_time=lambda: 0.0,
        _operation_camera_state=lambda: source,
    )
    if fail:
        with pytest.raises(ValueError, match="camera"):
            adapter()
    else:
        adapter()
    assert calls == [1]
    full = adapter.last_capture["full_capture_state"]
    assert len(full["camera_state"]["qpos"]) == 37
    assert len(full["camera_state"]["qvel"]) == 33
    assert full["physics_step"] == 0
    assert adapter.last_capture["before_guard"] == adapter.last_capture["after_guard"] == "g"
    assert adapter.last_capture["truth_scope"] == "OFFLINE_CAPTURE_STATE_ONLY_NEVER_DECODER_INPUT"


@pytest.mark.parametrize("final_step", [4805, 4806, 4807])
def test_real_factory_frozen_201_step_horizon_retains_deviations(tmp_path, final_step):
    m = pilot()
    header = json.loads((HERE / "pilot-protocol/header.json").read_text())
    base = m.configured_runner(header)
    selected = tuple(header["selected_steps"])
    current = [0]

    class CPUObservation:
        episode_id = "cpu-range-only"

        def __init__(self, n):
            self.sim_time_s = n / 240
            self.observation_id = f"cpu-{n}"
            self.checksum_sha256 = "cpu-fixture"

        def model_dump_json(self):
            return json.dumps({"observation_id": self.observation_id})

    def capture():
        return CPUObservation(current[0]), ["same", "same"]

    directory = tmp_path / "sparse"
    recorder = base.StepRGBDRecorder(
        directory,
        capture,
        episode_id=CPUObservation.episode_id,
        max_sample_gap_s=header["original_max_sample_gap_s"],
    )
    for n in range(final_step + 1):
        current[0] = n
        recorder.observe_step(
            episode_id=CPUObservation.episode_id, physics_step=n, sim_time_s=n / 240
        )
        if n in selected:
            recorder.record_step(
                episode_id=CPUObservation.episode_id, physics_step=n, sim_time_s=n / 240
            )
    summary = recorder.finish(final_step=final_step, final_sim_time_s=final_step / 240)
    rows = [json.loads(line) for line in (directory / "index.jsonl").read_text().splitlines()]
    callbacks = [r for r in rows if r["event"] == "PHYSICAL_CALLBACK"]
    reached = [n for n in selected if n <= final_step]
    assert [r["physics_step"] for r in callbacks] == list(range(final_step + 1))
    assert summary["allocated_steps"] == summary["saved_steps"] == reached
    assert summary["physical_callbacks"] == summary["physical_callback_attempts"] == final_step + 1
    assert summary["final_step"] == final_step
    assert summary["planned_selected_steps"] == list(selected)
    assert len(list((directory / "frames").glob("*.json.gz"))) == len(reached)
    assert summary["status"] == ("COMPLETE" if final_step == 4806 else "INCOMPLETE")
    assert summary["recipe_range_status"] == ("MATCH" if final_step == 4806 else "RECIPE_DEVIATION")


@pytest.mark.parametrize(
    "field,value",
    [
        ("expected_physics_steps", 4807),
        ("expected_physics_steps", True),
        ("expected_physics_steps_is_admission_gate", False),
    ],
)
def test_range_policy_rejects_before_source_or_runtime_loading(field, value):
    m = pilot()
    header = {"expected_physics_steps": 4806, "expected_physics_steps_is_admission_gate": True}
    m.require_range_policy(header)
    header[field] = value
    with pytest.raises(RuntimeError, match="frozen original"):
        m.source_preflight(None, header, Path("must-not-be-read"))
