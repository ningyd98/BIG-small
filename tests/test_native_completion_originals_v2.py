"""Original-byte CPU diagnostics, never a complete-horizon or live-source receipt."""

import base64
import hashlib
import json
from dataclasses import FrozenInstanceError, asdict, replace
from importlib import import_module, util
from math import sqrt

import pytest

from cloud_edge_robot_arm.contracts import Pose, RobotState, SkillName
from cloud_edge_robot_arm.edge.evidence.conditions import OnlineEvidenceSnapshot
from cloud_edge_robot_arm.research.native_geometry_calibration import (
    rebuild_owner_binding,
    required_capture_source_paths,
)
from cloud_edge_robot_arm.research.raw_episode_v3 import _camera_hash, _digest
from cloud_edge_robot_arm.vision.native_calibration import (
    NativeCalibrationRegistration,
    _json,
    required_native_source_paths,
)
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from tests.test_native_calibration_source import ASSET, ASSET_SHA, ROOT, geometry, owner_originals
from tests.test_pose_marker_evidence import observation as marker_observation
from tests.test_raw_episode_v3 import fixture as raw_fixture
from tests.test_raw_episode_v3 import state

MODULE = "cloud_edge_robot_arm.research.native_completion_originals"


def api():
    assert util.find_spec(MODULE) is not None, "missing production original completion adapter"
    return import_module(MODULE)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")


def refresh(root, registry):
    registry["original_file_hashes"] = {
        str(p.relative_to(root)): sha(p)
        for p in sorted(root.rglob("*"))
        if p.is_file() and p.name != "registry.json"
    }
    save(root / "registry.json", registry)
    return NativeCalibrationRegistration(root, ROOT, "registry.json", sha(root / "registry.json"))


def write_frames(case, envelope, records):
    for frame in records["frames"]:
        obs = frame["observation_payload"]
        if obs is None:
            continue
        obs["checksum_sha256"] = ""
        observation = RGBDObservation.model_validate(obs)
        frame["observation_payload"] = observation.model_dump(mode="json")
        files = {}
        for name, field in (
            ("rgb.png", "rgb_png_base64"),
            ("depth.f32", "depth_float32_base64"),
            ("mask.u8", "valid_mask_base64"),
        ):
            encoded = getattr(observation, field)
            if encoded is None:
                continue
            relative = f"frames/{frame['acquisition_id']}/{name}"
            target = case / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(base64.b64decode(encoded))
            files[relative] = sha(target)
        frame["file_hashes"] = files
        envelope["original_file_hashes"].update(files)
        for join in records["joins"]:
            if join["acquisition_id"] == frame["acquisition_id"]:
                join["checksum_sha256"] = observation.checksum_sha256


def originals(root, *, skill="MOVE_ABOVE", drift=0.0):
    """Independently specified truth and pixels; no decoder output defines the oracle."""
    envelope, records = raw_fixture()
    values, owner = owner_originals()
    owner_source = "src/cloud_edge_robot_arm/vision/owner_registration.py"
    sources = {p: sha(ROOT / p) for p in (*required_capture_source_paths(), owner_source)}
    contract = values["original"].contract.model_copy(deep=True)
    contract.task_target.object_id = "object"
    contract.task_target.target_region_id = "target_region"
    for step in contract.steps:
        step.parameters = {"object_id": "object"}
    contract.steps[0].skill = SkillName(skill)
    requirements = {
        step.step_id: replace(
            values["original"].requirements[step.step_id],
            _original_step_json=_json(step.model_dump(mode="json")),
            preconditions=tuple(
                replace(c, target_id="object")
                for c in values["original"].requirements[step.step_id].preconditions
            ),
            postconditions=tuple(
                replace(c, target_id="object")
                for c in values["original"].requirements[step.step_id].postconditions
            ),
            policy_source_hashes={owner_source: sources[owner_source]},
        )
        for step in contract.steps
    }
    original = replace(
        values["original"],
        _contract_json=_json(contract.model_dump(mode="json")),
        requirements=requirements,
        source_hashes=sources,
        compiler_source_hashes={owner_source: sources[owner_source]},
    )
    identity = replace(envelope.identity, asset_hash=ASSET_SHA, source_hashes=sources)
    descriptor = replace(
        envelope.clock_descriptor, source_hashes={owner_source: sources[owner_source]}
    )
    intervals = tuple(
        replace(
            row,
            identity=identity,
            start=replace(row.start, descriptor_hash=descriptor.digest()),
            end=replace(row.end, descriptor_hash=descriptor.digest()) if row.end else None,
        )
        for row in records.intervals
    )
    snapshots = {n: state(n) for n in range(122)}
    snapshots[121]["object_position_m"][0] += drift
    snapshots[121]["object_geom_position_m"][0] += drift
    physics = tuple(
        replace(
            row,
            identity=identity,
            previous_state_hash=_digest(snapshots[row.physics_step - 1]),
            post_state_payload=snapshots[row.physics_step],
        )
        for row in records.physics
    )
    frames = []
    for old in records.frames:
        payload = marker_observation().model_dump(mode="json")
        for key in ("frame_id", "observation_id", "captured_at", "sim_time_s", "episode_id"):
            payload[key] = old.observation_payload[key]
        payload["intrinsics"] = [47 / 0.045, 47 / 0.045, 79.5, 79.5]
        payload["camera_to_world"][3] = 0.303
        payload["camera_to_world"][7] = 0.1
        payload["camera_to_world"][11] = 1.07505
        payload["checksum_sha256"] = ""
        obs = RGBDObservation.model_validate(payload)
        step = 120 if old.acquisition_id == "before" else 121
        camera = json.loads(_json(old.camera_state_payload))
        camera["qpos"][9:12] = snapshots[step]["object_position_m"]
        frames.append(
            replace(
                old,
                identity=identity,
                observation_payload=obs.model_dump(mode="json"),
                camera_state_payload=camera,
                pass_state_hashes=(_camera_hash(camera),) * 3,
                joined_physics_observation_hash=_digest(snapshots[step]),
            )
        )
    before = RGBDObservation.model_validate_json(_json(frames[0].observation_payload))
    scope = geometry({k: before.model_dump(mode="json")[k] for k in geometry()["camera"]})
    owner["original"] = original.to_payload()
    owner["grounding_policy"]["source_hashes"] = {owner_source: sources[owner_source]}
    owner["grounding_inputs"].update(
        observation_id=before.observation_id,
        observation_checksum_sha256=before.checksum_sha256,
        episode_id=before.episode_id,
        calibration_version=before.calibration_version,
        grasp_tcp={"x": 0.203, "y": 0.1, "z": 0.05},
        destination=dict(zip("xyz", scope["region_world_m"], strict=True)),
        support_height_m=scope["support_height_m"],
        source_hashes={owner_source: sources[owner_source]},
    )
    online = OnlineEvidenceSnapshot(
        before,
        RobotState(tcp_pose=Pose(x=0.2, y=0.1, z=0.16), gripper_open=True, connected=True),
        {},
        original.contract.plan_version,
        original.contract.command_seq,
        values["source_checkpoint"].checkpoint_hash,
    )
    binding = (
        rebuild_owner_binding(owner, online, now=values["now"])
        if skill in {"MOVE_ABOVE", "APPROACH"}
        else None
    )
    result = json.loads(_json(records.actions[0].returned_result))
    result.update(action_type=skill, success=True, error_code=None)
    action = replace(
        records.actions[0],
        identity=identity,
        original_plan=original,
        grounding=binding,
        returned_result=result,
        executed_step_payload=(
            binding.grounded_step if binding else original.requirements["move"].original_step
        ).model_dump(mode="json"),
    )
    records = replace(
        records,
        intervals=intervals,
        physics=physics,
        commands=tuple(replace(row, identity=identity) for row in records.commands),
        actions=(action,),
        frames=tuple(frames),
        joins=tuple(replace(row, identity=identity) for row in records.joins),
    )
    envelope = replace(
        envelope,
        identity=identity,
        clock_descriptor=descriptor,
        terminal_state_payload=snapshots[121],
    )
    ep, raw = envelope.to_payload(), records.to_payload()
    ep["original_file_hashes"] = {}
    case = root / "case"
    write_frames(case, ep, raw)
    save(case / "envelope.json", ep)
    save(case / "records.json", raw)
    save(case / "owner.json", owner)
    registry = {
        "schema_version": "native.calibration.registry.v1",
        "calibration_id": "software-observed-endpoint",
        "source_scope": "SOFTWARE_ONLY",
        "recipe": "FULL_RIGID_GEOMETRY_AND_TERMINAL_JOINT_V1",
        "coverage": 0.9,
        "preregistered_at": "2026-01-01T00:00:00+00:00",
        "geometry": scope,
        "supported_actions": {"MOVE_ABOVE": 10.0},
        "support": {
            "object_center_min_m": [-1, -1, -1],
            "object_center_max_m": [1, 1, 1],
            "endpoint_min_m": [-1, -1, -1],
            "endpoint_max_m": [1, 1, 1],
            "min_marker_side_px": 8.0,
        },
        "source_hashes": {
            p: sha(ROOT / p) for p in {*required_native_source_paths(), *sources, ASSET}
        },
        "groups": [
            {
                "group_id": "group-1",
                "directory": "case",
                "envelope_path": "case/envelope.json",
                "records_path": "case/records.json",
                "owner_inputs_paths": {"span-1": "case/owner.json"},
                "split": "calibration",
                "prior_usage": ["UNVIEWED"],
                "ancestor_ids": ["software-original-1"],
                "clock_reference_path": None,
            }
        ],
        "original_file_hashes": {},
    }
    return refresh(root, registry), registry


def read_case(root):
    return (
        json.loads((root / "case/envelope.json").read_text()),
        json.loads((root / "case/records.json").read_text()),
        json.loads((root / "case/owner.json").read_text()),
    )


def rewrite_case(root, registry, envelope, records, owner):
    save(root / "case/envelope.json", envelope)
    save(root / "case/records.json", records)
    save(root / "case/owner.json", owner)
    return refresh(root, registry)


def result(root, **kwargs):
    module = api()
    registration, _ = originals(root, **kwargs)
    return module.reconstruct_observed_completion_v2(registration)


def test_original_adapter_api_is_present():
    assert callable(api().reconstruct_observed_completion_v2)


def test_decoded_move_originals_match_independent_oracle(tmp_path):
    group = result(tmp_path).groups[0]
    action = group.actions[0]
    assert group.raw_status == "COMPLETE", group.raw_reasons
    assert group.utc_mapping == "UNAVAILABLE"
    assert group.geometric_error_m == pytest.approx(0.003, abs=1e-8)
    assert [f.status for f in group.frames] == ["OBSERVED", "OBSERVED"]
    assert action.command_points_m[0] == pytest.approx((0.203, 0.1, 0.16), abs=1e-8)
    assert action.capture_reference_points_m[0] == pytest.approx((0.2, 0.1, 0.16))
    assert (action.capture_step, action.dispatch_step, action.return_step) == (120, 120, 121)
    assert action.observed_steps == 1
    metric = action.observed_endpoint_metric
    assert metric is not None, action.reasons
    assert (metric.u_m, metric.l_m, metric.m_m) == pytest.approx((0.003, 0.003, 0))
    assert metric.completion_error_m == pytest.approx(0.006)
    assert metric.endpoint_error_m == pytest.approx(0)


def test_decoded_approach_uses_contact_without_clearance(tmp_path):
    action = result(tmp_path, skill="APPROACH").groups[0].actions[0]
    metric = action.observed_endpoint_metric
    assert metric is not None, action.reasons
    assert action.command_points_m[0] == pytest.approx((0.203, 0.1, 0.05), abs=1e-8)
    assert metric.u_m == pytest.approx(0.003)
    assert metric.l_m == pytest.approx(sqrt(0.003**2 + 0.11**2))
    assert metric.m_m == 0
    assert metric.completion_error_m == pytest.approx(0.003 + sqrt(0.003**2 + 0.11**2))
    assert metric.endpoint_error_m == pytest.approx(0.11)


def test_original_truth_drift_changes_metric_not_command(tmp_path):
    action = result(tmp_path, drift=0.004).groups[0].actions[0]
    metric = action.observed_endpoint_metric
    assert metric is not None, action.reasons
    assert action.command_points_m[0] == pytest.approx((0.203, 0.1, 0.16))
    assert (metric.geometric_error_m, metric.u_m, metric.l_m, metric.m_m) == pytest.approx(
        (0.003, 0.003, 0.003, 0.004)
    )
    assert metric.completion_error_m == pytest.approx(0.010)
    assert metric.endpoint_error_m == pytest.approx(0.004)


@pytest.mark.parametrize(
    "change", ["rgb", "depth", "records", "owner", "missing", "symlink", "registry"]
)
def test_changed_or_missing_actual_files_are_rejected(tmp_path, change):
    module = api()
    registration, _ = originals(tmp_path)
    path = (
        tmp_path
        / {
            "rgb": "case/frames/before/rgb.png",
            "depth": "case/frames/before/depth.f32",
            "records": "case/records.json",
            "owner": "case/owner.json",
            "missing": "case/frames/before/rgb.png",
            "symlink": "case/frames/before/rgb.png",
            "registry": "registry.json",
        }[change]
    )
    if change in {"missing", "symlink"}:
        path.unlink()
        if change == "symlink":
            path.symlink_to(tmp_path / "case/frames/after/rgb.png")
    else:
        path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError):
        module.reconstruct_observed_completion_v2(registration)


@pytest.mark.parametrize(
    "change", ["state_join", "duplicate_before", "executed", "owner", "rebound_grasp"]
)
def test_rehashed_graph_and_owner_contradictions_are_unavailable(tmp_path, change):
    module = api()
    _, registry = originals(tmp_path)
    envelope, records, owner = read_case(tmp_path)
    if change == "state_join":
        records["frames"][0]["joined_physics_observation_hash"] = "f" * 64
    elif change == "duplicate_before":
        join = dict(records["joins"][0], record_seq=records["joins"][-1]["record_seq"] + 1)
        records["joins"].append(join)
    elif change == "executed":
        records["actions"][0]["executed_step_payload"]["parameters"]["target_pose"]["x"] += 0.02
    else:
        owner["grounding_inputs"]["grasp_tcp"]["x"] += 0.02
        if change == "rebound_grasp":
            observation = RGBDObservation.model_validate(
                records["frames"][0]["observation_payload"]
            )
            online = OnlineEvidenceSnapshot(
                observation,
                RobotState(tcp_pose=Pose(x=0.2, y=0.1, z=0.16), gripper_open=True, connected=True),
                {},
                owner["original"]["contract"]["plan_version"],
                owner["original"]["contract"]["command_seq"],
                owner["source_checkpoint"]["checkpoint_hash"],
            )
            from datetime import datetime

            binding = rebuild_owner_binding(
                owner,
                online,
                now=datetime.fromisoformat(records["actions"][0]["grounding"]["created_at"]),
            )
            records["actions"][0]["grounding"] = binding.to_payload()
            records["actions"][0]["executed_step_payload"] = binding.grounded_step.model_dump(
                mode="json"
            )
    registration = rewrite_case(tmp_path, registry, envelope, records, owner)
    group = module.reconstruct_observed_completion_v2(registration).groups[0]
    assert group.allocated_action_span_ids == ("span-1",)
    assert group.actions[0].observed_endpoint_metric is None
    assert group.actions[0].reasons


@pytest.mark.parametrize("change", ["missing", "blank", "duplicate_marker", "camera"])
def test_unknown_or_missing_allocated_frame_poison_geometry(tmp_path, change):
    module = api()
    _, registry = originals(tmp_path)
    envelope, records, owner = read_case(tmp_path)
    if change == "missing":
        records["frames"].pop()
    else:
        frame = records["frames"][1]
        if change == "camera":
            frame["observation_payload"]["intrinsics"][0] += 1
        else:
            other = marker_observation(duplicate=change == "duplicate_marker")
            if change == "blank":
                import io

                from PIL import Image

                buffer = io.BytesIO()
                Image.new("RGB", (160, 160), "white").save(buffer, format="PNG")
                frame["observation_payload"]["rgb_png_base64"] = base64.b64encode(
                    buffer.getvalue()
                ).decode()
            else:
                frame["observation_payload"]["rgb_png_base64"] = other.rgb_png_base64
        write_frames(tmp_path / "case", envelope, records)
    registration = rewrite_case(tmp_path, registry, envelope, records, owner)
    group = module.reconstruct_observed_completion_v2(registration).groups[0]
    assert group.allocated_acquisition_ids == ("before", "after")
    assert len(group.frames) == 2
    assert group.geometric_error_m is None
    assert group.actions[0].observed_endpoint_metric is None


@pytest.mark.parametrize(
    "change", ["capture_age", "missing_after", "duplicate_after", "return_step"]
)
def test_capture_and_return_joins_are_exact(tmp_path, change):
    module = api()
    _, registry = originals(tmp_path)
    envelope, records, owner = read_case(tmp_path)
    if change == "missing_after":
        records["joins"].pop()
    elif change == "duplicate_after":
        records["joins"].append(
            dict(records["joins"][-1], record_seq=records["joins"][-1]["record_seq"] + 1)
        )
    else:
        acquisition = "acq-before" if change == "capture_age" else "acq-after"
        for interval in records["intervals"]:
            if interval["interval_id"] == acquisition:
                interval["start_step"] -= 1
                interval["end_step"] -= 1
                interval["start_sim_time_s"] -= 1 / 240
                interval["end_sim_time_s"] -= 1 / 240
    registration = rewrite_case(tmp_path, registry, envelope, records, owner)
    action = module.reconstruct_observed_completion_v2(registration).groups[0].actions[0]
    assert action.observed_endpoint_metric is None
    assert action.reasons


@pytest.mark.parametrize(
    "change",
    [
        "failed",
        "partial",
        "missing",
        "GRASP",
        "LIFT",
        "MOVE_TO_REGION",
        "PLACE",
        "RELEASE",
        "RETREAT",
    ],
)
def test_failed_partial_missing_and_unsupported_actions_are_retained(tmp_path, change):
    module = api()
    _, registry = originals(tmp_path, skill=change if change.isupper() else "MOVE_ABOVE")
    envelope, records, owner = read_case(tmp_path)
    if change == "failed":
        records["actions"][0]["returned_result"].update(
            success=False, error_code="ORIGINAL_FAILURE"
        )
    elif change == "partial":
        records["actions"][0].update(
            disposition="PARTIAL", returned_result=None, error="interrupted"
        )
    elif change == "missing":
        records["actions"] = []
    registration = rewrite_case(tmp_path, registry, envelope, records, owner)
    group = module.reconstruct_observed_completion_v2(registration).groups[0]
    assert group.allocated_action_span_ids == ("span-1",)
    assert len(group.actions) == 1
    action = group.actions[0]
    assert action.observed_endpoint_metric is None
    assert action.qualified_completion_metric is None
    assert action.qualification == "UNKNOWN"
    assert action.reasons
    if change == "failed":
        assert action.returned_success is False
        assert action.disposition == "RETURNED"
    if change == "missing":
        assert action.skill is action.returned_success is action.disposition is None
    if change == "RELEASE":
        assert any("PLACE" in reason for reason in action.reasons)


def test_dt_and_non_authority_fields_are_immutable(tmp_path):
    view = result(tmp_path)
    group, action = view.groups[0], view.groups[0].actions[0]
    assert group.physics_dt_s == 1 / 240
    assert action.observed_steps == 1
    for item in (view, group, action):
        assert (item.evidence_scope, item.native_authority, item.qualification) == (
            "SOFTWARE_ONLY",
            "UNAVAILABLE",
            "UNKNOWN",
        )
        with pytest.raises(FrozenInstanceError):
            item.qualification = "VALID"
        with pytest.raises(ValueError):
            replace(item, native_authority="VALID")
        assert not hasattr(item, "full_horizon_steps")
        assert not hasattr(item, "geometric_error_bound_m")
        assert not hasattr(item, "reference_motion_bound_m_s")
    assert action.qualified_completion_metric is None
    with pytest.raises(ValueError):
        replace(action, qualified_completion_metric=action.observed_endpoint_metric)


def test_groups_and_returned_data_preserve_original_allocations(tmp_path):
    module = api()
    registration, registry = originals(tmp_path)
    registry["groups"].append(
        {
            **registry["groups"][0],
            "group_id": "group-2",
            "ancestor_ids": ["software-original-2"],
            "owner_inputs_paths": {},
        }
    )
    registration = refresh(tmp_path, registry)
    view = module.reconstruct_observed_completion_v2(registration)
    assert tuple(group.group_id for group in view.groups) == ("group-1", "group-2")
    assert view.groups[0].actions[0].observed_endpoint_metric is not None
    assert view.groups[1].actions[0].observed_endpoint_metric is None
    assert view.groups[1].ancestor_ids == ("software-original-2",)
    copied = asdict(view)
    copied["groups"][0]["actions"][0]["reasons"] = ("caller",)
    assert "caller" not in view.groups[0].actions[0].reasons
    assert not hasattr(view, "joint_bound_m")
    with pytest.raises(ValueError):
        (tmp_path / "case/owner.json").write_text("{}")
        module.reconstruct_observed_completion_v2(registration)
