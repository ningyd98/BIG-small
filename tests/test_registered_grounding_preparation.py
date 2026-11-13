"""Production preparation and strict current readout, using disposable source records."""

import importlib.util
import json
import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from cloud_edge_robot_arm.contracts import SkillName
from cloud_edge_robot_arm.edge.evidence import conditions
from cloud_edge_robot_arm.edge.recovery.lifecycle import checkpoint_digest
from cloud_edge_robot_arm.research import native_calibration_collection as protocol_api
from cloud_edge_robot_arm.research import native_collection_application as application
from cloud_edge_robot_arm.research import native_full_horizon_originals as reader
from cloud_edge_robot_arm.research.native_calibration_collection import digest, load_json
from cloud_edge_robot_arm.simulation_runtime.models import RuntimeJobStatus
from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import SQLiteSimulationJobRepository
from cloud_edge_robot_arm.vision import owner_registration as owner
from cloud_edge_robot_arm.vision import registered_object_tracking, tracking, worker_owner
from tests.test_registered_object_geometry import frame, revised
from tests.test_registered_object_tracking import later
from tests.test_visual_owner_registration import values

ROOT = Path(__file__).resolve().parents[1]


def context(tmp_path, monkeypatch, skill=SkillName.MOVE_ABOVE):
    repository = SQLiteSimulationJobRepository(tmp_path / "source.db")
    job = repository.create_job(
        run_id="registered-source",
        batch_id="",
        backend="MUJOCO",
        scenario_id="S01_NORMAL_STATIC",
        control_mode="CLOUD",
        seed=0,
        manifest_id="software",
        reproducibility_hash="a" * 64,
        draft={},
        timeout_seconds=120,
        max_attempts=1,
        artifact_root="software",
        source_commit="software",
        source_tree_hash="b" * 64,
    )
    repository.update_status_cas(
        job.job_id,
        expected=RuntimeJobStatus.CREATED,
        next_status=RuntimeJobStatus.QUEUED,
        reason_code="software",
        worker_id="",
        lease_id="",
    )
    lease = repository.acquire_lease(
        worker_id="registered-worker", backend="MUJOCO", lease_ttl_seconds=60
    )
    assert lease is not None
    repository.start_attempt(job.job_id, worker_id=lease.worker_id)
    for old, new in (
        (RuntimeJobStatus.LEASED, RuntimeJobStatus.STARTING),
        (RuntimeJobStatus.STARTING, RuntimeJobStatus.RUNNING),
    ):
        assert repository.update_status_cas(
            job.job_id,
            expected=old,
            next_status=new,
            reason_code="software",
            worker_id=lease.worker_id,
            lease_id=lease.lease_id,
            expected_lease_id=lease.lease_id,
        )
    stamp = datetime.now(UTC)
    clock = [stamp]

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            assert tz is UTC
            return clock[0]

    for module in (application, reader, registered_object_tracking, tracking, worker_owner):
        monkeypatch.setattr(module, "datetime", Clock)
    ref, _ = frame()
    ref = revised(ref, captured_at=stamp)
    current = later(ref, fragment=True)
    protocol = tmp_path / "protocol"
    protocol_api.prepare_registered_grounding_protocol(output=protocol)
    registration = protocol_api.read_protocol(protocol)
    lease_source = worker_owner.read_visual_worker_lease(
        repository,
        job_id=job.job_id,
        run_id=job.run_id,
        worker_id=lease.worker_id,
        lease_id=lease.lease_id,
    )
    before = values()
    contract = before["original"].contract
    step = contract.steps[0].model_copy(
        update={"skill": skill, "parameters": {"object_id": "object"}}, deep=True
    )
    target = contract.task_target.model_copy(
        update={"object_id": "object", "target_region_id": "target_region"}
    )
    contract = contract.model_copy(
        update={
            "steps": [step],
            "task_target": target,
            "timestamp": stamp,
            "issued_at": stamp,
            "valid_until": stamp + timedelta(seconds=40),
        },
        deep=True,
    )
    identity = lease_source.identity(
        episode_id=ref.episode_id,
        task_id=contract.task_id,
        plan_id="registered-plan",
        robot_id="registered-robot",
    )
    original = worker_owner.compile_worker_original_plan(
        lease_source=lease_source,
        identity=identity,
        contract=contract,
        observation=ref,
        proposal_hash="b" * 64,
        role_bundle_hash="c" * 64,
        source_hashes=registration["source_hashes"],
        registered_at=stamp,
        task_deadline_at=stamp + timedelta(seconds=35),
        verification_deadline_at=stamp + timedelta(seconds=30),
    )
    state = before["online"].robot_state
    cp = before["source_checkpoint"].model_copy(
        update={
            "plan_id": identity.plan_id,
            "robot_id": identity.robot_id,
            "pending_step_ids": ["move"],
            "created_at": stamp,
            "updated_at": stamp,
            "robot_state": state.model_dump(mode="json"),
            "checkpoint_hash": "",
        },
        deep=True,
    )
    cp = cp.model_copy(update={"checkpoint_hash": checkpoint_digest(cp)})
    clock[0] = current.captured_at
    args = dict(
        repository=repository,
        original=original,
        source_checkpoint=cp,
        reference_observation=ref,
        observation=current,
        robot_state=state,
        owner_revision=1,
        state_generation=2,
    )
    return protocol, args, clock


def v2_region_observation(reference, mode="foreground", *, index=1):
    """生成内部遮挡或反例；不修改参考帧和历史像素。"""
    import base64
    import io

    import numpy as np
    from PIL import Image

    current = later(reference, index=index, fragment=True)
    with Image.open(io.BytesIO(base64.b64decode(current.rgb_png_base64))) as image:
        rgb = np.array(image)
    depth = np.asarray(current.depth_values(), dtype="<f4").reshape(240, 320).copy()
    if mode != "full":
        rgb[169:172, 108:112] = (255, 255, 255)
        depth[169:172, 108:112] = {
            "zero": 0.0,
            "repaint": 1.4,
            "behind": 1.5,
            "nan": float("nan"),
        }.get(mode, 1.3)
    if mode == "boundary":
        rgb[160:180, 100] = (255, 255, 255)
    if mode == "moved":
        rgb[160:180, 100:120] = (255, 255, 255)
        rgb[160:180, 101:121] = (0, 255, 0)
    if mode == "ambiguous":
        rgb[190:205, 130:145] = (0, 255, 0)
    output = io.BytesIO()
    Image.fromarray(rgb).save(output, format="PNG")
    return revised(
        current,
        rgb_png_base64=base64.b64encode(output.getvalue()).decode(),
        depth_float32_base64=base64.b64encode(depth.tobytes()).decode(),
        valid_mask_base64=None,
    )


def v2_preview_environment(tmp_path, monkeypatch):
    from cloud_edge_robot_arm.research import native_collection_grounding as collection
    from tests.test_registered_object_tracking import environment

    _, ref, reg, root, hashes, clock = environment(tmp_path, monkeypatch)
    monkeypatch.setattr(collection, "datetime", registered_object_tracking.datetime)
    bootstrap = getattr(collection, "bootstrap_registered_collection_tracker_v2", None)
    assert callable(bootstrap), "v2 occlusion tracker missing"
    tracker = bootstrap(ref, reg, source_root=root, source_hashes=hashes)
    return collection, tracker, ref, reg, root, hashes, clock, values()["online"].robot_state


def test_v2_preview_full_and_internal_foreground_gap(tmp_path, monkeypatch):
    module, tracker, ref, _, _, _, clock, state = v2_preview_environment(tmp_path, monkeypatch)
    full = v2_region_observation(ref, "full")
    clock[0] = full.captured_at
    normal = module.registered_collection_grounding_preview_v2(tracker, full, state)
    current = v2_region_observation(ref, index=2)
    clock[0] = current.captured_at
    partial = module.registered_collection_grounding_preview_v2(tracker, current, state)
    assert normal.status == partial.status == "DERIVED"
    assert partial.destination_world_m == normal.destination_world_m
    assert partial.object_surface_visibility == "UNKNOWN"
    assert partial.geometric_error_bound_m is partial.region_geometric_error_bound_m is None
    proof = partial.to_payload()["region_evidence"]
    assert proof["status"] == "PARTIAL_FOREGROUND_SUPPORTED"
    assert proof["visible_pixels"] == 388 and proof["missing_pixels"] == 12
    assert proof["reference_observation_id"] == ref.observation_id
    assert proof["reference_observation_checksum_sha256"] == ref.checksum_sha256
    assert proof["current_observation_id"] == current.observation_id
    assert proof["current_observation_checksum_sha256"] == current.checksum_sha256
    assert proof["placement_clearance"] == "UNKNOWN"
    proof["visible_pixels"] = 0
    assert partial.to_payload()["region_evidence"]["visible_pixels"] == 388
    assert normal.to_payload()["region_evidence"]["status"] == "FULL"


@pytest.mark.parametrize(
    "problem",
    [
        "zero",
        "nan",
        "repaint",
        "behind",
        "boundary",
        "moved",
        "ambiguous",
        "camera",
        "expired",
        "future",
        "source",
    ],
)
def test_v2_preview_rejects_unsupported_region(tmp_path, monkeypatch, problem):
    module, tracker, ref, _, root, hashes, clock, state = v2_preview_environment(
        tmp_path, monkeypatch
    )
    if problem == "nan":
        with pytest.raises(ValueError):
            v2_region_observation(ref, problem)
        return
    current = v2_region_observation(ref, problem)
    clock[0] = current.captured_at
    if problem == "camera":
        current = revised(current, calibration_version="foreign")
    elif problem == "expired":
        clock[0] += timedelta(seconds=5)
    elif problem == "future":
        clock[0] -= timedelta(seconds=1)
    elif problem == "source":
        path = root / next(iter(hashes))
        path.write_bytes(path.read_bytes() + b"\n")
        with pytest.raises(ValueError):
            module.registered_collection_grounding_preview_v2(tracker, current, state)
        return
    preview = module.registered_collection_grounding_preview_v2(tracker, current, state)
    assert preview.status == "UNKNOWN"
    assert preview.grasp_tcp_world_m is None and preview.destination_world_m is None


@pytest.mark.parametrize("fault", ["missing", "foreign", "duplicate", "zero_depth"])
def test_v2_marker_failure_never_reuses_pose(tmp_path, monkeypatch, fault):
    module, tracker, ref, _, _, _, clock, state = v2_preview_environment(tmp_path, monkeypatch)
    first = v2_region_observation(ref)
    clock[0] = first.captured_at
    assert (
        module.registered_collection_grounding_preview_v2(tracker, first, state).status == "DERIVED"
    )
    current = later(ref, index=2, fault=fault)
    clock[0] = current.captured_at
    unknown = module.registered_collection_grounding_preview_v2(tracker, current, state)
    assert unknown.status == "UNKNOWN" and unknown.object_center_world_m is None
    assert unknown.grasp_tcp_world_m is None


@pytest.mark.parametrize(
    "age,expected", [(0, "DERIVED"), (4.999, "DERIVED"), (5, "UNKNOWN"), (-0.01, "UNKNOWN")]
)
def test_v2_preview_strict_entry_age_preserves_success_anchor(tmp_path, monkeypatch, age, expected):
    module, tracker, ref, _, _, _, clock, state = v2_preview_environment(tmp_path, monkeypatch)
    first = v2_region_observation(ref)
    clock[0] = first.captured_at
    assert (
        module.registered_collection_grounding_preview_v2(tracker, first, state).status == "DERIVED"
    )
    provider = tracker._provider
    anchors = (provider._last_successful_observation, provider._last_successful_geometry)
    real_update = provider.update
    calls = []

    def update(observation):
        calls.append(observation.observation_id)
        return real_update(observation)

    monkeypatch.setattr(provider, "update", update)
    current = v2_region_observation(ref, index=2)
    clock[0] = current.captured_at + timedelta(seconds=age)
    result = module.registered_collection_grounding_preview_v2(tracker, current, state)
    assert result.status == expected
    if expected == "UNKNOWN":
        assert calls == []
        assert provider._last_successful_observation is anchors[0]
        assert provider._last_successful_geometry is anchors[1]
        assert result.track.wrapper_freshness == "REJECTED"
        assert result.grasp_tcp_world_m is result.destination_world_m is None
        assert result.to_payload()["region_evidence"] is None


@pytest.mark.parametrize("delay", ["region", "source", "source_error"])
def test_v2_preview_rechecks_after_slow_work_and_restores_anchor(tmp_path, monkeypatch, delay):
    module, tracker, ref, _, _, _, clock, state = v2_preview_environment(tmp_path, monkeypatch)
    first = v2_region_observation(ref)
    clock[0] = first.captured_at
    assert (
        module.registered_collection_grounding_preview_v2(tracker, first, state).status == "DERIVED"
    )
    provider = tracker._provider
    anchors = (provider._last_successful_observation, provider._last_successful_geometry)
    current = v2_region_observation(ref, index=2)
    clock[0] = current.captured_at
    if delay == "region":
        real_region = module._registered_region_evidence_v2

        def region(*args, **kwargs):
            result = real_region(*args, **kwargs)
            clock[0] = current.captured_at + timedelta(seconds=5)
            return result

        monkeypatch.setattr(module, "_registered_region_evidence_v2", region)
    else:
        real_check = provider._recheck_current

        def recheck(observation):
            result = real_check(observation)
            if provider._last_successful_observation.observation_id == current.observation_id:
                if delay == "source_error":
                    raise ValueError("synthetic source verification failed after update")
                clock[0] = current.captured_at + timedelta(seconds=5)
            return result

        monkeypatch.setattr(provider, "_recheck_current", recheck)
    if delay == "source_error":
        with pytest.raises(ValueError, match="source verification failed"):
            module.registered_collection_grounding_preview_v2(tracker, current, state)
    else:
        result = module.registered_collection_grounding_preview_v2(tracker, current, state)
        assert result.status == "UNKNOWN" and result.evaluated_at == clock[0]
        assert result.track.wrapper_freshness == "REJECTED"
        assert (
            result.grasp_tcp_world_m
            is result.object_center_world_m
            is result.destination_world_m
            is None
        )
        assert (
            result.destination_observation_id
            is result.destination_observation_checksum_sha256
            is None
        )
        assert result.to_payload()["region_evidence"] is None
    assert provider._last_successful_observation is anchors[0]
    assert provider._last_successful_geometry is anchors[1]


@pytest.mark.parametrize("rotation", [0, 1])
@pytest.mark.parametrize("shift", [(0.0, 0.0), (-0.15, 0.2)])
def test_r643_registered_box_depth_attribution(tmp_path, monkeypatch, rotation, shift):
    import numpy as np

    from cloud_edge_robot_arm.research import native_collection_grounding as collection
    from cloud_edge_robot_arm.vision.registered_objects import derive_registered_object_geometry
    from tests.test_registered_object_tracking import environment

    _, ref, reg, root, hashes, _ = environment(tmp_path, monkeypatch)
    parser = getattr(collection, "_registered_opaque_primitives_v1", None)
    assert callable(parser), "registered opaque primitive parser missing"
    primitives = parser(reg, source_root=root, source_hashes=hashes)
    payload = primitives.to_payload()
    assert len(payload["boxes"]) == 38
    assert {b["name"] for b in payload["boxes"]} >= {
        "object_geom",
        "pose_marker_outboard_v3_quiet",
        "pose_marker_outboard_v3_r0c0",
    }
    geometry = derive_registered_object_geometry(ref, reg)
    center = np.asarray(geometry.object_center_world_m) + (shift[0], shift[1], 0.0)
    r = np.array(
        ((1, 0, 0), (0, 1, 0), (0, 0, 1)) if rotation == 0 else ((0, -1, 0), (1, 0, 0), (0, 0, 1)),
        dtype=float,
    )
    geometry = replace(
        geometry,
        object_center_world_m=tuple(center),
        rotation_object_to_world=tuple(r.ravel()),
        grasp_tcp_world_m=tuple(center + (0, 0, 0.01)),
    )
    camera = np.asarray(ref.camera_to_world).reshape(4, 4)
    fx, fy, cx, cy = ref.intrinsics
    probes = [(0.0, 0.0, 0.035), (0.045, 0.1, 0.03503), (0.0, 0.1, 0.03505)]
    pixels = []
    for point in probes:
        world = center + r @ np.asarray(point)
        optical = camera[:3, :3].T @ (world - camera[:3, 3])
        pixels.append(
            (round(cx + fx * optical[0] / optical[2]), round(cy + fy * optical[1] / optical[2]))
        )
    depths = collection._registered_model_depth_v1(ref, geometry, primitives, pixels + [(0, 0)])
    # Horizontal faces give these independent literal local heights under either yaw.
    expected = [camera[2, 3] - center[2] - h for h in (0.035, 0.03503, 0.03505)]
    assert depths[:3] == pytest.approx(expected, abs=1e-10)
    assert np.isinf(depths[3])
    copied = primitives.to_payload()
    copied["boxes"][0]["half_extent_m"][0] = 99
    assert primitives.to_payload()["boxes"][0]["half_extent_m"] == [0.035, 0.035, 0.035]


def prepare(tmp_path, monkeypatch, skill=SkillName.MOVE_ABOVE):
    protocol, args, clock = context(tmp_path, monkeypatch, skill)
    app = application.RegisteredGroundingPreparationApplication.from_protocol(
        protocol, source_root=ROOT
    )
    output = tmp_path / "prepared"
    result = app.prepare_step(**args, output=output)
    record = output / "prepared-step.json"
    return protocol, args, clock, result, record


def test_application_protocol_and_consumer_api_exist():
    assert hasattr(protocol_api, "prepare_registered_grounding_protocol"), "v6 protocol missing"
    assert hasattr(application, "RegisteredGroundingPreparationApplication"), (
        "preparation application missing"
    )


@pytest.mark.parametrize("skill", [SkillName.MOVE_ABOVE, SkillName.APPROACH])
def test_application_real_joined_source_prepares_without_promoting_visibility(
    tmp_path, monkeypatch, skill
):
    protocol, args, _, result, record = prepare(tmp_path, monkeypatch, skill)
    p = protocol_api.read_protocol(protocol)
    assert p["schema_version"] == "native.calibration.operational.v6"
    assert p["assignments"] == [] and p["released_assignments"] == []
    assert all(value == 0 for value in p["authorized_actual_budget"].values())
    assert result["status"] == "PREPARED_CANDIDATE" and result["execution_admitted"] is False
    payload = load_json(record)["content"]
    admission = payload["admission"]
    assert admission["candidate_ready"] is True and admission["execution_admitted"] is False
    assert admission["unknown_allowance_rows"] == []
    assert admission["pose_verdict"]["status"] == "PASS"
    visible = next(v for v in admission["preconditions"] if v["condition_name"] == "target_visible")
    reachable = next(
        v for v in admission["preconditions"] if v["condition_name"] == "target_reachable"
    )
    assert visible["status"] == reachable["status"] == "UNKNOWN"
    assert "protocol_prepare_only_not_released" in admission["blockers"]
    assert payload["binding"]["grounded_step"]["skill"] == skill.value
    grasp_z = payload["inputs"]["grasp_tcp_world_m"][2]
    expected_z = max(0.16, grasp_z + 0.10) if skill == SkillName.MOVE_ABOVE else grasp_z
    assert payload["binding"]["grounded_step"]["parameters"]["target_pose"]["z"] == expected_z
    assert args["repository"].get_job(args["original"].identity.job_id).attempt == 1
    assert not (protocol / "claims").exists()


@pytest.mark.parametrize("change", ["budget", "release", "schema", "extra", "basis"])
def test_application_protocol_rejects_resealed_authority_and_downgrade(tmp_path, change):
    output = tmp_path / "protocol"
    protocol_api.prepare_registered_grounding_protocol(output=output)
    payload = load_json(output / "protocol.json")
    if change == "budget":
        payload["authorized_actual_budget"]["teacher"] = 1
    elif change == "release":
        payload["execution_release"] = "RELEASED"
    elif change == "schema":
        payload["schema_version"] = "native.calibration.operational.v2"
    elif change == "basis":
        payload["geometry_basis"] = "MEASURED"
    else:
        payload["extra"] = True
    (output / "protocol.json").write_text(json.dumps(payload))
    with pytest.raises((ValueError, TypeError)):
        protocol_api.read_protocol(output)


@pytest.mark.parametrize("fault", ["missing", "incomplete", "left_cut"])
def test_application_unavailable_region_retains_unknown_without_candidate(
    tmp_path, monkeypatch, fault
):
    protocol, args, clock = context(tmp_path, monkeypatch)
    current = later(
        args["reference_observation"], region="missing" if fault == "missing" else "incomplete"
    )
    if fault == "left_cut":
        from tests.test_registered_object_tracking import cut_region

        current = cut_region(args["reference_observation"], "left")
    args["observation"] = current
    clock[0] = current.captured_at
    app = application.RegisteredGroundingPreparationApplication.from_protocol(
        protocol, source_root=ROOT
    )
    output = tmp_path / "unknown"
    result = app.prepare_step(**args, output=output)
    payload = load_json(output / "prepared-step.json")["content"]
    assert result["status"] == "PREPARATION_UNKNOWN"
    assert payload["inputs"] is None and payload["binding"] is None
    assert payload["preview"]["grasp_tcp_world_m"] is None
    assert payload["admission"]["candidate_ready"] is False


def test_application_refuses_cancelled_source_before_output(tmp_path, monkeypatch):
    protocol, args, _ = context(tmp_path, monkeypatch)
    args["repository"].request_cancel(args["original"].identity.job_id)
    app = application.RegisteredGroundingPreparationApplication.from_protocol(
        protocol, source_root=ROOT
    )
    output = tmp_path / "never"
    with pytest.raises(ValueError):
        app.prepare_step(**args, output=output)
    assert not output.exists()


def test_application_old_factory_and_old_condition_registry_still_refuse(tmp_path):
    protocol = tmp_path / "protocol"
    protocol_api.prepare_registered_grounding_protocol(output=protocol)
    output = tmp_path / "never"
    with pytest.raises(ValueError, match="prepare-only"):
        application.NativeCollectionApplication.from_startup(
            protocol, assignment_id="none", output=output
        )
    assert not output.exists() and not (protocol / "claims").exists()


@pytest.mark.parametrize("failure", ["cancel", "expiry", "write"])
def test_application_checks_final_boundaries_and_does_not_return_success(
    tmp_path, monkeypatch, failure
):
    from cloud_edge_robot_arm.research import native_collection_grounding as grounding

    protocol, args, clock = context(tmp_path, monkeypatch)
    original_preview = grounding.registered_collection_grounding_preview_v1

    def changed_after_preview(*a, **kw):
        result = original_preview(*a, **kw)
        if failure == "cancel":
            args["repository"].request_cancel(args["original"].identity.job_id)
        elif failure == "expiry":
            clock[0] += timedelta(seconds=5.01)
        return result

    monkeypatch.setattr(
        grounding, "registered_collection_grounding_preview_v1", changed_after_preview
    )
    if failure == "write":

        def failed_write(*a, **kw):
            raise OSError("disposable output unavailable")

        monkeypatch.setattr(application, "save_exclusive", failed_write)
    app = application.RegisteredGroundingPreparationApplication.from_protocol(
        protocol, source_root=ROOT
    )
    with pytest.raises((ValueError, OSError)):
        app.prepare_step(**args, output=tmp_path / "refused")
    assert not (tmp_path / "refused/prepared-step.json").exists()


def test_application_pose_only_inputs_do_not_change_legacy_conditions(tmp_path, monkeypatch):
    _, args, _, _, record = prepare(tmp_path, monkeypatch)
    payload = load_json(record)["content"]
    online = conditions.OnlineEvidenceSnapshot(
        args["observation"], args["robot_state"], {"target_visible": payload["inputs"]}
    )
    verdicts = conditions.evaluate_conditions(
        [
            conditions.ConditionSpec("target_visible", "object"),
            conditions.ConditionSpec("registered_object_pose_available", "object"),
        ],
        online,
        now=args["observation"].captured_at,
    )
    assert [v.status for v in verdicts] == ["UNKNOWN", "UNKNOWN"]


def test_application_alias_output_and_legacy_full_horizon_mode_refuse(tmp_path, monkeypatch):
    protocol, args, _ = context(tmp_path, monkeypatch)
    alias = tmp_path / "alias"
    alias.symlink_to(tmp_path, target_is_directory=True)
    app = application.RegisteredGroundingPreparationApplication.from_protocol(
        protocol, source_root=ROOT
    )
    with pytest.raises(ValueError):
        app.prepare_step(**args, output=alias / "never")
    with pytest.raises(ValueError, match="current-frame"):
        protocol_api.verify_native_calibration_collection(protocol, output=tmp_path / "legacy")
    assert not (tmp_path / "never").exists() and not (tmp_path / "legacy").exists()


def test_reader_api_exists():
    assert hasattr(reader, "verify_registered_prepared_step"), "strict preparation reader missing"


def test_reader_reconstructs_actual_production_record_and_legacy_decoder_refuses(
    tmp_path, monkeypatch
):
    protocol, args, _, _, record = prepare(tmp_path, monkeypatch)
    result = reader.verify_registered_prepared_step(
        protocol, record, repository=args["repository"], source_root=ROOT, output=tmp_path / "read"
    )
    assert result["status"] == "PREPARED_CANDIDATE_RECONSTRUCTED"
    assert result["execution_admitted"] is False and result["formal"] == "NOT_ACCEPTED"
    assert result["binding_sha256"] == digest(load_json(record)["content"]["binding"])
    from cloud_edge_robot_arm.research.raw_episode_v3 import _owner_decode
    from cloud_edge_robot_arm.vision.owner_registration import StepGroundingBinding

    with pytest.raises((ValueError, TypeError)):
        _owner_decode(StepGroundingBinding, load_json(record)["content"]["binding"])


@pytest.mark.parametrize(
    "change",
    [
        "candidate",
        "bound",
        "basis",
        "source",
        "checkpoint",
        "epoch",
        "policy",
        "time",
        "admission",
    ],
)
def test_reader_rejects_resealed_tampering(tmp_path, monkeypatch, change):
    protocol, args, _, _, record = prepare(tmp_path, monkeypatch)
    envelope = load_json(record)
    payload = envelope["content"]
    if change == "candidate":
        payload["binding"]["grounded_step"]["parameters"]["target_pose"]["x"] += 0.2
    elif change == "bound":
        payload["inputs"]["geometric_error_bound_m"] = 0.001
    elif change == "basis":
        payload["inputs"]["geometry_basis"] = "MEASURED"
    elif change == "source":
        payload["inputs"]["asset_sha256"] = "e" * 64
    elif change == "checkpoint":
        payload["context"]["source_checkpoint"]["command_seq"] += 1
    elif change == "epoch":
        payload["binding"]["current_identity"]["owner_epoch"] = "e" * 64
    elif change == "policy":
        payload["policy"]["clearance_m"] = 0.01
    elif change == "time":
        payload["binding"]["created_at"] = (
            args["observation"].captured_at - timedelta(seconds=1)
        ).isoformat()
    else:
        payload["admission"]["execution_admitted"] = True
    envelope["content_sha256"] = digest(payload)
    record.write_text(json.dumps(envelope))
    with pytest.raises((ValueError, TypeError)):
        reader.verify_registered_prepared_step(
            protocol,
            record,
            repository=args["repository"],
            source_root=ROOT,
            output=tmp_path / "refused",
        )
    assert not (tmp_path / "refused").exists()


def test_reader_current_expiry_refuses_without_time_rewind(tmp_path, monkeypatch):
    protocol, args, clock, _, record = prepare(tmp_path, monkeypatch)
    clock[0] = args["observation"].captured_at + timedelta(seconds=5.01)
    with pytest.raises(ValueError, match="stale|expired|fresh"):
        reader.verify_registered_prepared_step(
            protocol,
            record,
            repository=args["repository"],
            source_root=ROOT,
            output=tmp_path / "stale",
        )
    assert not (tmp_path / "stale").exists()


def test_cli_calls_protocol_prepare_and_strict_reader_in_process(tmp_path, monkeypatch, capsys):
    spec = importlib.util.spec_from_file_location(
        "registered_cli", ROOT / "scripts/collect_native_calibration.py"
    )
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    monkeypatch.setattr(
        sys,
        "argv",
        ["collect", "--prepare-registered-protocol", "--output", str(tmp_path / "cli-protocol")],
    )
    cli.main()
    assert json.loads(capsys.readouterr().out)["status"] == "REGISTERED_PROTOCOL_PREPARED"
    protocol, args, _ = context(tmp_path, monkeypatch)
    from cloud_edge_robot_arm.research.native_calibration_collection import detached

    ctx = tmp_path / "context.json"
    ctx.write_text(json.dumps({k: detached(v) for k, v in args.items() if k != "repository"}))
    common = ["--protocol", str(protocol), "--repository", str(args["repository"].database_path)]
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "collect",
            "--prepare-registered-step",
            *common,
            "--context",
            str(ctx),
            "--output",
            str(tmp_path / "cli-prepare"),
        ],
    )
    cli.main()
    assert json.loads(capsys.readouterr().out)["execution_admitted"] is False
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "collect",
            "--verify-registered-step",
            *common,
            "--prepared",
            str(tmp_path / "cli-prepare/prepared-step.json"),
            "--output",
            str(tmp_path / "cli-read"),
        ],
    )
    cli.main()
    assert json.loads(capsys.readouterr().out)["status"] == "PREPARED_CANDIDATE_RECONSTRUCTED"


@pytest.mark.parametrize("consumer", ["app", "reader"])
@pytest.mark.parametrize("limit", ["frame", "lease"])
def test_review_i1_final_join_rechecks_real_time(tmp_path, monkeypatch, consumer, limit):
    if consumer == "app":
        protocol, args, clock = context(tmp_path, monkeypatch)
        app = application.RegisteredGroundingPreparationApplication.from_protocol(
            protocol, source_root=ROOT
        )
    else:
        protocol, args, clock, _, record = prepare(tmp_path, monkeypatch)
    if limit == "lease":
        from cloud_edge_robot_arm.simulation_runtime import sqlite_repository as sqlite_source

        monkeypatch.setattr(sqlite_source, "_now", lambda: clock[0])
        args["repository"].heartbeat_lease(args["original"].identity.lease_id, lease_ttl_seconds=1)
    module = application if consumer == "app" else worker_owner
    genuine = module.read_visual_worker_lease
    calls = []

    def waiting_join(*a, **kw):
        calls.append("now" in kw)
        result = genuine(*a, **kw)
        if len(calls) == 2:
            clock[0] = (
                clock[0] + timedelta(seconds=5.01)
                if limit == "frame"
                else result.expires_at + timedelta(seconds=0.001)
            )
            if limit == "lease":
                assert (clock[0] - args["observation"].captured_at).total_seconds() < 5
        return result

    monkeypatch.setattr(module, "read_visual_worker_lease", waiting_join)
    output = tmp_path / "join-refused"
    with pytest.raises(ValueError, match="stale|expired|deadline|fresh"):
        if consumer == "app":
            app.prepare_step(**args, output=output)
        else:
            reader.verify_registered_prepared_step(
                protocol, record, repository=args["repository"], source_root=ROOT, output=output
            )
    assert not any(calls), "owning production APIs must not supply cached now to lease joins"
    assert not output.exists()


def short_original(args, *, condition_ttl=None, deadline=None):
    original = args["original"]
    changes = {}
    if condition_ttl is not None:
        requirements = {}
        for name, requirement in original.requirements.items():

            def changed(c):
                return replace(c, tolerances={**c.tolerances, "max_age_s": condition_ttl})

            requirements[name] = replace(
                requirement,
                preconditions=tuple(changed(c) for c in requirement.preconditions),
                postconditions=tuple(changed(c) for c in requirement.postconditions),
            )
        changes["requirements"] = requirements
    if deadline is not None:
        changes["verification_deadline_at"] = deadline
    args["original"] = owner.freeze_original_visual_plan(**{**original.freeze_inputs(), **changes})


@pytest.mark.parametrize(
    "boundary", ["admission", "serialization", "reader_rebuild", "reader_admission"]
)
def test_review_i1_late_validation_rechecks_deadline(tmp_path, monkeypatch, boundary):
    protocol, args, clock = context(tmp_path, monkeypatch)
    short_original(args, deadline=clock[0] + timedelta(seconds=0.15))
    app = application.RegisteredGroundingPreparationApplication.from_protocol(
        protocol, source_root=ROOT
    )
    if boundary.startswith("reader"):
        app.prepare_step(**args, output=tmp_path / "valid")
        if boundary == "reader_rebuild":
            genuine = owner.prepare_registered_step_binding
            calls = [0]

            def slow_rebuild(*a, **kw):
                result = genuine(*a, **kw)
                calls[0] += 1
                if calls[0] == 2:
                    clock[0] += timedelta(seconds=0.2)
                return result

            monkeypatch.setattr(owner, "prepare_registered_step_binding", slow_rebuild)
        else:
            genuine = application.registered_preparation_admission

            def slow_admission(*a, **kw):
                result = genuine(*a, **kw)
                clock[0] += timedelta(seconds=0.2)
                return result

            monkeypatch.setattr(application, "registered_preparation_admission", slow_admission)
    elif boundary == "admission":
        genuine = application.registered_preparation_admission

        def slow_admission(*a, **kw):
            result = genuine(*a, **kw)
            clock[0] += timedelta(seconds=0.2)
            return result

        monkeypatch.setattr(application, "registered_preparation_admission", slow_admission)
    else:
        genuine = application._registered_context_payload
        calls = [0]

        def slow_materialization(*a, **kw):
            result = genuine(*a, **kw)
            calls[0] += 1
            if calls[0] == 2:
                clock[0] += timedelta(seconds=0.2)
            return result

        monkeypatch.setattr(application, "_registered_context_payload", slow_materialization)
    output = tmp_path / "late-refused"
    with pytest.raises(ValueError, match="stale|expired|deadline|fresh"):
        if boundary.startswith("reader"):
            reader.verify_registered_prepared_step(
                protocol,
                tmp_path / "valid/prepared-step.json",
                repository=args["repository"],
                source_root=ROOT,
                output=output,
            )
        else:
            app.prepare_step(**args, output=output)
    assert not output.exists()


def test_review_i2_rejects_future_frame_before_processing_catches_up(tmp_path, monkeypatch):
    protocol, args, clock = context(tmp_path, monkeypatch)
    args["observation"] = revised(
        args["observation"], captured_at=clock[0] + timedelta(seconds=0.02)
    )
    genuine = application.read_visual_worker_lease
    calls = [0]

    def catching_up(*a, **kw):
        result = genuine(*a, **kw)
        calls[0] += 1
        if calls[0] == 1:
            clock[0] += timedelta(seconds=0.03)
        return result

    monkeypatch.setattr(application, "read_visual_worker_lease", catching_up)
    app = application.RegisteredGroundingPreparationApplication.from_protocol(
        protocol, source_root=ROOT
    )
    output = tmp_path / "future-refused"
    with pytest.raises(ValueError, match="future|fresh|deadline"):
        app.prepare_step(**args, output=output)
    assert calls[0] == 0 and not output.exists()


def authentic_unknown(tmp_path, monkeypatch, limit=None):
    protocol, args, clock = context(tmp_path, monkeypatch)
    args["observation"] = later(args["reference_observation"], region="missing")
    if limit == "ttl":
        short_original(args, condition_ttl=0.2)
    elif limit == "absolute":
        short_original(args, deadline=clock[0] + timedelta(seconds=0.2))
    app = application.RegisteredGroundingPreparationApplication.from_protocol(
        protocol, source_root=ROOT
    )
    app.prepare_step(**args, output=tmp_path / "unknown-valid")
    return protocol, args, clock, tmp_path / "unknown-valid/prepared-step.json"


def test_review_i3_authentic_unknown_reconstructs_before_deadline(tmp_path, monkeypatch):
    protocol, args, _, record = authentic_unknown(tmp_path, monkeypatch)
    result = reader.verify_registered_prepared_step(
        protocol,
        record,
        repository=args["repository"],
        source_root=ROOT,
        output=tmp_path / "unknown-read",
    )
    assert result["status"] == "PREPARATION_UNKNOWN_RECONSTRUCTED"
    assert result["execution_admitted"] is False and result["native_authority"] == "UNAVAILABLE"


@pytest.mark.parametrize("limit", ["ttl", "absolute"])
def test_review_i3_unknown_entry_deadline_refuses(tmp_path, monkeypatch, limit):
    protocol, args, clock, record = authentic_unknown(tmp_path, monkeypatch, limit)
    clock[0] += timedelta(seconds=0.21)
    output = tmp_path / "unknown-expired"
    with pytest.raises(ValueError, match="stale|expired|deadline|fresh"):
        reader.verify_registered_prepared_step(
            protocol, record, repository=args["repository"], source_root=ROOT, output=output
        )
    assert not output.exists()


def test_review_i3_unknown_final_deadline_refuses(tmp_path, monkeypatch):
    protocol, args, clock, record = authentic_unknown(tmp_path, monkeypatch, "ttl")
    genuine = worker_owner.read_visual_worker_lease
    calls = [0]

    def late_unknown_join(*a, **kw):
        result = genuine(*a, **kw)
        calls[0] += 1
        if calls[0] == 2:
            clock[0] += timedelta(seconds=0.21)
        return result

    monkeypatch.setattr(worker_owner, "read_visual_worker_lease", late_unknown_join)
    output = tmp_path / "unknown-final-expired"
    with pytest.raises(ValueError, match="stale|expired|deadline|fresh"):
        reader.verify_registered_prepared_step(
            protocol, record, repository=args["repository"], source_root=ROOT, output=output
        )
    assert not output.exists()


@pytest.mark.parametrize("value", [True, 0])
def test_review_i3_unknown_never_coerces_condition_ttl(tmp_path, monkeypatch, value):
    protocol, args, _ = context(tmp_path, monkeypatch)
    args["observation"] = later(args["reference_observation"], region="missing")
    short_original(args, condition_ttl=value)
    app = application.RegisteredGroundingPreparationApplication.from_protocol(
        protocol, source_root=ROOT
    )
    output = tmp_path / "invalid-ttl"
    with pytest.raises(ValueError):
        app.prepare_step(**args, output=output)
    assert not output.exists()


def test_review_normal_nonzero_times_are_honest_and_readable(tmp_path, monkeypatch):
    protocol, args, clock = context(tmp_path, monkeypatch)
    genuine_join = application.read_visual_worker_lease
    genuine_admission = application.registered_preparation_admission

    def nonzero_join(*a, **kw):
        clock[0] += timedelta(seconds=0.01)
        result = genuine_join(*a, **kw)
        clock[0] += timedelta(seconds=0.01)
        return result

    def nonzero_admission(*a, **kw):
        result = genuine_admission(*a, **kw)
        clock[0] += timedelta(seconds=0.01)
        return result

    monkeypatch.setattr(application, "read_visual_worker_lease", nonzero_join)
    monkeypatch.setattr(application, "registered_preparation_admission", nonzero_admission)
    app = application.RegisteredGroundingPreparationApplication.from_protocol(
        protocol, source_root=ROOT
    )
    app.prepare_step(**args, output=tmp_path / "nonzero")
    record = tmp_path / "nonzero/prepared-step.json"
    p = load_json(record)["content"]
    parse = datetime.fromisoformat
    assert (
        parse(p["started_at"])
        < parse(p["lease_before"]["observed_at"])
        < parse(p["lease_after"]["observed_at"])
        < parse(p["evaluated_at"])
        < parse(p["finished_at"])
    )
    assert p["binding"]["created_at"] == p["evaluated_at"]
    result = reader.verify_registered_prepared_step(
        protocol,
        record,
        repository=args["repository"],
        source_root=ROOT,
        output=tmp_path / "nonzero-read",
    )
    assert result["status"] == "PREPARED_CANDIDATE_RECONSTRUCTED"


def nominal_scene(tmp_path, monkeypatch, *, center=None, yaw=0):
    """Fresh pixel fixture; independent ray/triangle rasterizer, no simulator state online."""
    import base64
    import io
    import xml.etree.ElementTree as ET

    import numpy as np
    from PIL import Image

    from cloud_edge_robot_arm.research import native_collection_grounding as module
    from tests.test_registered_object_tracking import environment

    _, ref, reg, root, hashes, clock = environment(tmp_path, monkeypatch)
    monkeypatch.setattr(module, "datetime", registered_object_tracking.datetime)
    with Image.open(io.BytesIO(base64.b64decode(ref.rgb_png_base64))) as image:
        rgb = np.array(image)
    rgb[160:180, 100:120] = 255
    rgb[60:90, 118:148] = (0, 255, 0)
    depth = np.array(ref.depth_values(), dtype="<f4").reshape(ref.height, ref.width)
    depth[60:90, 118:148] = 1.396

    def encode(template, colors, depths, **changes):
        stream = io.BytesIO()
        Image.fromarray(colors).save(stream, format="PNG")
        return revised(
            template,
            rgb_png_base64=base64.b64encode(stream.getvalue()).decode(),
            depth_float32_base64=base64.b64encode(depths.astype("<f4").tobytes()).decode(),
            valid_mask_base64=None,
            **changes,
        )

    ref = encode(ref, rgb, depth)
    current_rgb = np.full_like(rgb, 255)
    current_rgb[60:90, 118:148] = (0, 255, 0)
    current_depth = np.full_like(depth, 1.4)
    current_depth[60:90, 118:148] = 1.396
    camera = np.asarray(ref.camera_to_world).reshape(4, 4)
    fx, fy, cx, cy = ref.intrinsics
    if center is None:
        center = np.array(
            [
                camera[0, 3] + (132.5 - cx) * 1.396 / fx,
                camera[1, 3] - (74.5 - cy) * 1.396 / fy,
                0.039,
            ]
        )
    center = np.asarray(center)
    rotation = np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]]) if yaw else np.eye(3)
    yy, xx = np.indices(current_depth.shape)
    rays = (
        np.stack(((xx.ravel() - cx) / fx, (yy.ravel() - cy) / fy, np.ones(xx.size)), axis=1)
        @ camera[:3, :3].T
    )
    origin = camera[:3, 3]
    nearest = np.full(xx.size, np.inf)
    colors = current_rgb.reshape(-1, 3)
    corners = np.array(
        [
            [-1, -1, -1],
            [-1, -1, 1],
            [-1, 1, -1],
            [-1, 1, 1],
            [1, -1, -1],
            [1, -1, 1],
            [1, 1, -1],
            [1, 1, 1],
        ]
    )
    faces = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    node = ET.fromstring((root / reg.to_payload()["asset_path"]).read_bytes()).find(
        ".//body[@name='object']"
    )
    for geom in node.findall("geom"):
        half = np.fromstring(geom.attrib["size"], sep=" ")
        local = np.fromstring(geom.attrib.get("pos", "0 0 0"), sep=" ")
        vertices = (corners * half + local) @ rotation.T + center
        rgba = np.fromstring(geom.attrib["rgba"], sep=" ")
        for a, b, c, d in faces:
            for indices in ((a, b, c), (a, c, d)):
                v0, v1, v2 = vertices[list(indices)]
                edge1, edge2 = v1 - v0, v2 - v0
                h = np.cross(rays, edge2)
                det = h @ edge1
                inv = np.zeros_like(det)
                np.divide(1.0, det, out=inv, where=np.abs(det) > 1e-12)
                displacement = origin - v0
                u = (h @ displacement) * inv
                q = np.cross(displacement, edge1)
                v = (rays @ q) * inv
                t = (edge2 @ q) * inv
                hit = (
                    (np.abs(det) > 1e-12)
                    & (u >= 0)
                    & (v >= 0)
                    & (u + v <= 1)
                    & (t > 0)
                    & (t < nearest)
                    & (t < current_depth.ravel())
                )
                nearest[hit] = t[hit]
                colors[hit] = np.rint(rgba[:3] * 255).astype(np.uint8)
    hits = np.isfinite(nearest)
    current_depth.ravel()[hits] = nearest[hits]
    current = encode(
        ref,
        current_rgb,
        current_depth,
        observation_id="nominal-current",
        frame_id="nominal-current",
        captured_at=ref.captured_at + timedelta(seconds=0.5),
        sim_time_s=ref.sim_time_s + 0.5,
    )
    return module, ref, current, reg, root, hashes, clock, values()["online"].robot_state


@pytest.mark.parametrize("offset_y_px", [0, 0.25])
def test_r672_nominal_quarter_turn_localization(tmp_path, monkeypatch, offset_y_px):
    module, ref, current, reg, root, hashes, clock, state = nominal_scene(
        tmp_path, monkeypatch, yaw=1
    )
    if offset_y_px:
        import numpy as np

        camera = np.asarray(ref.camera_to_world).reshape(4, 4)
        fx, fy, cx, cy = ref.intrinsics
        center = (
            camera[0, 3] + (132.5 - cx) * 1.396 / fx,
            camera[1, 3] - (74.5 - cy) * 1.396 / fy + offset_y_px * 1.396 / fy,
            0.039,
        )
        module, ref, current, reg, root, hashes, clock, state = nominal_scene(
            tmp_path / "translated", monkeypatch, center=center, yaw=1
        )
    policy = module.registered_nominal_region_policy_v1(hashes)
    tracker = module.bootstrap_registered_collection_tracker_v2(
        ref, reg, source_root=root, source_hashes=hashes, nominal_policy=policy
    )
    clock[0] = current.captured_at
    result = module.registered_collection_grounding_preview_v2(tracker, current, state)
    assert result.status == "DERIVED", result.reason
    assert result.region_evidence["maximum_model_residual_m"] == pytest.approx(
        0.008435160574, abs=1e-8
    )
    assert result.region_evidence["maximum_model_residual_m"] < policy["tau_model_m"]
    assert result.execution_allowed is False and result.native_authority == "UNAVAILABLE"
    assert result.geometric_error_bound_m is None
    assert result.region_evidence["placement_clearance"] == "UNKNOWN"


@pytest.mark.parametrize("yaw", [0, 1])
def test_r643_plate_crosses_region_boundary(tmp_path, monkeypatch, yaw):
    module, ref, current, reg, root, hashes, clock, state = nominal_scene(
        tmp_path, monkeypatch, yaw=yaw
    )
    make_policy = getattr(module, "registered_nominal_region_policy_v1", None)
    assert callable(make_policy), "source-bound nominal region policy missing"
    policy = make_policy(hashes)
    tracker = module.bootstrap_registered_collection_tracker_v2(
        ref, reg, source_root=root, source_hashes=hashes, nominal_policy=policy
    )
    clock[0] = current.captured_at
    result = module.registered_collection_grounding_preview_v2(tracker, current, state)
    assert result.status == "DERIVED", result.reason
    proof = result.region_evidence
    assert proof["status"] == "PARTIAL_REGISTERED_NOMINAL"
    assert proof["missing_boundary_pixels"] > 0
    assert proof["visible_corners"] >= 3 and all(proof["visible_sides"])
    assert proof["placement_clearance"] == "UNKNOWN"
    assert proof["geometric_error_bound_m"] is None
    assert proof["nominal_policy"] == policy


def test_r672_default_estimator_retains_quarter_turn_counterexample(tmp_path, monkeypatch):
    from cloud_edge_robot_arm.vision.registered_objects import derive_registered_object_geometry

    module, ref, current, reg, root, hashes, _, _ = nominal_scene(tmp_path, monkeypatch, yaw=1)
    baseline = derive_registered_object_geometry(current, reg)
    assert baseline == derive_registered_object_geometry(current, reg, corner_refinement="NONE")
    assert baseline.object_center_world_m == pytest.approx(
        (0.20267973932262515, 0.2447440079619855, 0.03899997348785392), abs=1e-12
    )
    policy = module.registered_nominal_region_policy_v1(hashes)
    tracker = module.bootstrap_registered_collection_tracker_v2(
        ref, reg, source_root=root, source_hashes=hashes, nominal_policy=policy
    )
    proof, reason = module._registered_region_evidence_v2(
        tracker, current, object_geometry=baseline, nominal_policy=policy
    )
    assert proof is None and reason == "registered_region_foreground_depth_mismatch"


@pytest.mark.parametrize(
    "yaw,dx,dy,expected",
    [
        (0, 0, 0, "DERIVED"),
        (0, 0.25, 0, "UNKNOWN"),
        (0, -0.25, 0, "UNKNOWN"),
        (0, 0, 0.25, "DERIVED"),
        (0, 0, -0.25, "UNKNOWN"),
        (1, 0.25, 0, "UNKNOWN"),
        (1, -0.25, 0, "UNKNOWN"),
        (1, 0, -0.25, "UNKNOWN"),
    ],
)
def test_r672_quarter_pixel_support_boundary(tmp_path, monkeypatch, yaw, dx, dy, expected):
    import numpy as np

    module, ref, current, reg, root, hashes, clock, state = nominal_scene(
        tmp_path, monkeypatch, yaw=yaw
    )
    if dx or dy:
        camera = np.asarray(ref.camera_to_world).reshape(4, 4)
        fx, fy, cx, cy = ref.intrinsics
        center = (
            camera[0, 3] + (132.5 - cx + dx) * 1.396 / fx,
            camera[1, 3] - (74.5 - cy - dy) * 1.396 / fy,
            0.039,
        )
        module, ref, current, reg, root, hashes, clock, state = nominal_scene(
            tmp_path / "translated", monkeypatch, center=center, yaw=yaw
        )
    policy = module.registered_nominal_region_policy_v1(hashes)
    tracker = module.bootstrap_registered_collection_tracker_v2(
        ref, reg, source_root=root, source_hashes=hashes, nominal_policy=policy
    )
    clock[0] = current.captured_at
    result = module.registered_collection_grounding_preview_v2(tracker, current, state)
    assert result.status == expected, result.reason
    assert result.execution_allowed is False and result.native_authority == "UNAVAILABLE"
    if expected == "UNKNOWN":
        assert result.reason == "registered_region_projection_mask_mismatch"
        assert result.region_evidence is result.destination_world_m is None
        assert result.object_center_world_m is result.grasp_tcp_world_m is None
    else:
        assert result.region_evidence["maximum_model_residual_m"] <= policy["tau_model_m"]
        assert result.region_evidence["placement_clearance"] == "UNKNOWN"


@pytest.mark.parametrize("bad", [None, "CONTOUR", True, []])
def test_r672_corner_refinement_options_are_closed(tmp_path, monkeypatch, bad):
    from cloud_edge_robot_arm.vision.pose_markers import detect_pose_marker
    from cloud_edge_robot_arm.vision.registered_objects import derive_registered_object_geometry

    _, ref, current, reg, root, hashes, _, _ = nominal_scene(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="unsupported marker corner refinement"):
        detect_pose_marker(current, reg.pose_marker, corner_refinement=bad)
    with pytest.raises(ValueError, match="unsupported marker corner refinement"):
        derive_registered_object_geometry(current, reg, corner_refinement=bad)
    with pytest.raises(ValueError, match="unsupported marker corner refinement"):
        registered_object_tracking.RegisteredObjectTrackerV1(
            ref, reg, source_root=root, source_hashes=hashes, corner_refinement=bad
        )


@pytest.mark.parametrize("fault", ["foreign", "duplicate"])
def test_r672_nominal_refinement_keeps_marker_identity_gate(tmp_path, monkeypatch, fault):
    module, ref, current, reg, root, hashes, clock, state = nominal_scene(
        tmp_path, monkeypatch, yaw=1
    )
    tracker = module.bootstrap_registered_collection_tracker_v2(
        ref,
        reg,
        source_root=root,
        source_hashes=hashes,
        nominal_policy=module.registered_nominal_region_policy_v1(hashes),
    )
    bad, _ = frame(fault=fault)
    bad = revised(
        bad,
        observation_id="bad-marker-" + fault,
        frame_id="bad-marker-" + fault,
        captured_at=current.captured_at,
        sim_time_s=current.sim_time_s,
    )
    clock[0] = bad.captured_at
    result = module.registered_collection_grounding_preview_v2(tracker, bad, state)
    assert result.status == "UNKNOWN" and result.reason == "foreign_or_ambiguous_marker"
    assert result.region_evidence is result.object_center_world_m is None
    assert result.destination_world_m is result.grasp_tcp_world_m is None
    assert result.execution_allowed is False


def test_r643_resealed_region_binding(tmp_path, monkeypatch):
    module, ref, current, reg, root, hashes, clock, state = nominal_scene(tmp_path, monkeypatch)
    tracker = module.bootstrap_registered_collection_tracker_v2(
        ref,
        reg,
        source_root=root,
        source_hashes=hashes,
        nominal_policy=module.registered_nominal_region_policy_v1(hashes),
    )
    clock[0] = current.captured_at
    preview = module.registered_collection_grounding_preview_v2(tracker, current, state)
    inputs = owner.RegisteredGroundingFrameInputsV2.from_preview(preview, current, reg)
    assert inputs.to_payload()["region_evidence"]["status"] == "PARTIAL_REGISTERED_NOMINAL"
    for change in ("threshold", "primitive", "mask", "status", "frame"):
        payload = inputs.to_payload()
        proof = payload["region_evidence"]
        if change == "threshold":
            proof["nominal_policy"]["tau_model_m"] = 0.011
        elif change == "primitive":
            proof["primitive_sha256"] = "invalid"
        elif change == "mask":
            proof["missing_pixels"] += 1
        elif change == "frame":
            proof["current_observation_checksum_sha256"] = "e" * 64
        else:
            proof["status"] = "FULL_NOMINAL"
        with pytest.raises((ValueError, TypeError)):
            owner.RegisteredGroundingFrameInputsV2.from_payload(payload)


@pytest.mark.parametrize("yaw", [0, 1])
@pytest.mark.parametrize(
    "change,expected",
    [
        ("visible_inside", "DERIVED"),
        ("visible_outside", "UNKNOWN"),
        ("foreign_depth", "UNKNOWN"),
        ("same_plane_repaint", "UNKNOWN"),
        ("lost_corners", "UNKNOWN"),
        ("zero", "UNKNOWN"),
        ("projection_hole", "UNKNOWN"),
    ],
)
def test_r643_nominal_residual_boundaries(tmp_path, monkeypatch, change, expected, yaw):
    import base64
    import io

    import numpy as np
    from PIL import Image

    module, ref, current, reg, root, hashes, clock, state = nominal_scene(
        tmp_path, monkeypatch, yaw=yaw
    )
    with Image.open(io.BytesIO(base64.b64decode(current.rgb_png_base64))) as image:
        rgb = np.array(image)
    depth = np.array(current.depth_values(), dtype="<f4").reshape(current.height, current.width)
    region = np.zeros(depth.shape, dtype=bool)
    region[60:90, 118:148] = True
    green = (rgb[:, :, 1] > 200) & (rgb[:, :, 0] < 30) & (rgb[:, :, 2] < 30)
    visible = region & green
    missing = region & ~green
    if change.startswith("visible_"):
        prior = float(np.float32(1.396))
        upper = np.float32(prior + 0.010)
        if float(upper) - prior > 0.010:
            upper = np.nextafter(upper, np.float32(-np.inf))
        depth[visible] = (
            upper if change == "visible_inside" else np.nextafter(upper, np.float32(np.inf))
        )
    elif change == "foreign_depth":
        depth[missing] -= 0.03
    elif change == "same_plane_repaint":
        depth[missing] = 1.396
    elif change == "lost_corners":
        rgb[60, 118] = rgb[60, 147] = 255
        depth[60, 118] = depth[60, 147] = 1.3
    elif change == "projection_hole":
        rgb[75, 120] = 255
        depth[75, 120] = 1.3
    else:
        depth[missing] = 0
    stream = io.BytesIO()
    Image.fromarray(rgb).save(stream, format="PNG")
    current = revised(
        current,
        rgb_png_base64=base64.b64encode(stream.getvalue()).decode(),
        depth_float32_base64=base64.b64encode(depth.tobytes()).decode(),
        valid_mask_base64=None,
    )
    tracker = module.bootstrap_registered_collection_tracker_v2(
        ref,
        reg,
        source_root=root,
        source_hashes=hashes,
        nominal_policy=module.registered_nominal_region_policy_v1(hashes),
    )
    clock[0] = current.captured_at
    result = module.registered_collection_grounding_preview_v2(tracker, current, state)
    assert result.status == expected, result.reason
    if expected == "UNKNOWN":
        assert result.region_evidence is result.destination_world_m is None


def _r675_repaint(observation, changes):
    import base64
    import io

    import numpy as np
    from PIL import Image

    with Image.open(io.BytesIO(base64.b64decode(observation.rgb_png_base64))) as image:
        rgb = np.array(image)
    for y, x, color in changes:
        rgb[y, x] = color
    stream = io.BytesIO()
    Image.fromarray(rgb).save(stream, format="PNG")
    return revised(observation, rgb_png_base64=base64.b64encode(stream.getvalue()).decode())


def _r675_scene(tmp_path, monkeypatch, *, corners=("tl",), partial=False):
    module, ref, current, reg, root, hashes, clock, state = nominal_scene(tmp_path, monkeypatch)
    points = {"tl": (60, 118), "tr": (60, 147), "bl": (89, 118), "br": (89, 147)}
    changes = [(points[name][0], points[name][1], 255) for name in corners]
    ref = _r675_repaint(ref, changes)
    if partial:
        current = _r675_repaint(current, changes)
    else:
        current = revised(
            ref,
            frame_id="r675-current-full",
            observation_id="r675-current-full",
            captured_at=ref.captured_at + timedelta(seconds=0.5),
            sim_time_s=ref.sim_time_s + 0.5,
        )
    return module, ref, current, reg, root, hashes, clock, state


@pytest.mark.parametrize("corner", [None, "tl", "tr", "bl", "br"])
def test_r675_full_measured_reference_keeps_exact_support(tmp_path, monkeypatch, corner):
    import hashlib

    import numpy as np

    module, ref, current, reg, root, hashes, clock, state = _r675_scene(
        tmp_path, monkeypatch, corners=() if corner is None else (corner,)
    )
    tracker = module.bootstrap_registered_collection_tracker_v2(
        ref,
        reg,
        source_root=root,
        source_hashes=hashes,
        nominal_policy=module.registered_nominal_region_policy_v1(hashes),
    )
    clock[0] = current.captured_at
    result = module.registered_collection_grounding_preview_v2(tracker, current, state)
    assert result.status == "DERIVED", result.reason
    proof = result.region_evidence
    expected = np.zeros((ref.height, ref.width), dtype=bool)
    expected[60:90, 118:148] = True
    if corner is not None:
        y, x = {"tl": (60, 118), "tr": (60, 147), "bl": (89, 118), "br": (89, 147)}[corner]
        expected[y, x] = False
    depth = np.asarray(ref.depth_values(), dtype="<f4").reshape(expected.shape)
    assert proof["status"] == "FULL_NOMINAL"
    assert proof["region_pixels"] == proof["visible_pixels"] == 900 - (corner is not None)
    assert proof["missing_pixels"] == 0
    assert proof["reference_region_mask_sha256"] == hashlib.sha256(expected.tobytes()).hexdigest()
    assert (
        proof["reference_region_depth_sha256"]
        == hashlib.sha256(depth[expected].tobytes()).hexdigest()
    )
    assert proof["reference_observation_checksum_sha256"] == ref.checksum_sha256
    assert result.execution_allowed is False and result.native_authority == "UNAVAILABLE"
    assert result.geometric_error_bound_m is None
    assert proof["placement_clearance"] == "UNKNOWN"
    inputs = owner.RegisteredGroundingFrameInputsV2.from_preview(result, current, reg)
    assert inputs.to_payload()["region_evidence"]["region_pixels"] == int(expected.sum())


@pytest.mark.parametrize("yaw", [0, 1])
@pytest.mark.parametrize("corner", ["tl", "tr", "bl", "br"])
def test_measured_reference_partial_keeps_exact_support(tmp_path, monkeypatch, yaw, corner):
    import hashlib

    import numpy as np

    module, ref, current, reg, root, hashes, clock, state = nominal_scene(
        tmp_path, monkeypatch, yaw=yaw
    )
    y, x = {"tl": (60, 118), "tr": (60, 147), "bl": (89, 118), "br": (89, 147)}[corner]
    ref = _r675_repaint(ref, [(y, x, 255)])
    current = _r675_repaint(current, [(y, x, 255)])
    tracker = module.bootstrap_registered_collection_tracker_v2(
        ref,
        reg,
        source_root=root,
        source_hashes=hashes,
        nominal_policy=module.registered_nominal_region_policy_v1(hashes),
    )
    clock[0] = current.captured_at
    result = module.registered_collection_grounding_preview_v2(tracker, current, state)
    assert result.status == "DERIVED", result.reason
    proof = result.region_evidence
    expected = np.zeros((ref.height, ref.width), dtype=bool)
    expected[60:90, 118:148] = True
    expected[y, x] = False
    assert proof["status"] == "PARTIAL_REGISTERED_NOMINAL"
    assert proof["region_pixels"] == 899
    assert proof["visible_pixels"] + proof["missing_pixels"] == 899
    assert proof["missing_pixels"] > 0 and proof["missing_boundary_pixels"] > 0
    assert proof["reference_region_mask_sha256"] == hashlib.sha256(expected.tobytes()).hexdigest()
    assert proof["visible_corners"] == 3 and all(proof["visible_sides"])
    assert proof["placement_clearance"] == "UNKNOWN" and proof["geometric_error_bound_m"] is None
    assert result.execution_allowed is False and result.native_authority == "UNAVAILABLE"


@pytest.mark.parametrize(
    "fault,reason",
    [
        ("restored_corner", "registered_region_extra_or_moved_color"),
        ("lost_corner", "registered_region_anchors_unavailable"),
        ("foreign_depth", "registered_region_foreground_depth_mismatch"),
        ("invalid_depth", "registered_region_current_depth_unavailable"),
        ("projection_hole", "registered_region_projection_mask_mismatch"),
    ],
)
def test_measured_partial_reference_keeps_rejection_gates(tmp_path, monkeypatch, fault, reason):
    import base64

    import numpy as np

    module, ref, current, reg, root, hashes, clock, state = _r675_scene(
        tmp_path, monkeypatch, partial=True
    )
    if fault == "restored_corner":
        current = _r675_repaint(current, [(60, 118, (0, 255, 0))])
    elif fault == "lost_corner":
        current = _r675_repaint(current, [(60, 147, 255)])
    elif fault == "projection_hole":
        assert tuple(tracking._rgb(current)[75, 120]) == (0, 255, 0)
        current = _r675_repaint(current, [(75, 120, 255)])
    else:
        depth = np.array(current.depth_values(), dtype="<f4").reshape(current.height, current.width)
        # The registered plate crosses the center of the top boundary here.
        depth[60, 132] = 0 if fault == "invalid_depth" else depth[60, 132] - 0.03
        current = revised(
            current,
            depth_float32_base64=base64.b64encode(depth.tobytes()).decode(),
            valid_mask_base64=None,
        )
    tracker = module.bootstrap_registered_collection_tracker_v2(
        ref,
        reg,
        source_root=root,
        source_hashes=hashes,
        nominal_policy=module.registered_nominal_region_policy_v1(hashes),
    )
    clock[0] = current.captured_at
    result = module.registered_collection_grounding_preview_v2(tracker, current, state)
    assert result.status == "UNKNOWN" and result.reason == reason
    assert (
        result.region_evidence is result.destination_world_m is result.object_center_world_m is None
    )


@pytest.mark.parametrize("fault", ["hole", "cropped", "degenerate", "two_corners", "zero_boundary"])
def test_r675_invalid_measured_reference_is_not_released(tmp_path, monkeypatch, fault):
    import base64

    import numpy as np

    module, ref, current, reg, root, hashes, clock, state = _r675_scene(
        tmp_path, monkeypatch, corners=("tl", "tr") if fault == "two_corners" else ()
    )
    if fault == "hole":
        ref = _r675_repaint(ref, [(70, 130, 255)])
    elif fault in {"cropped", "degenerate"}:
        changes = [(y, x, 255) for y in range(60, 90) for x in range(118, 148)]
        changes += [
            (y, x, (0, 255, 0))
            for y in range(60, 90)
            for x in (range(0, 30) if fault == "cropped" else range(125, 127))
        ]
        ref = _r675_repaint(ref, changes)
    elif fault == "zero_boundary":
        depth = np.asarray(ref.depth_values(), dtype="<f4").reshape(ref.height, ref.width)
        depth[89, 147] = 0
        ref = revised(
            ref,
            depth_float32_base64=base64.b64encode(depth.tobytes()).decode(),
            valid_mask_base64=None,
        )
    if fault != "two_corners":
        expected = {
            "hole": "region_topology_not_supported_axis_aligned_rectangle",
            "cropped": "extent_truncated_at_image_boundary",
            "degenerate": "region_topology_not_supported_axis_aligned_rectangle",
            "zero_boundary": "target_depth_incomplete",
        }[fault]
        with pytest.raises(ValueError, match=expected):
            module.bootstrap_registered_collection_tracker_v2(
                ref,
                reg,
                source_root=root,
                source_hashes=hashes,
                nominal_policy=module.registered_nominal_region_policy_v1(hashes),
            )
        return
    tracker = module.bootstrap_registered_collection_tracker_v2(
        ref,
        reg,
        source_root=root,
        source_hashes=hashes,
        nominal_policy=module.registered_nominal_region_policy_v1(hashes),
    )
    clock[0] = current.captured_at
    result = module.registered_collection_grounding_preview_v2(tracker, current, state)
    assert result.status == "UNKNOWN" and result.reason == "registered_region_anchors_unavailable"


@pytest.mark.parametrize(
    "fault",
    [
        "restored_corner",
        "extra_color",
        "disconnected",
        "missing_color",
        "zero_boundary",
        "depth_residual",
        "false_foreground",
    ],
)
def test_r675_full_support_still_checks_current_pixels_and_depth(tmp_path, monkeypatch, fault):
    import base64

    import numpy as np

    module, ref, current, reg, root, hashes, clock, state = _r675_scene(tmp_path, monkeypatch)
    tracker = module.bootstrap_registered_collection_tracker_v2(
        ref,
        reg,
        source_root=root,
        source_hashes=hashes,
        nominal_policy=module.registered_nominal_region_policy_v1(hashes),
    )
    if fault == "restored_corner":
        current = _r675_repaint(current, [(60, 118, (0, 255, 0))])
    elif fault == "extra_color":
        current = _r675_repaint(current, [(70, 148, (0, 255, 0))])
    elif fault == "disconnected":
        current = _r675_repaint(current, [(y, 132, 255) for y in range(60, 90)])
    elif fault == "missing_color":
        current = _r675_repaint(current, [(70, 130, 255)])
    elif fault == "false_foreground":

        def false_model(observation, geometry, primitives, pixels):
            model = np.full(len(pixels), np.inf)
            model[0] = 1.2
            return model

        monkeypatch.setattr(module, "_registered_model_depth_v1", false_model)
    else:
        depth = np.asarray(current.depth_values(), dtype="<f4").reshape(
            current.height, current.width
        )
        depth[89, 147] = 0 if fault == "zero_boundary" else depth[89, 147] + 0.011
        current = revised(
            current,
            depth_float32_base64=base64.b64encode(depth.tobytes()).decode(),
            valid_mask_base64=None,
        )
    clock[0] = current.captured_at
    result = module.registered_collection_grounding_preview_v2(tracker, current, state)
    assert result.status == "UNKNOWN", result.reason
    assert (
        result.object_center_world_m is result.destination_world_m is result.region_evidence is None
    )
