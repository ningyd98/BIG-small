"""Independent original-byte reconstruction tests; software fixtures only."""

import copy
import json
from dataclasses import replace
from importlib import import_module, util

import numpy as np
import pytest

from cloud_edge_robot_arm.research.native_calibration_collection import (
    CONFIG,
    ROOT,
    canonical,
    digest,
    load_json,
    prepare_native_calibration,
    read_protocol,
    save_exclusive,
)
from cloud_edge_robot_arm.research.native_full_horizon_originals import (
    _Audit,
    _bracket,
    _holding_steps,
    _release_points,
    _restore_frame,
    read_native_full_horizon_group,
    reconstruct_native_full_horizon_registry,
)
from cloud_edge_robot_arm.vision.native_completion import completion_metric_v2


@pytest.fixture
def eight_action_originals(tmp_path):
    """Complete eight-action byte graph, expressly SOFTWARE_ONLY (no source certificate).

    Action/hold identities and rational horizons are real schema objects. Frame,
    provenance and physical layers have separate original-byte counterexamples.
    """
    from cloud_edge_robot_arm.cloud.replanning.visual_dependencies import StepDependency
    from cloud_edge_robot_arm.contracts import SkillName
    from cloud_edge_robot_arm.edge.robot_adapter import build_action_result
    from cloud_edge_robot_arm.vision.owner_registration import (
        OriginalActionRequirements,
        _resolved_parameters,
        freeze_original_visual_plan,
    )
    from tests.test_raw_episode_v3 import fixture
    from tests.test_visual_owner_registration import bind, values

    protocol_dir = tmp_path / "registration"
    prepare_native_calibration(ROOT / CONFIG, output=protocol_dir)
    protocol = read_protocol(protocol_dir)
    data = values()
    old = data["original"]
    steps = [
        old.contract.steps[0].model_copy(
            update=dict(
                step_id=f"step-{i + 1}",
                skill=SkillName(row["skill"]),
                parameters={},
                timeout_ms=row["original_timeout_ms"],
                expected_duration_ms=row["original_timeout_ms"],
            )
        )
        for i, row in enumerate(protocol["actions"])
    ]
    contract = old.contract.model_copy(update={"steps": steps}, deep=True)
    req = old.requirements["move"]
    requirements = {
        step.step_id: OriginalActionRequirements(
            step,
            req.preconditions,
            req.postconditions,
            req.allowed_error_m,
            req.sensor_requirements,
            req.ordinary_ttl_s,
            row["horizon"]["total_steps"] / 240,
            req.policy_source_hashes,
        )
        for step, row in zip(steps, protocol["actions"], strict=True)
    }
    dependencies = tuple(
        StepDependency(
            s.step_id,
            (steps[i - 1].step_id,) if i else (),
            ("frame",),
            s.step_id + "-effect",
            False,
        )
        for i, s in enumerate(steps)
    )
    original = freeze_original_visual_plan(
        **{
            **old.freeze_inputs(),
            "contract": contract,
            "requirements": requirements,
            "dependencies": dependencies,
        }
    )
    envelope, _ = fixture()
    identity = replace(envelope.identity, owner_identity=original.identity)
    raw = dict(
        actions=[],
        horizons=[],
        allocated_actions=[],
        joins=[],
        commands=[],
        hold_mappings=[],
        total_physics_steps=12960,
    )
    intervals, frames = {}, {}
    cursor = 120
    for i, (step, row) in enumerate(zip(steps, protocol["actions"], strict=True)):
        grounded = step.model_copy(
            update=dict(
                parameters=_resolved_parameters(
                    step,
                    original,
                    data["online"],
                    data["grounding_inputs"],
                    data["grounding_policy"],
                ),
                preconditions=[],
                success_conditions=[],
            )
        )
        binding = replace(
            bind(),
            original_plan_hash=original.digest(),
            original_requirements=requirements[step.step_id],
            _grounded_step_json=canonical(grounded.model_dump(mode="json")).decode(),
            expected_duration_s=row["horizon"]["total_steps"] / 240,
        )
        a = cursor + (121 if row["skill"] == "LIFT" else 1)
        t = cursor + row["horizon"]["total_steps"]
        returned = build_action_result(
            action_type=row["skill"],
            success=True,
            state_before={},
            state_after={},
            duration_ms=4,
            started_at=data["now"],
            details={"contact_hold_s": 0.5, "physics_steps": a - cursor},
        ).model_dump(mode="json")
        span, hold, before, after = (
            f"span-{i + 1}",
            f"hold-{i + 1}",
            f"before-{i + 1}",
            f"after-{i + 1}",
        )
        raw["allocated_actions"].append(span)
        raw["actions"].append(
            dict(
                record_seq=i + 1,
                span_id=span,
                original_plan=original.to_payload(),
                step_id=step.step_id,
                attempt=1,
                grounding=binding.to_payload(),
                interval_id=span,
                command_seq_start=1,
                command_seq_end=1,
                returned_result=returned,
                disposition="RETURNED",
                error=None,
                executed_step_payload=grounded.model_dump(mode="json"),
            )
        )
        raw["horizons"].append(
            dict(
                step_id=step.step_id,
                skill=row["skill"],
                original_plan_sha256=original.digest(),
                executed_step_sha256=digest(grounded.model_dump(mode="json")),
                horizon_json=canonical(row["horizon"]).decode(),
                dispatch_step=cursor,
                controller_return_step=a,
                terminal_step=t,
                controller_result_json=canonical(dict(action_result=returned)).decode(),
                padding_interval_id=hold,
                terminal_acquisition_id=after,
                complete=True,
                reasons=[],
                failure_type=None,
            )
        )
        intervals[span] = dict(start_step=cursor, end_step=a, kind="EXECUTOR_ATTEMPT")
        intervals[hold] = dict(interval_id=hold, start_step=a, end_step=t, kind="HOLD")
        raw["hold_mappings"].append(
            dict(interval_id=hold, action_span_id=span, semantic_kind="FULL_HORIZON_HOLD")
        )
        for aid, n in ((before, cursor), (after, t)):
            frames[aid] = dict(step=n, observation_id=aid, checksum_sha256="a" * 64)
        raw["joins"].append(
            dict(
                record_seq=9 + i,
                span_id=span,
                acquisition_id=before,
                relation="BEFORE_SUBMIT",
                observation_id=before,
                checksum_sha256="a" * 64,
            )
        )
        cursor = t
    bundle = dict(
        raw=raw,
        intervals=intervals,
        frames=frames,
        identity=identity.to_payload(),
        original=original.to_payload(),
    )
    path = tmp_path / "software-eight-action-originals.json"
    save_exclusive(path, bundle)

    def audit():
        from cloud_edge_robot_arm.research.raw_episode_v3 import RawEpisodeIdentityV3, _owner_decode
        from cloud_edge_robot_arm.vision.owner_registration import VisualOriginalPlan

        read = load_json(path)
        value = _Audit(protocol, protocol["assignments"][0], tmp_path)
        value.raw, value.intervals, value.frames = read["raw"], read["intervals"], read["frames"]
        value.identity = RawEpisodeIdentityV3.from_json(json.dumps(read["identity"]))
        value.original = _owner_decode(VisualOriginalPlan, read["original"])
        return value

    return audit, protocol_dir, path


def test_full_group_reader_api_required():
    name = "cloud_edge_robot_arm.research.native_full_horizon_originals"
    module = import_module(name) if util.find_spec(name) else None
    assert callable(getattr(module, "read_native_full_horizon_group", None)), (
        "full group reader missing"
    )


def test_complete_eight_action_byte_horizons_and_required_counterexamples(eight_action_originals):
    factory, _, _ = eight_action_originals
    audit = factory()
    audit.horizons()
    assert (
        audit.horizon_ok and len(audit.actions) == 8 and audit.actions[-1]["terminal_step"] == 12960
    )
    changes = [
        lambda a: a.raw["actions"].pop(),
        lambda a: a.raw["horizons"][0].update(terminal_step=2041),
        lambda a: a.intervals["hold-1"].update(end_step=2041),
        lambda a: a.raw["horizons"][6].update(
            controller_return_step=a.raw["horizons"][6]["terminal_step"] - 239
        ),
        lambda a: a.raw["hold_mappings"][0].update(action_span_id="span-2"),
        lambda a: a.raw["actions"][5].update(grounding=None),
        lambda a: a.raw["actions"][1]["executed_step_payload"]["parameters"].update(
            target_pose={"x": 99, "y": 0, "z": 0}
        ),
        lambda a: a.frames["before-1"].update(step=119),
        lambda a: a.raw["actions"][0].update(attempt=2),
    ]
    for change in changes:
        broken = factory()
        change(broken)
        with pytest.raises((ValueError, KeyError, TypeError)):
            broken.horizons()


def test_release_full_transform_from_registered_place_tcp(eight_action_originals):
    from types import MappingProxyType

    from cloud_edge_robot_arm.research.native_collection_grounding import (
        release_reference_registration,
    )
    from tests.test_raw_episode_v3 import state

    factory, _, _ = eight_action_originals
    audit = factory()
    original_sources = dict(audit.protocol["source_hashes"])
    frozen_sources = MappingProxyType(original_sources)
    assert release_reference_registration(frozen_sources, audit.protocol["geometry"]) == (
        release_reference_registration(dict(frozen_sources), audit.protocol["geometry"])
    )
    assert dict(frozen_sources) == original_sources
    place, receipt = audit.raw["actions"][5], audit.raw["horizons"][5]
    tcp = [place["executed_step_payload"]["parameters"]["target_pose"][k] for k in "xyz"]
    correct = [tcp[0] + 0.002, tcp[1], tcp[2]]
    truth = state(receipt["terminal_step"])
    truth["object_geom_position_m"] = (np.asarray(tcp) - [0, 0, 0.01]).tolist()
    p, rc, rt, x = _release_points(
        audit.protocol, place, receipt, truth, correct_place_reference=correct
    )
    vertices = np.asarray(audit.protocol["release_reference"]["vertices_object_m"])
    assert len(p) == 8 and np.allclose(np.asarray(p) - vertices, np.asarray(tcp) - [0, 0, 0.01])
    assert np.allclose(p, x) and np.allclose(rc, rt) and not np.allclose(p, rc)
    reference = audit.protocol["release_reference"]
    rotation = np.asarray(reference["command_tcp_rotation"]).reshape(3, 3)
    world_tcp = np.eye(4)
    world_tcp[:3, :3] = rotation
    world_tcp[:3, 3] = tcp
    tool_tcp = np.asarray(reference["tool_to_tcp"]).reshape(4, 4)
    world_tool = world_tcp @ np.linalg.inv(tool_tcp)
    route = (
        world_tool
        @ tool_tcp
        @ np.linalg.inv(np.asarray(reference["nominal_object_to_tcp"]).reshape(4, 4))
    )
    assert np.allclose(vertices @ route[:3, :3].T + route[:3, 3], p)
    truth["object_geom_rotation_row_major"] = [0, -1, 0, 1, 0, 0, 0, 0, 1]
    p, rc, rt, x = _release_points(
        audit.protocol, place, receipt, truth, correct_place_reference=correct
    )
    metric = completion_metric_v2(
        geometric_error_m=0,
        command_points_m=p,
        capture_reference_points_m=rc,
        terminal_reference_points_m=rt,
        actual_points_m=x,
    )
    assert metric.l_m > 0.04 and metric.u_m == pytest.approx(0.002)
    assert reference["measured_tcp_rotation"] is False


def test_release_reference_rejects_missing_or_wrong_frame_sources(eight_action_originals):
    from tests.test_raw_episode_v3 import state

    factory, _, _ = eight_action_originals
    changes = [
        lambda a, p, r: a.protocol.pop("release_reference"),
        lambda a, p, r: p.update(grounding=None),
        lambda a, p, r: p["returned_result"].update(success=False),
        lambda a, p, r: p.update(step_id="step-5"),
        lambda a, p, r: r.update(complete=False),
        lambda a, p, r: a.protocol["release_reference"].update(
            nominal_object_to_tcp=a.protocol["geometry"]["object_to_tcp"]
        ),
        lambda a, p, r: a.protocol["release_reference"]["object_contact_offset_m"].__setitem__(
            2, 0.02
        ),
        lambda a, p, r: a.protocol["release_reference"].update(source_generation="f" * 64),
        lambda a, p, r: a.protocol["release_reference"].update(tool_to_tcp=[1] * 16),
    ]
    for change in changes:
        audit = factory()
        audit.protocol = copy.deepcopy(audit.protocol)
        p, r = audit.raw["actions"][5], audit.raw["horizons"][5]
        change(audit, p, r)
        with pytest.raises((ValueError, KeyError, TypeError)):
            _release_points(
                audit.protocol, p, r, state(123), correct_place_reference=(0.3, 0.2, 0.1)
            )
    audit = factory()
    with pytest.raises(ValueError, match="independent correct PLACE"):
        _release_points(
            audit.protocol,
            audit.raw["actions"][5],
            audit.raw["horizons"][5],
            state(123),
            correct_place_reference=None,
        )


def test_original_grasp_lift_release_hold_windows(eight_action_originals):
    factory, _, _ = eight_action_originals
    audit = factory()
    audit.horizons()
    for action in audit.actions:
        steps = list(_holding_steps(action))
        assert steps[-1] == action["terminal_step"]
        if action["skill"] == "GRASP":
            assert steps[0] == action["dispatch_step"] < action["controller_return_step"]
            errors = {n: 0.0 for n in steps}
            errors[steps[0]] = 0.02
            assert max(errors.values()) == 0.02  # Closing-period TCP drift is retained.
        elif action["skill"] == "LIFT":
            assert steps[0] == action["controller_return_step"] - 120 and len(steps) >= 121
        elif action["skill"] == "RELEASE":
            assert steps[0] == action["controller_return_step"] and len(steps) >= 241
            with pytest.raises(ValueError, match="release tail"):
                _holding_steps(action | {"terminal_step": action["controller_return_step"] + 239})
        else:
            assert steps == [action["terminal_step"]]
        sequence = dict.fromkeys(steps)
        del sequence[steps[len(steps) // 2]]
        with pytest.raises(KeyError):
            [sequence[n] for n in _holding_steps(action)]


def test_streamed_original_bytes_nulls_and_tamper_are_not_cached(tmp_path):
    from tests.test_native_collection_authority import source_recorder

    recorder, _, capture, owner, _ = source_recorder(tmp_path)
    try:
        with capture, recorder:
            obs = recorder.capture()
            aid = recorder.allocated_acquisition_ids[-1]
            metadata = load_json(recorder.directory / recorder.frame_sources[aid])
            assert _restore_frame(recorder.directory, metadata)[
                "observation_payload"
            ] == obs.model_dump(mode="json")
            for name in metadata["encoded_fields"].values():
                path = recorder.directory / name
                original = path.read_bytes()
                path.write_bytes(original + b"broken")
                with pytest.raises(ValueError):
                    _restore_frame(recorder.directory, metadata)
                path.write_bytes(original)
            broken = copy.deepcopy(metadata)
            broken["observation_payload_sha256"] = "0" * 64
            with pytest.raises(ValueError):
                _restore_frame(recorder.directory, broken)
            assert _restore_frame(
                recorder.directory, dict(frame={"observation_payload": None}, encoded_fields={})
            ) == {"observation_payload": None}
    finally:
        owner.close()


def test_registry_keeps_nine_groups_partial_unknown_and_ignores_caller_score(tmp_path):
    directory = tmp_path / "protocol"
    prepare_native_calibration(ROOT / CONFIG, output=directory)
    root = tmp_path / "partial"
    root.mkdir()
    save_exclusive(
        root / "collection-result.json",
        dict(status="PASS", qualified_group_score=0, joint_bound_m=0),
    )
    one = read_native_full_horizon_group(directory, assignment_id="native-r439-0001", root=root)
    assert not one.source_complete and not one.horizon_complete and one.group_score is None
    groups = []
    joint = reconstruct_native_full_horizon_registry(
        directory, roots={"native-r439-0001": root}, group_sink=groups.append
    )
    assert joint.assigned_group_count == joint.component_count == joint.rank == 9
    assert joint.joint_bound_m is None and len(joint.unavailable_group_ids) == 9
    assert len(groups) == 9 and sum(r.get("state") == "NOT_RUN" for r in groups) == 8
    assert not one.execution_admitted and one.native_qualification == "UNKNOWN"


def test_original_deadline_equality_and_foreign_clock_reject():
    domain = {"source": "software-only"}
    _bracket(dict(domain=domain, lower_ns=5, upper_ns=9), domain, 10)
    for row in (
        dict(domain=domain, lower_ns=5, upper_ns=10),
        dict(domain={}, lower_ns=5, upper_ns=9),
        dict(domain=domain, lower_ns=8, upper_ns=7),
        dict(domain=domain, lower_ns=True, upper_ns=9),
    ):
        with pytest.raises(ValueError):
            _bracket(row, domain, 10)


def test_all_action_metrics_use_all_hold_states_and_physical_truth_is_offline(
    eight_action_originals,
):
    from tests.test_raw_episode_v3 import state
    from tests.test_visual_owner_registration import values

    factory, _, _ = eight_action_originals
    audit = factory()
    audit.horizons()
    audit.states = {n: state(n) for n in range(12961)}
    audit.geometry_ok = audit.decision_ok = True
    audit.geometry_errors = [0.003]
    audit.policies = {row["skill"]: values()["grounding_policy"] for row in audit.actions}
    audit.metrics()
    assert all(row["metric"]["completion_error_m"] >= 0.003 for row in audit.actions)
    assert all(row["metric"]["native_authority"] == "UNAVAILABLE" for row in audit.actions)
    before = audit.actions[2]["metric"]["l_m"]
    closing = audit.actions[2][
        "dispatch_step"
    ]  # p is fixed at this source; change a later closing/hold state.
    audit.states[closing + 1]["tcp_position_m"][0] += 0.2
    audit.metrics()
    assert audit.actions[2]["metric"]["l_m"] > before + 0.1
    audit.physical_outcome()
    assert not audit.physical["success"] and not audit.physical["registered_grasp_hold"]
    assert (
        not audit.physical["registered_lift_hold"]
        and not audit.physical["registered_release_stability"]
    )
    assert audit.original.digest() == factory().original.digest()
