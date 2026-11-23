"""Development clock boundaries, with a separate lease and no skill dispatch."""

import time
from contextlib import contextmanager
from pathlib import Path

import pytest
from scripts.graduation import dynamic_vision as original
from scripts.graduation.guarded_clock import GuardedClockEpisode
from scripts.graduation.perception_io import ROOT, read, write

from cloud_edge_robot_arm.contracts import Pose
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig

R1 = Path(
    "artifacts/research/process/20261004-ced-development/astra-rounds/"
    "round-graduation-dynamic-qualification-20261123/allocation-vision.public.json"
)


@contextmanager
def source_fixture(episode_type, directory):
    allocation = read(ROOT / R1)
    allocation["case"].update(visual_id="software-r2-no-dispatch/fixture", visual_seed=8300120)
    catalog = original.inventory()
    episode = episode_type(directory, allocation, original.digest(allocation), catalog)
    episode.backend.initialize(
        SimulatorConfig(
            model_path=str(ROOT / allocation["geometry"]["asset_path"]),
            seed=8300120,
            physics_dt_s=1 / 240,
            domain_randomization=False,
            render_rgb=True,
            render_depth=True,
        )
    )
    try:
        episode.backend.reset(
            PhysicalScenarioConfig(
                scenario_id="R2_SOFTWARE_NO_DISPATCH",
                seed=8300120,
                object_pose=Pose(x=0.45, y=0, z=0.035),
                object_yaw_rad=0,
            )
        )
        episode.fixture_physics = [episode.backend.current_physics_observation()]
        episode.capture("reset")
        with (
            episode.backend.observe_physics_steps(episode.fixture_physics.append),
            episode.backend.sensor_capture_on_demand(),
        ):
            episode.backend.step(120)
        episode.bootstrap()
        yield episode
    finally:
        episode.backend.shutdown()
        episode.owner.close(False)


def first_gate(episode, frame):
    return original.registered_collection_step_v2(
        episode.original,
        index=0,
        observation=frame,
        state=episode.robot.get_state(),
        tracker=episode.registered,
        lease_source=episode.active(),
        evidence_sink=episode.audit.append,
    )


def test_first_grounding_reuses_handoff_source(tmp_path):
    with source_fixture(GuardedClockEpisode, tmp_path) as episode:
        frame = episode.capture("MOVE_ABOVE/PRE")
        reference = episode.frames[-1][2]
        assert frame is reference
        assert frame.checksum_sha256 == episode.color._reference.checksum_sha256
        contract, step, binding, _, _ = first_gate(episode, frame)
        assert frame.checksum_sha256 == episode.registered._provider._reference.checksum_sha256
        assert step.skill.value == "MOVE_ABOVE"
        episode.action = episode.report["actions"][0]
        try:
            episode.admission(frame, "PRE", contract, step, binding, time.monotonic(), None)
        except original.ComponentStopped:
            pass
        pre = episode.action["pre"]
        assert pre["conditions"] and pre["shield"]["result"]["evaluated_rules"]
        time_rule = next(
            r for r in pre["shield"]["result"]["evaluated_rules"] if r["rule_id"] == "STEP_TIMEOUT"
        )
        assert time_rule["reason_code"] == "STEP_TIME_OK"
        assert all(r["status"] == "PASS" for r in pre["conditions"])
        assert episode.context_rows[-1]["relative"] == 0
        assert pre["frame_id"] == reference.frame_id
        assert not any(a.get("dispatched", False) for a in episode.report["actions"])
        write(
            tmp_path / "real-pre-no-dispatch.json",
            {
                "scope": "software source fixture with actual RGBD and live isolated lease",
                "fixture_seed": 8300120,
                "physics_step": episode.backend.total_physics_steps,
                "original_digest": episode.original.digest(),
                "binding_digest": binding.digest(),
                "current_frame_id": frame.frame_id,
                "current_checksum": frame.checksum_sha256,
                "decision": pre,
                "source_roles": episode.roles,
                "clock_contexts": episode.context_rows,
                "skill_dispatches": 0,
            },
        )
        duplicate = episode.capture("fixture/old-extra")
        with pytest.raises(ValueError, match="capture_not_new_and_monotonic"):
            first_gate(episode, duplicate)


def test_all_eight_structural_boundaries_retain_terminal_observation(tmp_path):
    with source_fixture(GuardedClockEpisode, tmp_path) as episode:
        previous = episode.frames[-1][2]
        retained = []
        with episode.backend.sensor_capture_on_demand():
            for row in episode.report["actions"]:
                name = row["skill"]
                assert episode.capture(name + "/PRE") is previous
                span = {"LIFT": 120, "RELEASE": 240}.get(name, 8)
                episode.backend.step(span)
                if name in {"LIFT", "RELEASE"}:
                    previous = episode.capture(name + "/dwell-" + str(span))
                    assert episode.capture(name + "/POST") is previous
                else:
                    previous = episode.capture(name + "/POST")
                assert episode.stage_source() is previous
                retained.append(previous.frame_id)
        assert len(set(retained)) == 8
        assert not any(a.get("dispatched", False) for a in episode.report["actions"])


def test_registration_and_servo_do_not_share_the_same_clock_rule(tmp_path):
    with source_fixture(GuardedClockEpisode, tmp_path) as episode:
        ref = episode.stage_source()
        target = Pose.model_validate(episode.report["bootstrap"]["resolver_candidate_m"])
        servo_ref = episode.capture("MOVE_ABOVE/servo_reference")
        servo = original.OpenCVServoFeedback(
            servo_ref,
            episode.color,
            episode.evidence,
            skill="MOVE_ABOVE",
            initial_target=target,
            marker_family_id=original.SIDE_PREPARE_ONLY_FAMILY,
            verify_mujoco_calibration=True,
        )
        first = episode.capture("MOVE_ABOVE/feedback")
        assert first.sim_time_s == servo_ref.sim_time_s and first.frame_id != servo_ref.frame_id
        servo.update(first)
        with pytest.raises(ValueError, match="servo repeated frame"):
            servo.update(first)
        with pytest.raises(ValueError, match="time gap or nonmonotonic time"):
            servo.update(episode.capture("MOVE_ABOVE/feedback"))
        with episode.backend.sensor_capture_on_demand():
            episode.backend.step(8)
            current = episode.capture("MOVE_ABOVE/feedback")
            servo.update(current)
        assert len(servo.records) == 2
        successful = episode.registered._provider.update(current)
        assert successful.status == "DERIVED"
        assert episode.registered._provider.update(ref).status == "UNKNOWN"


def test_wrong_stage_source_rejected_before_registered_conditions(tmp_path):
    with source_fixture(GuardedClockEpisode, tmp_path) as episode:
        wrong = episode.capture("software-foreign-role")
        with pytest.raises(ValueError, match="retained source frame"):
            episode.admission(wrong, "PRE", None, None, None, time.monotonic(), None)
        episode.backend.step(1)
        with pytest.raises(ValueError, match="terminal step/episode"):
            episode.capture("MOVE_ABOVE/PRE")


def test_origin_rejects_foreign_sources_invalid_order_and_resets_each_action():
    from scripts.graduation.guarded_clock import ActionClock

    one = ("fixture", 1, 1, "step-1", "MOVE_ABOVE")
    two = ("fixture", 1, 1, "step-2", "APPROACH")
    for invalid in [None, -1, True, False, 1.25]:
        with pytest.raises(ValueError):
            ActionClock(one, "ep", "binding", "frame", "sha", invalid)
    for start, identity in [(120, one), (2040, two)]:
        clock = ActionClock(identity, "ep", "binding", "frame", "sha", start)
        assert clock.position("PRE", start, identity, "ep") == 0
        for phase, tick, sign, episode in [
            ("PRE", start + 1, identity, "ep"),
            ("FEEDBACK", start, identity, "ep"),
            ("POST", start, identity, "ep"),
            ("PRE", start, ("other",), "ep"),
            ("PRE", start, identity, "other"),
            ("OTHER", start, identity, "ep"),
            ("PRE", start - 1, identity, "ep"),
            ("PRE", None, identity, "ep"),
            ("PRE", False, identity, "ep"),
        ]:
            with pytest.raises(ValueError):
                clock.position(phase, tick, sign, episode)
        for bad in [
            ("other", "frame", "sha"),
            ("binding", "other", "sha"),
            ("binding", "frame", "foreign"),
        ]:
            with pytest.raises(ValueError):
                clock.dispatch(start, identity, "ep", *bad)
        for invalid in (True, False, None, 0.5, -2):
            with pytest.raises(ValueError):
                clock.position("PRE", invalid, identity, "ep")
            with pytest.raises(ValueError):
                clock.dispatch(invalid, identity, "ep", "binding", "frame", "sha")
            with pytest.raises(ValueError):
                clock.returned_at(invalid, identity)
        clock.dispatch(start, identity, "ep", "binding", "frame", "sha")
        assert [clock.position("FEEDBACK", start + i, identity, "ep") for i in [0, 8, 16]] == [
            0,
            8,
            16,
        ]
        with pytest.raises(ValueError):
            clock.position("FEEDBACK", start + 8, identity, "ep")
        with pytest.raises(ValueError):
            clock.returned_at(start + 24, ("other",))
        assert clock.returned_at(start + 24, identity) == 24
        with pytest.raises(ValueError):
            clock.position("POST", start + 8, identity, "ep")
        assert clock.position("POST", start + 32, identity, "ep") == 32


def test_original_physics_timeout_rule_in_real_pre_and_post_contexts(tmp_path):
    from dataclasses import asdict, replace
    from datetime import UTC, datetime

    from cloud_edge_robot_arm.vision.native_completion_horizon import (
        controller_window_error_v2,
        registered_teacher_horizon_v2,
    )

    with source_fixture(GuardedClockEpisode, tmp_path) as e:
        f = e.capture("MOVE_ABOVE/PRE")
        contract, step, _, _, _ = first_gate(e, f)
        h = registered_teacher_horizon_v2("MOVE_ABOVE", step.timeout_ms)
        status = []
        for phase, elapsed, want, bad_horizon in [
            ("PRE", 0, "STEP_TIME_OK", False),
            ("FEEDBACK", 0, "STEP_TIME_OK", False),
            ("FEEDBACK", 8, "STEP_TIME_OK", False),
            ("POST", h.terminal_steps, "STEP_TIME_OK", False),
            ("POST", h.terminal_steps + 1, "STEP_TIMEOUT", False),
            ("PRE", None, "PHYSICS_STEP_INVALID", False),
            ("PRE", -1, "PHYSICS_STEP_INVALID", False),
            ("PRE", True, "STEP_TIME_OK", False),
            ("PRE", 1, "STEP_TIME_OK", False),
            ("PRE", 0, "HORIZON_INCOMPLETE", True),
        ]:
            chosen = (
                step if not bad_horizon else step.model_copy(update={"metadata": {}}, deep=True)
            )
            current = contract.model_copy(
                update={
                    "steps": [
                        chosen if item.step_id == step.step_id else item for item in contract.steps
                    ]
                },
                deep=True,
            )
            now = datetime.now(UTC)
            ctx = e.shield.context_builder.build(
                contract=current,
                step=chosen,
                robot_state=e.robot.get_state(),
                scene_version=current.scene_version,
                resolved_parameters=chosen.parameters,
                scene_updated_at=f.captured_at,
                telemetry_timestamp=now,
                wall_clock_now=now,
                step_started_at_mono=time.monotonic(),
                task_started_at_mono=e.owner.begin,
                monotonic_now=time.monotonic(),
                physics_step=elapsed,
            )
            result = (e.shield.post_check if phase == "POST" else e.shield.pre_check)(ctx)
            rule = next(r for r in result.evaluated_rules if r.rule_id == "STEP_TIMEOUT")
            assert rule.reason_code == want
            status.append(
                [
                    phase,
                    elapsed,
                    type(elapsed).__name__,
                    ctx.physics_step,
                    type(ctx.physics_step).__name__,
                    rule.reason_code,
                ]
            )
            if elapsed is True:
                assert type(ctx.physics_step) is int and ctx.physics_step == 1
                raw_control = ctx.model_copy(update={"physics_step": True})
                assert type(raw_control.physics_step) is bool
                verdict = e.shield.pre_check(raw_control)
                direct = next(r for r in verdict.evaluated_rules if r.rule_id == "STEP_TIMEOUT")
                assert direct.reason_code == "PHYSICS_STEP_INVALID"
                status.append(["raw_rule", True, "bool", True, "bool", direct.reason_code])
        write(
            tmp_path / "software-shield-clock-cases.json",
            {
                "scope": "software clocks, no dispatch",
                "source_frame": f.frame_id,
                "software_contexts": status,
            },
        )

    lift = registered_teacher_horizon_v2("LIFT", 8000)
    release = registered_teacher_horizon_v2("RELEASE", 1000)
    assert (lift.controller_deadline_steps, lift.terminal_steps) == (1920, 2040)
    assert (release.controller_deadline_steps, release.terminal_steps) == (240, 480)
    assert (
        controller_window_error_v2(lift, 2040, {"physics_steps": 2040, "contact_hold_s": 0.5})
        is None
    )
    assert controller_window_error_v2(lift, 2040, {}) == "controller_lift_hold_incomplete"
    assert (
        controller_window_error_v2(lift, 2041, {"physics_steps": 2041, "contact_hold_s": 0.5})
        == "controller_exceeded_registered_deadline"
    )
    assert controller_window_error_v2(release, 12, {}) is None
    assert controller_window_error_v2(release, 240, {}) is None
    assert controller_window_error_v2(release, 241, {}) == "controller_exceeded_registered_deadline"
    short = replace(release, terminal_steps=470)
    assert (
        controller_window_error_v2(short, 240, {}) == "release_open_return_leaves_insufficient_tail"
    )
    assert asdict(lift)["builtin_tail_steps"] == 120


def test_real_registry_validates_eight_pixel_grounded_parameters_without_skill_dispatch(tmp_path):
    from cloud_edge_robot_arm.edge.runtime.skill_registry import SkillRegistry
    from cloud_edge_robot_arm.simulation.mujoco.motion_controller import MotionTarget

    rows = []
    with source_fixture(GuardedClockEpisode, tmp_path) as e:
        registry = SkillRegistry.default()
        with e.backend.sensor_capture_on_demand():
            for index, action in enumerate(e.report["actions"]):
                if index:
                    e.backend.step(8)
                f = e.stage_source() if not index else e.capture("software/registry-input")
                _, step, _, _, _ = original.registered_collection_step_v2(
                    e.original,
                    index=index,
                    observation=f,
                    state=e.robot.get_state(),
                    tracker=e.registered,
                    lease_source=e.active(),
                )
                params = registry.definition_for(step.skill).validate(step.parameters)
                assert params is not None
                servo = step.parameters.get("target_pose") is not None and step.skill.value not in {
                    "GRASP",
                    "RELEASE",
                }
                if servo:
                    target = MotionTarget(
                        Pose.model_validate(step.parameters["target_pose"]), (1, 0, 0, 0)
                    )
                    assert target.position.z >= 0
                rows.append(
                    {"skill": action["skill"], "servo": servo, "timeout_ms": step.timeout_ms}
                )
    assert sum(r["servo"] for r in rows) == 6 and len(rows) == 8
    write(
        tmp_path / "software-eight-registry-checks.json",
        {"source": "live RGBD, no skill dispatch", "skills": rows},
    )


def test_recorded_executor_validates_real_result_types_and_command_contract(tmp_path):
    from dataclasses import replace
    from datetime import UTC, datetime, timedelta
    from types import SimpleNamespace

    from scripts.graduation.guarded_clock import (
        ActionClock,
        RecordedExecutor,
        action_identity,
        command_evidence,
    )

    from cloud_edge_robot_arm.contracts import ActionResult, SkillName
    from cloud_edge_robot_arm.edge.runtime.skill_executor import StepExecutionResult
    from cloud_edge_robot_arm.errors import StructuredError

    now = datetime.now(UTC)
    frame = SimpleNamespace(
        frame_id="software-frame",
        checksum_sha256="software-src",
        episode_id="software-ep",
        captured_at=now,
    )
    contract = SimpleNamespace(task_id="software-task", plan_version=1, command_seq=1)
    step = SimpleNamespace(step_id="step-1", skill=SkillName.MOVE_ABOVE, timeout_ms=8000)
    details = ActionResult(
        action_id="software-record",
        action_type="MOVE_ABOVE",
        started_at=now,
        finished_at=now,
        success=True,
        duration_ms=0,
        details={"physics_steps": 8},
    )
    success = StepExecutionResult(
        contract.task_id, step.step_id, "MOVE_ABOVE", 1, True, None, details, 0, now
    )
    error = StructuredError(code="SOFTWARE_CONTROL_FAILURE", message="recorded software example")
    failed = replace(
        success,
        success=False,
        error=error,
        action_result=details.model_copy(update={"success": False, "error": error}),
    )
    source_rows = [
        {
            "episode_id": frame.episode_id,
            "physics_step": 120 + i,
            "command_seq": i + 1,
            "type": name,
            "accepted": keep,
            "reason": "" if keep else "software rejected",
        }
        for i, (name, keep) in enumerate(
            [
                ("joint_target", True),
                ("joint_target", False),
                ("hold_current_joints", True),
                ("emergency_stop", True),
            ]
        )
    ]
    evidence = []
    for receipt in [
        success,
        failed,
        replace(failed, action_result=None),
        replace(success, task_id="other"),
        replace(success, skill="LIFT"),
        replace(success, attempt=2),
        {},
    ]:
        backend = SimpleNamespace(total_physics_steps=120, command_records=[])
        clock = ActionClock(
            action_identity(contract, step),
            frame.episode_id,
            "binding",
            frame.frame_id,
            frame.checksum_sha256,
            120,
        )
        episode = SimpleNamespace(
            backend=backend,
            stage_source=lambda: frame,
            active=lambda: None,
            action_clock=clock,
            pending_dispatch=(frame, now + timedelta(seconds=120)),
            pending_binding="binding",
            action={"dispatch_step": 120},
            audit=[],
        )

        class SoftwareRecordedReturn:
            def execute_attempt(self, *, contract, step, attempt, answer=receipt, source=backend):
                if type(answer) is StepExecutionResult and answer.action_result is not None:
                    source.command_records.extend(source_rows)
                    source.total_physics_steps = 128
                return answer

        adapter = RecordedExecutor(episode, SoftwareRecordedReturn())
        if type(receipt) is not StepExecutionResult or (
            receipt.task_id,
            receipt.skill,
            receipt.attempt,
        ) != (contract.task_id, "MOVE_ABOVE", 1):
            with pytest.raises(ValueError, match="identity"):
                adapter.execute_attempt(contract=contract, step=step, attempt=1)
        else:
            actual = adapter.execute_attempt(contract=contract, step=step, attempt=1)
            assert actual is receipt
            assert episode.action["return_evidence"]["error_code"] == receipt.error_code
            assert episode.action["command_records"] == (
                4 if actual.action_result is not None else 0
            )
            evidence.append(episode.action)
    for changed in [
        {k: v for k, v in source_rows[0].items() if k != "accepted"},
        {**source_rows[0], "episode_id": "other"},
        {**source_rows[0], "command_seq": 0},
        {**source_rows[0], "physics_step": 119},
        {**source_rows[0], "physics_step": 129},
        {**source_rows[0], "accepted": 1},
    ]:
        with pytest.raises(ValueError, match="command record"):
            command_evidence([changed], frame.episode_id, 120, 128, 1)
    write(
        tmp_path / "software-recorded-executor.json",
        {
            "scope": "SOFTWARE_ONLY recorded returns",
            "new_physical_skills": 0,
            "scenarios": evidence,
        },
    )


def test_public_score_cli_separates_actual_decisions_from_software_faults(tmp_path):
    import copy
    import os
    import subprocess
    import sys
    from dataclasses import asdict

    from scripts.graduation.perception_io import sha

    alloc = read(ROOT / R1)
    alloc["case"]["visual_id"] = "software-score-only/source"
    alloc["r1_allocation_sha256"] = sha(ROOT / R1)
    alloc["software_receipt_sha256"] = "0" * 64
    alloc_path = tmp_path / "software-allocation.json"
    write(alloc_path, alloc)
    with source_fixture(GuardedClockEpisode, tmp_path) as e:
        frame = e.capture("MOVE_ABOVE/PRE")
        contract, step, binding, _, _ = first_gate(e, frame)
        e.action = e.report["actions"][0]
        e.action.update(entered_step=120, end_step=120, status="PASS", dispatched=False)
        try:
            e.admission(frame, "PRE", contract, step, binding, time.monotonic(), None)
        except original.ComponentStopped:
            pass
        report = copy.deepcopy(e.report)
        report["lease_summary"] = {"scope": "SOFTWARE_ONLY cli-shape fixture"}
        originals = e.frames
        samples = [asdict(s) for s in e.fixture_physics]
        audit = copy.deepcopy(e.audit)
    cases = {
        "normal": "COMPONENT_SEQUENCE_RETURNED",
        "refused": "REGISTERED_CONDITION_OR_SHIELD_STOP",
        "before_executor": "ENGINEERING_BLOCKED",
        "after_executor": "PRODUCTION_CONTROLLER_REPORTED_FAILURE",
        "foreign_value_error": "ENGINEERING_BLOCKED",
    }
    outcomes = []
    for label, expected in cases.items():
        directory = tmp_path / label
        directory.mkdir()
        local = copy.deepcopy(report)
        stage = local["actions"][0]
        if label != "normal":
            stage["status"] = "STOPPED"
            phase = "PRE" if label == "refused" else "CONTROLLER"
            error_type = {
                "refused": "ComponentStopped",
                "after_executor": "ComponentStopped",
                "foreign_value_error": "ValueError",
                "before_executor": "NameError",
            }[label]
            local["stop"] = {
                "phase": phase,
                "type": error_type,
                "origin": "test_software_case.py",
                "function": "software_case",
                "reason": "explicit software case",
                "skill": "MOVE_ABOVE",
                "physics_step": 120,
            }
            if label == "refused":
                stage["pre"]["shield"]["allowed"] = False
            if label == "after_executor":
                stage.update(
                    dispatched=True,
                    executor_entered=True,
                    dispatch_step=120,
                    backend_return_step=120,
                    return_evidence={
                        "action_result_present": True,
                        "success": False,
                        "error_code": "SOFTWARE_STOP",
                    },
                )
        rows = []
        for i, (tick, role, obs) in enumerate(originals):
            filename = f"source-{i}.json"
            write(directory / filename, obs.model_dump(mode="json"))
            rows.append(
                {
                    "physics_step": tick,
                    "label": role,
                    "frame_id": obs.frame_id,
                    "checksum_sha256": obs.checksum_sha256,
                    "file": filename,
                    "file_sha256": sha(directory / filename),
                }
            )
        write(
            directory / "pixel-index.json",
            {
                "allocation_sha256": sha(alloc_path),
                "scene": frame.scene_id,
                "episode": frame.episode_id,
                "frames": rows,
            },
        )
        write(
            directory / "offline-truth.json",
            {
                "allocation_sha256": sha(alloc_path),
                "asset_sha256": alloc["asset_sha256"],
                "episode": frame.episode_id,
                "samples": samples,
            },
        )
        local_audit = list(audit)
        if label != "normal":
            local_audit.append(
                {
                    "phase": local["stop"]["phase"],
                    "stop_stack": [
                        {"source": "software_case.py", "line": 1, "function": "software_case"}
                    ],
                }
            )
        write(directory / "run.json", local)
        write(directory / "online-audit.json", original.plain(local_audit))
        write(
            directory / "acquisition-seal.json",
            {
                k: sha(directory / name)
                for k, name in {
                    "index_sha256": "pixel-index.json",
                    "truth_sha256": "offline-truth.json",
                    "run_sha256": "run.json",
                    "audit_sha256": "online-audit.json",
                }.items()
            },
        )
        cli = [sys.executable, "-m", "scripts.graduation.guarded_clock_score"]
        common = [str(directory), str(alloc_path), sha(alloc_path)]
        environment = {**os.environ, "PYTHONPATH": str(ROOT / "src") + os.pathsep + str(ROOT)}
        subprocess.run([*cli, "pixels", *common], cwd=ROOT, env=environment, check=True)
        output = directory / "score.json"
        subprocess.run(
            [*cli, "score", *common, "--output", str(output)], cwd=ROOT, env=environment, check=True
        )
        scored = read(output)
        assert scored["observed_outcome"]["kind"] == expected
        assert scored["physics_clock"]["independent_source_step_and_hash_checks"] == 1
        outcomes.append([label, expected, sha(output)])
    write(
        tmp_path / "software-five-score-cases.json",
        {
            "scope": "SOFTWARE_ONLY score and stop shapes",
            "physical_skill_dispatches": 0,
            "results": outcomes,
        },
    )
