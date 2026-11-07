"""Pixel/proprioception bootstrap and exact registration; no engine initialization."""

import copy
from datetime import datetime

import pytest

from cloud_edge_robot_arm.research.native_calibration_collection import (
    BASE_SHA,
    MARKED_ASSET,
    MARKED_SHA,
    ROOT,
)
from cloud_edge_robot_arm.research.native_collection_grounding import (
    collection_unknown_row,
    geometry_registration,
    validate_camera,
)
from cloud_edge_robot_arm.vision.native_calibration import NativeGeometryRegistration
from cloud_edge_robot_arm.vision.top_grasp import CURRENT_GRASP_PROFILE, calibration_asset_sha256


def test_marked_scene_and_base_gripper_remain_separate():
    geometry = geometry_registration()
    assert geometry["asset_path"] == MARKED_ASSET
    assert geometry["pose_marker"]["marked_asset_sha256"] == MARKED_SHA
    assert calibration_asset_sha256(CURRENT_GRASP_PROFILE) == BASE_SHA != MARKED_SHA
    assert geometry["camera"]["calibration_version"] == "f33940579c533afe"
    NativeGeometryRegistration(geometry).validate_asset(ROOT)


def test_camera_mismatch_cannot_be_registered_from_a_new_frame():
    from tests.test_visual_owner_registration import values

    observation = values()["online"].observation
    with pytest.raises(ValueError, match="preregistered"):
        validate_camera(observation, geometry_registration())


def test_grounder_has_no_truth_or_instance_inputs():
    import inspect

    from cloud_edge_robot_arm.research import native_collection_grounding as module

    text = inspect.getsource(module)
    assert "current_physics_observation" not in text
    assert "instance_ids" not in text
    assert "get_object_pose" not in text
    assert "_resolved_parameters" in text and "bind_step_grounding" in text


@pytest.mark.parametrize("name", ["object_lifted", "object_stable"])
def test_lift_depth_gap_retained_only_after_full_h_and_proprioception(name):
    data = dict(
        phase="POST",
        skill="LIFT",
        condition=name,
        verdict=dict(status="UNKNOWN", reasons=["visual_fact_not_boolean"]),
        facts={name: dict(value=None, reasons=["calibrated_depth_error_bound_missing"])},
        holding=True,
        tcp_reached=True,
        full_horizon=True,
        nominal_release=False,
        released=False,
        tracker_has_no_held=True,
        depth_bound_missing=True,
    )
    assert collection_unknown_row(**data) == "POST_LIFT_DEPTH"
    original = copy.deepcopy(data)
    for field in ("holding", "tcp_reached", "full_horizon"):
        assert collection_unknown_row(**(data | {field: False})) is None
    assert data == original
    data["facts"][name]["reasons"] = ["effect_evidence_incomplete"]
    assert collection_unknown_row(**data) is None


def test_grounding_originals_roundtrip_and_write_failure_prevents_dispatch(monkeypatch):
    from types import SimpleNamespace

    from cloud_edge_robot_arm.contracts import ExecutionCheckpoint
    from cloud_edge_robot_arm.research import native_collection_grounding as module
    from cloud_edge_robot_arm.research.native_calibration_collection import digest
    from cloud_edge_robot_arm.research.raw_episode_v3 import _owner_decode
    from cloud_edge_robot_arm.vision.owner_registration import (
        DeterministicGroundingPolicy,
        GroundingFrameInputs,
        StepGroundingBinding,
    )
    from tests.test_visual_owner_registration import values

    data = values()

    class FixedTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return data["now"]

    monkeypatch.setattr(module, "datetime", FixedTime)
    monkeypatch.setattr(
        module, "collection_grounding_inputs", lambda *a, **kw: data["grounding_inputs"]
    )
    tracker = SimpleNamespace(
        facts=lambda observation, state: data["online"].visual_facts,
        last_binding_evaluated_at=data["now"],  # SOFTWARE_ONLY API fixture
    )
    saved = []
    kwargs = dict(
        index=0,
        observation=data["online"].observation,
        state=data["online"].robot_state,
        tracker=tracker,
        evidence={},
        geometry={},
    )
    contract, step, binding, online, checkpoint = module.grounded_collection_step(
        data["original"], **kwargs, evidence_sink=saved.append
    )
    row = saved[0]
    assert row["source_generation"] == digest(dict(data["original"].source_hashes))
    assert GroundingFrameInputs(**row["inputs"]).digest() == row["inputs_sha256"]
    assert DeterministicGroundingPolicy(**row["policy"]).digest() == row["policy_sha256"]
    assert _owner_decode(StepGroundingBinding, row["binding"]).digest() == binding.digest()
    assert ExecutionCheckpoint.model_validate(row["checkpoint"]) == checkpoint
    assert row["binding_now"] == data["now"].isoformat()
    assert row["grounded_step"] == step.model_dump(mode="json")
    assert row["executed_contract"] == contract.model_dump(mode="json")
    assert row["online"]["context_hash"] == online.context_hash
    dispatched = []

    def failed_sink(row):
        raise OSError("original sink full")

    with pytest.raises(OSError, match="sink full"):
        result = module.grounded_collection_step(
            data["original"], **kwargs, evidence_sink=failed_sink
        )
        dispatched.append(result)
    assert not dispatched


def _registration_pixels(name, when, *, marker=True, region=True, changed=False, sim_time=0.5):
    """SOFTWARE_ONLY registered camera pixels; no engine or claimed physical state."""
    import base64
    import io

    import numpy as np
    from PIL import Image

    from cloud_edge_robot_arm.vision.observations import RGBDObservation
    from tests.test_pose_marker_evidence import BITS7

    image = np.full((240, 320, 3), 255, dtype=np.uint8)
    image[112:128, 152:168] = (220, 30, 30)
    if region:
        image[60:86, 119:146] = (30, 200, 30)
    if marker:
        glyph = np.asarray(
            Image.fromarray(BITS7).resize((10, 10), resample=Image.Resampling.NEAREST)
        )
        image[115:125, 175:185] = glyph[:, :, None]
    if changed:
        image[1, 1] = (200, 200, 200)
    output = io.BytesIO()
    Image.fromarray(image).save(output, format="PNG")
    depths = np.full((240, 320), 1.4, dtype="<f4")
    depths[112:128, 152:168] = 1.33
    depths[60:86, 119:146] = 1.396
    depths[112:128, 172:188] = 1.32995
    return RGBDObservation(
        frame_id=name,
        captured_at=when,
        sim_time_s=sim_time,
        rgb_png_base64=base64.b64encode(output.getvalue()).decode(),
        depth_float32_base64=base64.b64encode(depths.tobytes()).decode(),
        episode_id="SOFTWARE_ONLY_R446",
        **geometry_registration()["camera"],
    )


def _registration_case(monkeypatch, tmp_path):
    from datetime import UTC, timedelta
    from types import SimpleNamespace

    from cloud_edge_robot_arm.research import native_collection_application as app_module
    from cloud_edge_robot_arm.research import native_collection_grounding as grounding
    from cloud_edge_robot_arm.research.native_calibration_collection import (
        digest,
        load_json,
        save_exclusive,
        source_inventory,
    )
    from cloud_edge_robot_arm.research.native_full_horizon_originals import _Audit
    from cloud_edge_robot_arm.research.native_full_horizon_recorder import NativeFullHorizonRecorder
    from cloud_edge_robot_arm.vision import tracking
    from cloud_edge_robot_arm.vision.worker_owner import WorkerLeaseObservation
    from tests.test_visual_owner_registration import values

    t0 = datetime(2026, 11, 7, tzinfo=UTC)
    clock = [t0 + timedelta(seconds=1.25)]

    class FixedTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock[0]

    monkeypatch.setattr(grounding, "datetime", FixedTime)
    monkeypatch.setattr(app_module, "datetime", FixedTime)
    monkeypatch.setattr(tracking, "datetime", FixedTime)
    b = _registration_pixels("B", t0 + timedelta(seconds=1))
    e = _registration_pixels("E", t0 + timedelta(seconds=3))
    lease = WorkerLeaseObservation(
        "software-job",
        "software-run",
        "software-worker",
        "software-lease",
        1,
        t0,
        t0 + timedelta(seconds=1.5),
        t0 + timedelta(seconds=60),
        "a" * 64,
        "b" * 64,
        "c" * 64,
    )
    geometry = geometry_registration()
    sources = source_inventory()
    owner = dict(
        issued_at=t0,
        deadline_at=t0 + timedelta(seconds=1800),
        task_id=lease.job_id,
        plan_id="software-plan",
        lease=lease,
        role_sha256="d" * 64,
    )
    args = dict(
        assignment={"assignment_id": "software-r446"},
        current_owner=owner,
        geometry=geometry,
        source_hashes=sources,
        observation=b,
    )
    protocol = dict(geometry=geometry, source_generation=digest(sources))
    domain = {"scope": "SOFTWARE_ONLY_CLOCK"}
    brackets = {
        name: dict(domain=domain, lower_ns=i * 100, upper_ns=i * 100 + 1)
        for i, name in enumerate(("B", "E"), 1)
    }
    tmp_path.mkdir(parents=True, exist_ok=True)

    class Recorder:
        record_grounding = NativeFullHorizonRecorder.record_grounding
        record_shield_config = NativeFullHorizonRecorder.record_shield_config
        check_shield = NativeFullHorizonRecorder.check_shield

        def __init__(self):
            self.inventory, self.frames = {}, {"B": b, "E": e}
            self.current, self.capture_calls = "B", 0
            self.fail, self.advance = None, False
            self.decisions, self.grounding_sources = [], {}
            self.shield_config_source, self.source_hashes = None, sources
            for name, obs in self.frames.items():
                self._write_original(name + ".json", obs.model_dump(mode="json"))

        def _write_original(self, name, value):
            if self.fail == name:
                raise OSError("software original write failure")
            save_exclusive(tmp_path / name, value)
            from hashlib import sha256

            sha = sha256((tmp_path / name).read_bytes()).hexdigest()
            self.inventory[name] = dict(sha256=sha)
            return sha

        def acquisition_source(self):
            name = self.current + ".json"
            return dict(
                acquisition_id=self.current, path=name, sha256=self.inventory[name]["sha256"]
            )

        def current_capture(self):
            return self.current, None, brackets[self.current]

        def capture(self):
            self.capture_calls += 1
            if self.fail == "capture":
                raise OSError("software capture failure")
            self.current = "E"
            if self.advance:
                live.backend.total_physics_steps += 1
            return self.frames["E"]

    recorder = Recorder()
    live = SimpleNamespace(
        original=None,
        recorder=recorder,
        backend=SimpleNamespace(total_physics_steps=120),
        tracker=None,
        grounding_evidence=None,
        origin={"software": True},
        deadline={"deadline_ns": 10**12},
    )

    state = values()["online"].robot_state
    live.robot = SimpleNamespace(get_state=lambda: state)
    consumptions, serial = [], [0]
    task_origin = ["SOFTWARE_ONLY", 0, t0.isoformat()]

    def consume():
        # Synthetic monotonic readings, deliberately unrelated to the UTC epoch.
        aid = recorder.current
        serial[0] = max(serial[0] + 10, brackets[aid]["upper_ns"] + 10)
        current = dict(domain=domain, lower_ns=serial[0], upper_ns=serial[0] + 1)
        row = dict(
            acquisition_id=aid,
            capture=brackets[aid],
            step=live.backend.total_physics_steps,
            consumed=dict(domain=domain, lower_ns=serial[0] + 2, upper_ns=serial[0] + 3),
            live_owner=dict(
                lease=lease.to_payload() | {"observed_at": clock[0].isoformat()},
                task_origin=task_origin,
                current=current,
                original_deadline_ns=10**12,
            ),
        )
        consumptions.append(row)
        return row

    tracker, evidence = app_module._record_bootstrap_tracker(
        live,
        b,
        protocol,
        purpose="BOOTSTRAP_B",
        name="tracker-clock/bootstrap.json",
        consume_capture=consume,
    )
    live.tracker, live.grounding_evidence = tracker, evidence
    recorder._write_original("bootstrap.json", evidence)
    clock[0] = t0 + timedelta(seconds=2)
    original = grounding.build_collection_contract(**args)
    live.original = original
    clock[0] = t0 + timedelta(seconds=4)

    def audit():
        value = _Audit(protocol, {}, tmp_path)
        value.directory = tmp_path
        value.manifest = {"files": recorder.inventory}
        value.original, value.domain, value.deadline = original, domain, 10**12
        value.identity = SimpleNamespace(owner_identity=original.identity)
        value.frames = {n: {"step": 120} for n in ("B", "E")}
        value.raw = dict(
            frame_sources={n: n + ".json" for n in ("B", "E")},
            operational_events=[dict(acquisition_id=n, bracket=brackets[n]) for n in ("B", "E")],
            decisions=[dict(inputs=dict(capture=dict(acquisition_id="E")))],
        )
        value.actions = [dict(capture_acquisition_id="E")]
        source = dict(
            origin=live.origin,
            deadline=live.deadline,
            source=dict(lease=lease.to_payload(), task_origin=task_origin),
        )

        def read(name):
            if name == "source-binding.json":
                return source
            if name == "capture-consumptions.json":
                return consumptions
            return load_json(tmp_path / name)

        value.read = read
        # Chronology and pixel replay only, never a physics/source certificate.
        value.frame = lambda aid: (
            recorder.frames[aid],
            {"capture_source": {"role": "REGISTERED_ACTION_BOUNDARY"}},
            {},
        )
        return value

    return SimpleNamespace(
        live=live,
        protocol=protocol,
        b=b,
        e=e,
        lease=lease,
        clock=clock,
        original=original,
        state=state,
        consume=consume,
        consumptions=consumptions,
        args=args,
        audit=audit,
        module=grounding,
        app=app_module,
        root=tmp_path,
    )


def test_original_registration_requires_new_first_dispatch_frame(monkeypatch, tmp_path):
    import numpy as np

    from cloud_edge_robot_arm.research.native_calibration_collection import canonical, load_json
    from cloud_edge_robot_arm.vision.pose_markers import PoseMarkerRegistration, detect_pose_marker

    c = _registration_case(monkeypatch, tmp_path)
    marker_registration = PoseMarkerRegistration(**c.protocol["geometry"]["pose_marker"])
    for observation in (c.b, c.e):
        marker = detect_pose_marker(observation, marker_registration)
        assert marker.status == "OBSERVED" and marker.observed_marker_ids == (7,)
        assert marker.measured_min_side_px >= 8
        assert all(0.045 * 0.7 <= edge <= 0.045 * 1.3 for edge in marker.measured_edge_lengths_m)
        assert marker.geometric_error_bound_m is None and marker.stability_status == "UNKNOWN"
        corners = np.asarray(marker.ordered_corners_px)
        depths = np.asarray(observation.depth_values()).reshape(240, 320)
        for x, y in (*corners, corners.mean(axis=0)):
            u, v = round(float(x)), round(float(y))
            assert np.all(depths[v - 1 : v + 2, u - 1 : u + 2] == float(np.float32(1.32995)))
    facts = c.live.tracker.facts(c.e, c.state)
    assert "capture_not_new_and_monotonic" in facts["target_visible"]["reasons"]
    with pytest.raises(ValueError, match="deadline"):
        c.module.grounded_collection_step(
            c.original,
            index=0,
            observation=c.b,
            state=c.state,
            tracker=c.live.tracker,
            evidence=c.live.grounding_evidence,
            geometry=c.protocol["geometry"],
        )
    old_tracker, original_digest = c.live.tracker, c.original.digest()
    returned = c.app._handoff_registered_capture(
        c.live, c.b, c.lease, c.protocol, consume_capture=c.consume
    )
    assert returned is c.e and c.live.tracker is not old_tracker
    for _ in range(2):
        assert c.live.tracker.facts(c.e, c.state)["target_visible"]["value"] is True
    _, _, binding, _, _ = c.module.grounded_collection_step(
        c.original,
        index=0,
        observation=c.e,
        state=c.state,
        tracker=c.live.tracker,
        evidence=c.live.grounding_evidence,
        geometry=c.protocol["geometry"],
    )
    assert binding.observation_id == c.e.observation_id
    tracker, evidence = c.audit().registration_bootstraps()
    assert canonical(evidence) == canonical(c.live.grounding_evidence)
    assert (
        tracker.facts_at(c.e, c.state, evaluated_at=c.clock[0])["target_visible"]["value"] is True
    )
    assert c.original.digest() == original_digest and c.live.backend.total_physics_steps == 120
    assert c.live.recorder.capture_calls == 1
    audit = c.audit()
    read = audit.read
    swapped = load_json(tmp_path / "registration-timeline.json")
    swapped["bootstrap"]["acquisition"], swapped["dispatch"]["acquisition"] = (
        swapped["dispatch"]["acquisition"],
        swapped["bootstrap"]["acquisition"],
    )
    audit.read = lambda name: swapped if name == "registration-timeline.json" else read(name)
    with pytest.raises(ValueError, match="handoff acquisition"):
        audit.registration_bootstraps()


def test_registration_handoff_rejects_backdating_and_stale_capture(monkeypatch, tmp_path):
    from datetime import timedelta

    for case in (
        "backdate",
        "reuse",
        "stale",
        "future",
        "capture",
        "write",
        "step",
        "marker",
        "region",
    ):
        c = _registration_case(monkeypatch, tmp_path / case)
        if case == "backdate":
            c.clock[0] = c.lease.observed_at - timedelta(microseconds=1)
            with pytest.raises(ValueError, match="source time"):
                c.module.build_collection_contract(**c.args)
            continue
        if case == "reuse":
            c.live.recorder.frames["E"] = c.b
        elif case == "stale":
            c.clock[0] = c.e.captured_at + timedelta(seconds=5)
        elif case == "future":
            c.clock[0] = c.e.captured_at - timedelta(microseconds=1)
        elif case == "capture":
            c.live.recorder.fail = "capture"
        elif case == "write":
            c.live.recorder.fail = "registration-timeline.json"
        elif case == "step":
            c.live.recorder.advance = True
        elif case in ("marker", "region"):
            c.live.recorder.frames["E"] = _registration_pixels(
                "E", c.e.captured_at, marker=case != "marker", region=case != "region"
            )
        before = c.live.tracker
        with pytest.raises((ValueError, OSError)):
            c.app._handoff_registered_capture(
                c.live, c.b, c.lease, c.protocol, consume_capture=c.consume
            )
        assert c.live.tracker is before and c.live.recorder.capture_calls == 1
        assert not (c.root / "registration-timeline.json").exists()
        assert (c.root / "bootstrap.json").is_file() and (c.root / "B.json").is_file()
        if case == "write":
            assert (c.root / "dispatch-bootstrap.json").is_file()
    c = _registration_case(monkeypatch, tmp_path / "changed-repeat")
    c.app._handoff_registered_capture(c.live, c.b, c.lease, c.protocol, consume_capture=c.consume)
    changed = _registration_pixels("E", c.e.captured_at, changed=True)
    assert (
        "reused_frame_with_changed_payload"
        in c.live.tracker.facts(changed, c.state)["target_visible"]["reasons"]
    )
    later = _registration_pixels("later", c.e.captured_at + timedelta(seconds=1))
    assert (
        "capture_not_new_and_monotonic"
        in c.live.tracker.facts(later, c.state)["target_visible"]["reasons"]
    )
