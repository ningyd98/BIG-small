"""SOFTWARE_ONLY raw-v3 structure; no sampling, simulator or physical authority."""

import base64
import hashlib
import json
import struct
from dataclasses import replace
from datetime import timedelta
from importlib import import_module

import pytest

from cloud_edge_robot_arm.edge.robot_adapter import build_action_result
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from tests.test_visual_owner_registration import NOW, values

SHA = "a" * 64
SOURCES = {"src/software-fixture.py": SHA}


def api():
    return import_module("cloud_edge_robot_arm.research.raw_episode_v3")


def test_missing_module_then_consistency_view_has_no_execution_authority():
    module = api()
    assert module.RawV3ConsistencyView.scope == "SOURCE_CONSISTENCY_ONLY"
    assert module.RawV3ConsistencyView.continuous_motion == "NOT_CERTIFIED"


def hash_payload(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def state(step):
    return dict(
        episode_id="episode",
        physics_step=step,
        sim_time_s=step / 240,
        object_position_m=[0.2, 0.1, 0.04],
        object_geom_position_m=[0.2, 0.1, 0.04],
        object_geom_rotation_row_major=[1, 0, 0, 0, 1, 0, 0, 0, 1],
        object_half_extent_m=[0.035] * 3,
        object_bottom_z_m=0.005,
        object_linear_velocity_m_s=[0] * 3,
        object_angular_velocity_rad_s=[0] * 3,
        region_center_m=[0.3, 0.2, 0],
        region_half_extent_m=[0.1, 0.1, 0.01],
        table_top_m=0,
        tcp_position_m=[0.2, 0.1, 0.16],
        gripper_open=True,
        finger_positions_m=[0.039] * 2,
        finger_velocities_m_s=[0] * 2,
        finger_ranges_m=[[0, 0.04]] * 2,
        joint_positions_rad=[0] * 7,
        joint_velocities_rad_s=[0] * 7,
        joint_ranges_rad=[[-3, 3]] * 7,
        contact_pairs=[],
        self_collision_distances_m=[],
        estop_engaged=False,
    )


def control(step):
    return dict(
        episode_id="episode",
        physics_step=step,
        sim_time_s=(step - 1) / 240,
        applied_joint_targets_rad=[0] * 7,
        pre_joint_positions_rad=[0] * 7,
        pre_gravity_bias_nm=[0] * 7,
        control_rad=[0] * 7,
        finger_control_targets_m=[0.039] * 2,
        actuator_gains=[20] * 7,
        actuator_ctrl_ranges=[[-3, 3]] * 7,
    )


def fixture(*, late_action=False):
    m = api()
    original = values()["original"]
    identity = m.RawEpisodeIdentityV3(
        "raw-attempt-1",
        "assignment-1",
        SHA,
        "episode",
        "SOFTWARE_ONLY",
        original.identity,
        SHA,
        SHA,
        SHA,
        SHA,
        SHA,
        {**SOURCES, **dict(original.source_hashes)},
        "clock-1",
    )
    descriptor = m.ClockDescriptorV3(
        "clock-1", "epoch-1", "fixture-monotonic", "fixture-utc", 1, 1000, None, SOURCES
    )
    seq = 0
    intervals, physics = [], []

    def next_seq():
        nonlocal seq
        seq += 1
        return seq

    def pair(ns):
        return m.ClockPairV3(
            "clock-1",
            descriptor.digest(),
            ns + 1,
            ns,
            NOW + timedelta(microseconds=ns // 1000),
            ns + 100,
        )

    def interval(name, kind, n0, n1, t0, t1, disposition="COMPLETE", error=None):
        row = m.RawIntervalV3(
            name,
            next_seq(),
            identity,
            kind,
            pair(t0),
            pair(t1) if t1 is not None else None,
            n0,
            n1,
            n0 / 240,
            n1 / 240 if n1 is not None else None,
            disposition,
            error,
        )
        intervals.append(row)
        return row

    interval("settle", "SETTLE", 0, 120, 0, 12_100_000)
    shift = 6_000_000_000 if late_action else 0
    interval("attempt", "EXECUTOR_ATTEMPT", 120, 121, 210_000_000 + shift, 220_000_000 + shift)
    for n in range(1, 122):
        base = (n - 1) * 100_000 if n <= 120 else 211_000_000 + shift
        interval(f"control-{n}", "CONTROL_APPLY", n - 1, n - 1, base + 1000, base + 2000)
        interval(f"step-{n}", "PHYSICS_STEP", n - 1, n, base + 3000, base + 90_000)
        physics.append(
            m.RawPhysicsStepV3(
                next_seq(),
                identity,
                n,
                hash_payload(state(n - 1)),
                state(n),
                control(n),
                f"step-{n}",
                f"control-{n}",
                "settle" if n <= 120 else "attempt",
            )
        )
    interval("command", "COMMAND", 120, 120, 210_100_000 + shift, 210_110_000 + shift)
    command = m.RawCommandV3(
        next_seq(),
        identity,
        1,
        dict(
            type="joint_target",
            accepted=True,
            reason="",
            after_emergency_stop=False,
            sim_time_s=0.5,
            episode_id="episode",
            physics_step=120,
            command_seq=1,
            target_positions_rad=[0] * 7,
            applied_target_positions_rad=[0] * 7,
        ),
        "command",
        "attempt",
        "span-1",
        121,
    )
    action = m.TypedActionSpanV3(
        next_seq(),
        identity,
        "span-1",
        original,
        "move",
        1,
        None,
        "attempt",
        1,
        2,
        build_action_result(
            action_type="MOVE_ABOVE",
            success=False,
            state_before={},
            state_after={},
            duration_ms=4,
            started_at=NOW + timedelta(seconds=0.21),
            error_code="SOFTWARE_DIAGNOSTIC",
            details={"physics_steps": 1},
        ).model_dump(mode="json"),
        "RETURNED",
        None,
        original.requirements["move"].original_step.model_dump(mode="json"),
    )
    base_observation = values()["online"].observation.model_dump(mode="json")
    frames = []
    for name, index, ns in (("before", 120, 100_000_000), ("after", 121, 221_000_000 + shift)):
        interval(f"acq-{name}", "ACQUISITION", index, index, ns, ns + 1_000_000)
        payload = {
            **base_observation,
            "frame_id": name,
            "observation_id": name,
            "captured_at": (NOW + timedelta(microseconds=ns // 1000)).isoformat(),
            "sim_time_s": index / 240,
            "checksum_sha256": "",
        }
        observation = RGBDObservation.model_validate(payload)
        files = {
            f"frames/{name}/{key}": hashlib.sha256(
                base64.b64decode(getattr(observation, attr))
            ).hexdigest()
            for key, attr in (
                ("rgb.png", "rgb_png_base64"),
                ("depth.f32", "depth_float32_base64"),
                ("mask.u8", "valid_mask_base64"),
            )
        }
        camera_state = dict(
            sim_time_s=index / 240,
            qpos=[0] * 7 + [0.039] * 2 + [0.2, 0.1, 0.04, 1, 0, 0, 0],
            qvel=[0] * 15,
            act=[],
            ctrl=[0] * 7 + [0.039] * 2,
        )
        binary = struct.pack("<d", camera_state["sim_time_s"])
        for key in ("qpos", "qvel", "act", "ctrl"):
            binary += struct.pack("<I", len(camera_state[key])) + struct.pack(
                f"<{len(camera_state[key])}d", *camera_state[key]
            )
        camera_hash = hashlib.sha256(binary).hexdigest()
        frames.append(
            m.FrameAcquisitionV3(
                next_seq(),
                identity,
                name,
                f"acq-{name}",
                observation.model_dump(mode="json"),
                camera_state,
                hash_payload(state(index)),
                (camera_hash,) * 3,
                files,
                "ONLINE",
                None,
                None,
                {},
            )
        )
    joins = tuple(
        m.ActionFrameJoinV3(
            next_seq(),
            identity,
            "span-1",
            f.acquisition_id,
            relation,
            f.observation_payload["observation_id"],
            f.observation_payload["checksum_sha256"],
        )
        for f, relation in zip(frames, ("BEFORE_SUBMIT", "AFTER_RETURN"), strict=True)
    )
    records = m.RawEpisodeRecordsV3(
        tuple(intervals), tuple(physics), (command,), (action,), tuple(frames), joins
    )
    inventory = {path: digest for f in frames for path, digest in f.file_hashes.items()}
    envelope = m.RawEpisodeEnvelopeV3(
        identity,
        descriptor,
        state(0),
        state(121),
        120,
        1 / 240,
        1,
        ("span-1",),
        ("before", "after"),
        inventory,
        NOW + timedelta(seconds=60),
        NOW + timedelta(seconds=40),
        NOW + timedelta(seconds=60),
        {"joints_rad": [0] * 7, "fingers_m": [0.039] * 2},
        0,
    )
    return envelope, records


def test_complete_recorded_graph_and_unknown_utc_uncertainty_are_separate():
    envelope, records = fixture()
    view = api().validate_raw_episode_v3(envelope, records)
    assert view.status == "COMPLETE", view.reasons
    assert view.monotonic_coverage == "COMPLETE" and view.utc_mapping == "UNAVAILABLE"
    assert view.counts["allocated_actions"] == view.counts["recorded_actions"] == 1
    assert view.counts["physics_expected"] == view.counts["physics_recorded"] == 121
    assert view.counts["missing_actions"] == view.counts["missing_acquisitions"] == 0
    assert view.to_payload()["continuous_motion"] == "NOT_CERTIFIED"
    assert "execution_accepted" not in view.to_payload()


@pytest.mark.parametrize("value", [True, "1", 10**500, float("nan"), float("inf"), -1])
def test_invalid_clock_numeric_fields_do_not_coerce(value):
    m = api()
    with pytest.raises(ValueError):
        m.ClockPairV3("clock-1", SHA, 1, value, NOW, 10)


@pytest.mark.parametrize(
    "change",
    [
        {"utc_at": NOW.replace(tzinfo=None)},
        {"mono_after_ns": 0},
        {"descriptor_hash": "x"},
        {"sequence": True},
    ],
)
def test_clock_constructor_rejects_naive_reversed_or_fake_identity(change):
    m = api()
    row = dict(
        clock_domain_id="clock-1",
        descriptor_hash=SHA,
        sequence=1,
        mono_before_ns=1,
        utc_at=NOW,
        mono_after_ns=2,
    )
    with pytest.raises(ValueError):
        m.ClockPairV3(**{**row, **change})


def test_public_records_clone_subclass_mutable_payload_and_detach_serialization():
    envelope, records = fixture()
    m = api()

    class MutableAction(m.TypedActionSpanV3):
        def to_payload(self):
            return {"wrong": mutable}

    mutable = ["before"]
    action = MutableAction(
        **{
            name: getattr(records.actions[0], name)
            for name in records.actions[0].__dataclass_fields__
        }
    )
    copied = replace(records, actions=[action])
    first = copied.digest()
    mutable.append("after")
    payload = copied.to_payload()
    payload["actions"][0]["original_plan"]["requirements"]["move"]["allowed_error_m"] = 100
    assert type(copied.actions[0]) is m.TypedActionSpanV3 and copied.digest() == first
    assert m.validate_raw_episode_v3(envelope, copied).status == "COMPLETE"


def test_strict_json_roundtrip_rejects_duplicate_unknown_nonfinite_and_bool_step():
    envelope, records = fixture()
    m = api()
    assert (
        m.RawEpisodeRecordsV3.from_json(json.dumps(records.to_payload())).digest()
        == records.digest()
    )
    assert (
        m.RawEpisodeEnvelopeV3.from_json(json.dumps(envelope.to_payload())).digest()
        == envelope.digest()
    )
    for stored in ('{"identity":{},"identity":{}}', '{"unknown":1}', '{"x":NaN}'):
        with pytest.raises(ValueError):
            m.RawEpisodeRecordsV3.from_json(stored)
    payload = records.to_payload()
    payload["actions"][0]["original_plan"]["contract"]["steps"][0]["timeout_ms"] = True
    with pytest.raises(ValueError):
        m.RawEpisodeRecordsV3.from_json(json.dumps(payload))


@pytest.mark.parametrize("field", ["physics", "commands", "actions", "frames"])
def test_missing_record_keeps_complete_original_allocations(field):
    envelope, records = fixture()
    changes = {field: getattr(records, field)[:-1]}
    view = api().validate_raw_episode_v3(envelope, replace(records, **changes))
    assert view.status == "INCOMPLETE"
    assert view.counts["allocated_actions"] == 1 and view.counts["allocated_acquisitions"] == 2
    assert view.counts["physics_expected"] == 121 and view.counts["commands_expected"] == 1


@pytest.mark.parametrize(
    "kind",
    [
        "duplicate-step",
        "wrong-control",
        "wrong-hash",
        "foreign-epoch",
        "wrong-command-range",
        "frame-checksum",
    ],
)
def test_contradictory_record_graph_is_invalid(kind):
    envelope, records = fixture()
    if kind == "duplicate-step":
        records = replace(records, physics=(*records.physics, records.physics[-1]))
    elif kind == "wrong-control":
        raw = dict(records.physics[-1].control_payload)
        raw["pre_joint_positions_rad"] = [0.1] * 7
        records = replace(
            records,
            physics=(*records.physics[:-1], replace(records.physics[-1], control_payload=raw)),
        )
    elif kind == "wrong-hash":
        records = replace(
            records,
            physics=(
                *records.physics[:-1],
                replace(records.physics[-1], previous_state_hash="b" * 64),
            ),
        )
    elif kind == "foreign-epoch":
        owner = replace(envelope.identity.owner_identity, owner_epoch="epoch-2")
        foreign = replace(envelope.identity, owner_identity=owner)
        records = replace(records, commands=(replace(records.commands[0], identity=foreign),))
    elif kind == "wrong-command-range":
        records = replace(records, actions=(replace(records.actions[0], command_seq_end=1),))
    else:
        records = replace(
            records, joins=(replace(records.joins[0], checksum_sha256="b" * 64), records.joins[1])
        )
    assert api().validate_raw_episode_v3(envelope, records).status == "INVALID"


def test_partial_exception_and_missing_acquisition_remain_auditable():
    envelope, records = fixture()
    interval = next(i for i in records.intervals if i.interval_id == "attempt")
    partial = replace(
        interval,
        end=None,
        end_step=None,
        end_sim_time_s=None,
        disposition="PARTIAL",
        error="reader-failed",
    )
    records = replace(
        records,
        intervals=tuple(partial if i == interval else i for i in records.intervals),
        actions=(replace(records.actions[0], disposition="PARTIAL", error="reader-failed"),),
    )
    view = api().validate_raw_episode_v3(envelope, records)
    assert view.status == "INCOMPLETE" and view.counts["partial_actions"] == 1
    assert view.counts["allocated_actions"] == view.counts["recorded_actions"] == 1


def test_clocks_cannot_change_domain_or_fabricate_whole_episode_mapping():
    envelope, records = fixture()
    first = records.intervals[0]
    shifted = replace(first.end, utc_at=first.end.utc_at + timedelta(seconds=20))
    records = replace(records, intervals=(replace(first, end=shifted), *records.intervals[1:]))
    view = api().validate_raw_episode_v3(envelope, records)
    assert view.utc_mapping == "UNAVAILABLE" and view.continuous_motion == "NOT_CERTIFIED"
    assert "utc_clock_discontinuity" in view.reasons


def test_camera_hash_domain_is_distinct_and_recomputed_from_original_full_arrays():
    envelope, records = fixture()
    frame = records.frames[0]
    assert frame.pass_state_hashes[0] != frame.joined_physics_observation_hash
    corrupted = dict(frame.camera_state_payload)
    corrupted["qvel"] = [0.1] * 15
    changed = replace(
        records, frames=(replace(frame, camera_state_payload=corrupted), records.frames[1])
    )
    view = api().validate_raw_episode_v3(envelope, changed)
    assert view.status == "INVALID" and "camera_pass_state_hash_mismatch" in view.reasons


def test_command_effect_and_initial_controller_targets_are_replayed_not_assumed():
    envelope, records = fixture()
    altered = {"joints_rad": [0.1] * 7, "fingers_m": [0.039] * 2}
    view = api().validate_raw_episode_v3(
        replace(envelope, initial_controller_targets=altered), records
    )
    assert view.status == "INVALID" and "applied_controller_target_replay_mismatch" in view.reasons


def test_missing_effect_step_and_delay_mismatch_remain_distinct():
    envelope, records = fixture()
    missing = replace(records, commands=(replace(records.commands[0], effective_from_step=None),))
    assert api().validate_raw_episode_v3(envelope, missing).status == "INCOMPLETE"
    delayed = replace(records, commands=(replace(records.commands[0], effective_from_step=122),))
    assert api().validate_raw_episode_v3(envelope, delayed).status == "INVALID"


def test_action_before_frame_cannot_outlive_original_ttl():
    envelope, records = fixture(late_action=True)
    view = api().validate_raw_episode_v3(envelope, records)
    assert view.status == "INVALID" and "action_frame_original_ttl_expired" in view.reasons


def test_stable_original_grounding_clones_and_json_roundtrips_then_rejects_policy_drift():
    envelope, records = fixture()
    m = api()
    v = values()
    from cloud_edge_robot_arm.vision.owner_registration import bind_step_grounding

    grounding = bind_step_grounding(**v)
    before = records.frames[0].observation_payload
    grounding = replace(
        grounding,
        observation_id=before["observation_id"],
        observation_checksum_sha256=before["checksum_sha256"],
    )
    updated = replace(
        records,
        actions=(
            replace(
                records.actions[0],
                grounding=grounding,
                executed_step_payload=grounding.grounded_step.model_dump(mode="json"),
            ),
        ),
    )
    assert m.validate_raw_episode_v3(envelope, updated).status == "COMPLETE"
    assert (
        m.RawEpisodeRecordsV3.from_json(json.dumps(updated.to_payload())).digest()
        == updated.digest()
    )
    with pytest.raises(ValueError):
        bad = replace(grounding.original_requirements, allowed_error_m=True)
        replace(updated.actions[0], grounding=replace(grounding, original_requirements=bad))
    drift = replace(grounding.original_requirements, allowed_error_m=0.1)
    altered = replace(
        updated,
        actions=(
            replace(updated.actions[0], grounding=replace(grounding, original_requirements=drift)),
        ),
    )
    assert m.validate_raw_episode_v3(envelope, altered).status == "INVALID"


def test_online_trace_without_grounding_is_missing_evidence_without_actual_flag():
    envelope, records = fixture()
    identity = replace(envelope.identity, source_kind="ONLINE_CED")

    def update(group):
        return tuple(replace(r, identity=identity) for r in group)

    updated = api().RawEpisodeRecordsV3(
        *(
            update(getattr(records, name))
            for name in ("intervals", "physics", "commands", "actions", "frames", "joins")
        )
    )
    view = api().validate_raw_episode_v3(replace(envelope, identity=identity), updated)
    assert view.status == "INCOMPLETE" and "online_grounding_source_missing" in view.reasons
    assert view.scope == "SOURCE_CONSISTENCY_ONLY"


def test_frame_and_descriptor_source_identity_cannot_drift_from_envelope():
    envelope, records = fixture()
    descriptor = replace(
        envelope.clock_descriptor, source_hashes={"src/changed-clock.py": "b" * 64}
    )
    view = api().validate_raw_episode_v3(replace(envelope, clock_descriptor=descriptor), records)
    assert view.status == "INVALID"


def test_submitted_json_cannot_replace_scope_or_schema_with_acceptance_receipt():
    envelope, records = fixture()
    payload = envelope.to_payload()
    assert (
        payload["schema_version"] == "rgbd.raw-episode.v3"
        and payload["scope"] == "SOURCE_CONSISTENCY_ONLY"
    )
    payload["scope"] = "EXECUTION_ACCEPTED"
    with pytest.raises(ValueError):
        api().RawEpisodeEnvelopeV3.from_json(json.dumps(payload))


def renumber(records):
    seq = 0
    changes = {}
    for name in ("intervals", "physics", "commands", "actions", "frames", "joins"):
        rows = []
        for row in getattr(records, name):
            seq += 1
            rows.append(replace(row, record_seq=seq))
        changes[name] = tuple(rows)
    return replace(records, **changes)


def test_same_step_overwritten_commands_remain_ordered_in_complete_trace():
    envelope, records = fixture()
    command = records.commands[0]
    first = dict(command.command_payload)
    first.update(target_positions_rad=[0.1] * 7, applied_target_positions_rad=[0.1] * 7)
    second = {**dict(command.command_payload), "command_seq": 2}
    stamp = next(i for i in records.intervals if i.interval_id == "command")
    later = replace(
        stamp,
        interval_id="command-2",
        start=replace(
            stamp.start,
            sequence=210_200_001,
            mono_before_ns=210_200_000,
            utc_at=NOW + timedelta(microseconds=210200),
            mono_after_ns=210_200_100,
        ),
        end=replace(
            stamp.end,
            sequence=210_210_001,
            mono_before_ns=210_210_000,
            utc_at=NOW + timedelta(microseconds=210210),
            mono_after_ns=210_210_100,
        ),
    )
    updated = renumber(
        replace(
            records,
            intervals=(*records.intervals, later),
            commands=(
                replace(command, command_payload=first),
                replace(command, command_seq=2, command_payload=second, interval_id="command-2"),
            ),
            actions=(replace(records.actions[0], command_seq_end=3),),
        )
    )
    view = api().validate_raw_episode_v3(replace(envelope, terminal_command_seq=2), updated)
    assert view.status == "COMPLETE", view.reasons
    assert view.counts["commands_recorded"] == 2
    assert updated.commands[0].command_payload["target_positions_rad"] == (0.1,) * 7


def test_delayed_command_applies_in_later_passive_interval_without_changing_action_owner():
    envelope, records = fixture()
    m = api()
    base = next(i for i in records.intervals if i.interval_id == "command")

    def interval(name, kind, n0, n1, start, end):
        def pair(ns):
            return replace(
                base.start,
                sequence=ns + 1,
                mono_before_ns=ns,
                mono_after_ns=ns + 100,
                utc_at=NOW + timedelta(microseconds=ns // 1000),
            )

        return replace(
            base,
            interval_id=name,
            kind=kind,
            start_step=n0,
            end_step=n1,
            start_sim_time_s=n0 / 240,
            end_sim_time_s=n1 / 240,
            start=pair(start),
            end=pair(end),
        )

    extra = (
        interval("wait", "WAIT", 121, 122, 230_000_000, 240_000_000),
        interval("control-122", "CONTROL_APPLY", 121, 121, 231_000_000, 231_001_000),
        interval("step-122", "PHYSICS_STEP", 121, 122, 231_002_000, 239_000_000),
    )
    ctl = control(122)
    ctl.update(applied_joint_targets_rad=[0.1] * 7, control_rad=[0.1] * 7)
    physical = m.RawPhysicsStepV3(
        999,
        envelope.identity,
        122,
        hash_payload(state(121)),
        state(122),
        ctl,
        "step-122",
        "control-122",
        "wait",
    )
    cmd = dict(records.commands[0].command_payload)
    cmd.update(
        reason="queued_until_physics_step=121",
        target_positions_rad=[0.1] * 7,
        applied_target_positions_rad=[0.1] * 7,
    )
    changed = renumber(
        replace(
            records,
            intervals=(*records.intervals, *extra),
            physics=(*records.physics, physical),
            commands=(replace(records.commands[0], command_payload=cmd, effective_from_step=122),),
        )
    )
    view = m.validate_raw_episode_v3(
        replace(envelope, terminal_state_payload=state(122), actuator_delay_steps=1), changed
    )
    assert view.status == "COMPLETE", view.reasons
    assert (
        changed.commands[0].owner_action_span_id == "span-1"
        and changed.physics[-1].purpose_interval_id == "wait"
    )


def test_zero_step_rejected_attempt_is_retained_without_fabricating_after_capture():
    envelope, records = fixture()
    attempted = next(i for i in records.intervals if i.interval_id == "attempt")
    attempted = replace(attempted, end_step=120, end_sim_time_s=0.5)
    removed = {"step-121", "control-121", "command", "acq-after"}
    kept = tuple(
        attempted if i.interval_id == "attempt" else i
        for i in records.intervals
        if i.interval_id not in removed
    )
    action = replace(
        records.actions[0],
        command_seq_end=1,
        returned_result=None,
        disposition="REJECTED",
        error="precondition_rejected",
    )
    changed = renumber(
        replace(
            records,
            intervals=kept,
            physics=records.physics[:-1],
            commands=(),
            actions=(action,),
            frames=records.frames[:1],
            joins=records.joins[:1],
        )
    )
    view = api().validate_raw_episode_v3(
        replace(
            envelope,
            terminal_state_payload=state(120),
            terminal_command_seq=0,
            allocated_acquisition_ids=("before",),
            original_file_hashes=records.frames[0].file_hashes,
        ),
        changed,
    )
    assert view.status == "COMPLETE", view.reasons
    assert view.counts["allocated_actions"] == view.counts["rejected_actions"] == 1
    assert view.counts["physics_recorded"] == 120 and view.counts["recorded_acquisitions"] == 1


def test_large_declared_missing_tail_does_not_allocate_or_iterate_the_missing_population():
    import os
    import subprocess
    import sys
    from pathlib import Path

    script = """
import json,os,resource
from dataclasses import replace
from tests.test_raw_episode_v3 import fixture,state,api
envelope,records=fixture()
current=int(open('/proc/self/statm').read().split()[0])*os.sysconf('SC_PAGE_SIZE')
resource.setrlimit(resource.RLIMIT_AS,(current+128*1024*1024,current+128*1024*1024))
view=api().validate_raw_episode_v3(replace(envelope,terminal_state_payload=state(2**63-1)),records)
assert view.status=='INCOMPLETE',view.reasons
assert view.counts['physics_expected']==2**63-1
print('bounded missing denominator retained')
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "PYTHONPATH": "src:."},
        text=True,
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert "bounded missing denominator retained" in result.stdout


def test_executed_payload_and_original_absolute_deadlines_cannot_be_replaced():
    envelope, records = fixture()
    altered = (
        records.actions[0].original_plan.requirements["move"].original_step.model_dump(mode="json")
    )
    altered["parameters"] = {"object_id": "decoy"}
    bad = replace(records, actions=(replace(records.actions[0], executed_step_payload=altered),))
    view = api().validate_raw_episode_v3(envelope, bad)
    assert view.status == "INVALID" and "executor_payload_original_binding_mismatch" in view.reasons
    extended = replace(envelope, task_deadline_at=NOW + timedelta(seconds=600))
    view = api().validate_raw_episode_v3(extended, records)
    assert view.status == "INVALID" and "original_absolute_deadline_extended" in view.reasons


def test_retry_attempt_and_return_step_count_are_strict_original_policy():
    envelope, records = fixture()
    retry = replace(records, actions=(replace(records.actions[0], attempt=2),))
    view = api().validate_raw_episode_v3(envelope, retry)
    assert (
        view.status == "INVALID"
        and "original_retry_policy_or_attempt_order_mismatch" in view.reasons
    )
    payload = records.to_payload()
    payload["actions"][0]["returned_result"]["details"]["physics_steps"] = True
    with pytest.raises(ValueError):
        api().RawEpisodeRecordsV3.from_json(json.dumps(payload))


def test_missing_executed_arguments_is_incomplete_without_losing_attempt():
    envelope, records = fixture()
    altered = replace(records, actions=(replace(records.actions[0], executed_step_payload=None),))
    view = api().validate_raw_episode_v3(envelope, altered)
    assert view.status == "INCOMPLETE" and view.counts["allocated_actions"] == 1


def test_derived_source_transform_requires_exact_schema_and_policy_sources():
    envelope, records = fixture()
    with pytest.raises(ValueError):
        replace(
            records.frames[0],
            source_acquisition_id="some-source",
            transform_payload={"garbage": True},
            transform_source_hashes=SOURCES,
        )


def test_individual_original_task_deadline_cannot_extend_even_when_verification_is_earlier():
    envelope, records = fixture()
    view = api().validate_raw_episode_v3(
        replace(envelope, task_deadline_at=NOW + timedelta(seconds=600)), records
    )
    assert view.status == "INVALID" and "original_absolute_deadline_extended" in view.reasons


def test_action_result_step_count_boolean_is_not_the_integer_one():
    envelope, records = fixture()
    payload = records.to_payload()
    payload["actions"][0]["returned_result"]["details"]["physics_steps"] = True
    with pytest.raises(ValueError):
        api().RawEpisodeRecordsV3.from_json(json.dumps(payload))


def derived_fixture(*, corrupt_online=False):
    envelope, records = fixture()
    source = replace(records.frames[0], input_role="SOURCE")
    payload = dict(source.observation_payload)
    if not corrupt_online:
        payload.update(
            depth_float32_base64=base64.b64encode(bytes(16)).decode(),
            valid_mask_base64=None,
            checksum_sha256="",
        )
    obs = RGBDObservation.model_validate(payload)
    files = {
        f"frames/before-derived/{name}": hashlib.sha256(
            base64.b64decode(getattr(obs, attr))
        ).hexdigest()
        for name, attr in (
            ("rgb.png", "rgb_png_base64"),
            ("depth.f32", "depth_float32_base64"),
            ("mask.u8", "valid_mask_base64"),
        )
    }
    transform = dict(
        schema_version="rgbd.fixed-corruption.v1",
        perturbation_seed=7,
        frame_count=1,
        noise_m=0.0,
        invalid_fraction=1.0,
        occlusion_fraction=0.0,
    )
    derived = replace(
        source,
        acquisition_id="before-derived",
        input_role="ONLINE",
        source_acquisition_id="before",
        observation_payload=obs.model_dump(mode="json"),
        file_hashes=files,
        transform_payload=transform,
        transform_source_hashes=SOURCES,
    )
    before_join = replace(
        records.joins[0], acquisition_id="before-derived", checksum_sha256=obs.checksum_sha256
    )
    changed = renumber(
        replace(
            records,
            frames=(source, derived, records.frames[1]),
            joins=(before_join, records.joins[1]),
        )
    )
    envelope = replace(
        envelope,
        allocated_acquisition_ids=("before", "before-derived", "after"),
        original_file_hashes={**dict(envelope.original_file_hashes), **files},
    )
    return envelope, changed


def test_clean_source_and_online_derivative_share_one_capture_and_replay_actual_transform():
    envelope, records = derived_fixture()
    view = api().validate_raw_episode_v3(envelope, records)
    assert view.status == "COMPLETE", view.reasons
    assert view.counts["recorded_acquisition_records"] == 3
    assert (
        view.counts["distinct_acquisition_intervals"] == 2
        and view.counts["derived_online_inputs"] == 1
    )
    envelope, bad = derived_fixture(corrupt_online=True)
    view = api().validate_raw_episode_v3(envelope, bad)
    assert view.status == "INVALID" and "derived_online_transform_bytes_mismatch" in view.reasons


def clock_interval(base, name, kind, n0, n1, start_ns, end_ns):
    def pair(ns):
        return replace(
            base.start,
            sequence=ns + 1,
            mono_before_ns=ns,
            mono_after_ns=ns + 100,
            utc_at=NOW + timedelta(microseconds=ns // 1000),
        )

    return replace(
        base,
        interval_id=name,
        kind=kind,
        start_step=n0,
        end_step=n1,
        start_sim_time_s=n0 / 240,
        end_sim_time_s=n1 / 240,
        start=pair(start_ns),
        end=pair(end_ns),
    )


def stop_order_fixture(*, later="accepted", clear_state=False):
    envelope, records = fixture()
    base = next(i for i in records.intervals if i.interval_id == "command")
    intervals = (
        clock_interval(base, "hold-before-stop", "COMMAND", 120, 120, 210020000, 210021000),
        clock_interval(base, "accepted-stop", "COMMAND", 120, 120, 210040000, 210041000),
    )
    common = {
        "accepted": True,
        "reason": "",
        "after_emergency_stop": False,
        "sim_time_s": 0.5,
        "episode_id": "episode",
        "physics_step": 120,
    }
    original = records.commands[0]
    hold = replace(
        original,
        interval_id=intervals[0].interval_id,
        command_payload={
            **common,
            "type": "hold_current_joints",
            "command_seq": 1,
            "target_positions_rad": [0] * 7,
            "applied_target_positions_rad": [0] * 7,
        },
    )
    stop = replace(
        original,
        command_seq=2,
        interval_id=intervals[1].interval_id,
        command_payload={**common, "type": "emergency_stop", "command_seq": 2},
    )
    payload = {**dict(original.command_payload), "command_seq": 3}
    effective = 121
    if later == "rejected":
        payload.update(accepted=False, reason="emergency_stop", after_emergency_stop=True)
        del payload["applied_target_positions_rad"]
        effective = None
    elif later == "hold":
        payload.update(type="hold_current_joints", after_emergency_stop=True)
    subsequent = replace(
        original, command_seq=3, command_payload=payload, effective_from_step=effective
    )
    final_state = {**dict(records.physics[-1].post_state_payload), "estop_engaged": not clear_state}
    final_physics = replace(records.physics[-1], post_state_payload=final_state)
    final_frame = replace(
        records.frames[-1], joined_physics_observation_hash=hash_payload(final_state)
    )
    return replace(envelope, terminal_command_seq=3, terminal_state_payload=final_state), renumber(
        replace(
            records,
            intervals=(*records.intervals, *intervals),
            commands=(hold, stop, subsequent),
            actions=(replace(records.actions[0], command_seq_end=4),),
            physics=(*records.physics[:-1], final_physics),
            frames=(records.frames[0], final_frame),
        )
    )


def test_terminal_relation_cannot_point_to_the_preserved_before_action_frame():
    envelope, records = fixture()
    stale = replace(records.joins[0], relation="TERMINAL")
    view = api().validate_raw_episode_v3(
        envelope, renumber(replace(records, joins=(*records.joins, stale)))
    )
    assert view.status == "INVALID"
    assert view.counts["physics_recorded"] == view.counts["physics_expected"] == 121


def test_terminal_relation_to_actual_final_state_after_known_return_is_complete():
    envelope, records = fixture()
    terminal = replace(records.joins[1], relation="TERMINAL")
    view = api().validate_raw_episode_v3(
        envelope, renumber(replace(records, joins=(*records.joins, terminal)))
    )
    assert view.status == "COMPLETE", view.reasons
    assert view.utc_mapping == "UNAVAILABLE" and view.continuous_motion == "NOT_CERTIFIED"


def test_accepted_stop_cannot_be_erased_by_a_later_ordinary_command_false_flag():
    envelope, records = stop_order_fixture()
    view = api().validate_raw_episode_v3(envelope, records)
    assert view.status == "INVALID"
    assert view.counts["commands_expected"] == view.counts["commands_recorded"] == 3
    assert view.counts["allocated_actions"] == view.counts["recorded_actions"] == 1


def test_consistently_stopped_states_cannot_accept_ordinary_command_false_flag():
    envelope, records = fixture()
    previous = {**dict(envelope.reset_state_payload), "estop_engaged": True}
    physics = []
    for row in records.physics:
        post = {**dict(row.post_state_payload), "estop_engaged": True}
        physics.append(
            replace(row, previous_state_hash=hash_payload(previous), post_state_payload=post)
        )
        previous = post
    by_step = {row.physics_step: row.post_state_payload for row in physics}
    indices = {interval.interval_id: interval.start_step for interval in records.intervals}
    frames = tuple(
        replace(
            frame,
            joined_physics_observation_hash=hash_payload(dict(by_step[indices[frame.interval_id]])),
        )
        for frame in records.frames
    )
    view = api().validate_raw_episode_v3(
        replace(
            envelope,
            reset_state_payload={**dict(envelope.reset_state_payload), "estop_engaged": True},
            terminal_state_payload=previous,
        ),
        replace(records, physics=tuple(physics), frames=frames),
    )
    assert view.status == "INVALID"


@pytest.mark.parametrize("later", ["rejected", "hold"])
def test_latched_stop_keeps_rejected_ordinary_and_allowed_hold_original_records(later):
    envelope, records = stop_order_fixture(later=later)
    view = api().validate_raw_episode_v3(envelope, records)
    assert view.status == "COMPLETE", view.reasons
    assert view.counts["commands_recorded"] == 3
    assert records.commands[1].command_payload["after_emergency_stop"] is False
    assert records.physics[-2].post_state_payload["estop_engaged"] is False
    assert records.commands[-1].command_payload["after_emergency_stop"] is True


def test_rejected_ordinary_stop_flag_must_preserve_the_latch():
    envelope, records = stop_order_fixture(later="rejected")
    bad = replace(
        records.commands[-1],
        command_payload={
            **dict(records.commands[-1].command_payload),
            "after_emergency_stop": False,
        },
    )
    assert (
        api()
        .validate_raw_episode_v3(envelope, replace(records, commands=(*records.commands[:-1], bad)))
        .status
        == "INVALID"
    )


def test_later_physics_cannot_clear_an_accepted_stop_latch():
    envelope, cleared = stop_order_fixture(later="rejected", clear_state=True)
    assert api().validate_raw_episode_v3(envelope, cleared).status == "INVALID"


@pytest.mark.parametrize("late", [False, True])
def test_terminal_join_obeys_the_final_termination_boundary(late):
    envelope, records = fixture()
    base = next(i for i in records.intervals if i.interval_id == "attempt")
    first = clock_interval(base, "termination-1", "TERMINATION", 121, 121, 220100000, 220900000)
    intervals = (*records.intervals, first)
    if late:
        intervals += (
            clock_interval(
                base, "termination-final", "TERMINATION", 121, 121, 230000000, 240000000
            ),
        )
    terminal = replace(records.joins[1], relation="TERMINAL")
    view = api().validate_raw_episode_v3(
        envelope, renumber(replace(records, intervals=intervals, joins=(*records.joins, terminal)))
    )
    assert view.status == ("INVALID" if late else "COMPLETE"), view.reasons


def test_terminal_missing_actual_return_boundary_stays_incomplete():
    envelope, records = fixture()
    terminal = replace(records.joins[1], relation="TERMINAL")
    records = renumber(
        replace(
            records,
            actions=(replace(records.actions[0], returned_result=None),),
            joins=(*records.joins, terminal),
        )
    )
    view = api().validate_raw_episode_v3(envelope, records)
    assert view.status == "INCOMPLETE"
    assert "terminal_action_completion_boundary_unavailable" in view.reasons
    assert view.counts["allocated_actions"] == view.counts["recorded_actions"] == 1


@pytest.mark.parametrize("capture_after_rejection", [False, True])
def test_terminal_boundaries_consider_all_actions_including_later_zero_step_rejection(
    capture_after_rejection,
):
    envelope, records = fixture()
    base = next(i for i in records.intervals if i.interval_id == "attempt")
    rejected = clock_interval(
        base, "grasp-rejected", "EXECUTOR_ATTEMPT", 121, 121, 230000000, 240000000
    )
    action = replace(
        records.actions[0],
        span_id="span-2",
        step_id="grasp",
        interval_id=rejected.interval_id,
        command_seq_start=2,
        command_seq_end=2,
        returned_result=None,
        disposition="REJECTED",
        error="precondition_rejected",
        executed_step_payload=records.actions[0]
        .original_plan.requirements["grasp"]
        .original_step.model_dump(mode="json"),
    )
    before_second = replace(records.joins[1], span_id="span-2", relation="BEFORE_SUBMIT")
    terminal = replace(records.joins[1], relation="TERMINAL")
    extra_frames, extra_intervals = (), ()
    if capture_after_rejection:
        source = records.frames[-1]
        payload = {
            **dict(source.observation_payload),
            "frame_id": "terminal",
            "observation_id": "terminal",
            "captured_at": (NOW + timedelta(microseconds=241000)).isoformat(),
            "checksum_sha256": "",
        }
        observation = RGBDObservation.model_validate(payload)
        files = {
            name.replace("/after/", "/terminal/"): digest
            for name, digest in source.file_hashes.items()
        }
        acquisition = clock_interval(
            base, "acq-terminal", "ACQUISITION", 121, 121, 241000000, 242000000
        )
        frame = replace(
            source,
            acquisition_id="terminal",
            interval_id=acquisition.interval_id,
            observation_payload=observation.model_dump(mode="json"),
            file_hashes=files,
        )
        extra_frames, extra_intervals = (
            (frame,),
            (
                acquisition,
                clock_interval(
                    base, "earlier-termination", "TERMINATION", 121, 121, 220100000, 220900000
                ),
                clock_interval(
                    base, "final-termination", "TERMINATION", 121, 121, 240100000, 240900000
                ),
            ),
        )
        terminal = replace(
            terminal,
            acquisition_id="terminal",
            observation_id=observation.observation_id,
            checksum_sha256=observation.checksum_sha256,
        )
        envelope = replace(
            envelope,
            allocated_acquisition_ids=(*envelope.allocated_acquisition_ids, "terminal"),
            original_file_hashes={**dict(envelope.original_file_hashes), **files},
        )
    view = api().validate_raw_episode_v3(
        replace(envelope, allocated_action_span_ids=("span-1", "span-2")),
        renumber(
            replace(
                records,
                intervals=(*records.intervals, rejected, *extra_intervals),
                actions=(*records.actions, action),
                frames=(*records.frames, *extra_frames),
                joins=(*records.joins, before_second, terminal),
            )
        ),
    )
    assert view.status == ("COMPLETE" if capture_after_rejection else "INVALID"), view.reasons
    assert view.counts["allocated_actions"] == view.counts["recorded_actions"] == 2
    assert view.counts["rejected_actions"] == 1


@pytest.mark.parametrize("has_termination", [False, True])
def test_partial_action_terminal_requires_explicit_complete_termination(has_termination):
    envelope, records = fixture()
    base = next(i for i in records.intervals if i.interval_id == "attempt")
    partial = replace(
        base,
        end=None,
        end_step=None,
        end_sim_time_s=None,
        disposition="PARTIAL",
        error="reader-failed",
    )
    intervals = tuple(partial if row == base else row for row in records.intervals)
    if has_termination:
        intervals += (
            clock_interval(base, "termination", "TERMINATION", 121, 121, 220100000, 220900000),
        )
    terminal = replace(records.joins[1], relation="TERMINAL")
    view = api().validate_raw_episode_v3(
        envelope,
        renumber(
            replace(
                records,
                intervals=intervals,
                actions=(
                    replace(
                        records.actions[0],
                        returned_result=None,
                        disposition="PARTIAL",
                        error="reader-failed",
                    ),
                ),
                joins=(*records.joins, terminal),
            )
        ),
    )
    assert view.status == "INCOMPLETE", view.reasons
    assert (
        "terminal_action_completion_boundary_unavailable" in view.reasons
    ) is not has_termination
