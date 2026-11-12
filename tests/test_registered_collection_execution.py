"""Registered coordinates retain the original collection conditions and authority boundary."""

from dataclasses import replace

import pytest

from cloud_edge_robot_arm.contracts import SkillName
from cloud_edge_robot_arm.vision import owner_registration as owner
from cloud_edge_robot_arm.vision import worker_owner
from tests.test_registered_grounding_binding import binding_data


def collection_type():
    assert hasattr(owner, "RegisteredCollectionStepBinding"), "collection source binding missing"
    return owner.RegisteredCollectionStepBinding


def test_collection_binding_api():
    assert collection_type()


@pytest.mark.parametrize(
    "skill",
    [
        SkillName.MOVE_ABOVE,
        SkillName.APPROACH,
        SkillName.GRASP,
        SkillName.LIFT,
        SkillName.MOVE_TO_REGION,
        SkillName.PLACE,
        SkillName.RELEASE,
        SkillName.RETREAT,
    ],
)
def test_collection_binding_preserves_constraints_without_becoming_legacy(
    tmp_path, monkeypatch, skill
):
    data = binding_data(tmp_path, monkeypatch, skill)
    prepared = owner.prepare_registered_step_binding(**data)
    result = collection_type().from_prepared(
        prepared, collection_policy_id="registered-model-collection-v1"
    )
    payload = result.to_payload()
    assert payload["schema_version"] == "registered.collection.binding.v1"
    assert payload["execution_authority"] is False
    assert payload["native_authority"] == "UNAVAILABLE"
    assert result.prepared.to_payload() == prepared.to_payload()
    assert result.prepared.to_payload()["prepare_only"] is True
    assert result.grounded_step.parameters == prepared.grounded_step.parameters
    assert result.grounded_step.timeout_ms == 10000
    assert not isinstance(result, owner.StepGroundingBinding)
    assert not isinstance(result, owner.RegisteredPreparedStepBinding)
    effect = worker_owner.registered_collection_effect_conditions(data["original"], result)
    assert [c.name for c in effect] == [
        c.name for c in data["original"].requirements["move"].postconditions
    ]
    for condition in effect:
        if condition.name == "tcp_at_resolved_target":
            assert [condition.tolerances["target_" + a] for a in "xyz"] == [
                prepared.grounded_step.parameters["target_pose"][a] for a in "xyz"
            ]
    with pytest.raises(ValueError, match="concrete"):
        worker_owner.grounded_worker_effect_conditions(data["original"], result)
    saved = result.digest()
    payload["prepared"]["grounded_step"]["parameters"]["object_id"] = "foreign"
    assert result.digest() == saved
    assert type(result).from_payload(result.to_payload()).digest() == saved


@pytest.mark.parametrize(
    "field,value",
    [
        ("execution_authority", True),
        ("native_authority", "AVAILABLE"),
        ("collection_policy_id", "rgbd-top-grasp-v1"),
        ("extra", "unregistered"),
    ],
)
def test_collection_binding_rejects_authority_relabelling(tmp_path, monkeypatch, field, value):
    data = binding_data(tmp_path, monkeypatch)
    cls = collection_type()
    result = cls.from_prepared(
        owner.prepare_registered_step_binding(**data),
        collection_policy_id="registered-model-collection-v1",
    )
    payload = result.to_payload()
    payload[field] = value
    with pytest.raises((ValueError, TypeError)):
        cls.from_payload(payload)


def test_collection_effect_rejects_foreign_original(tmp_path, monkeypatch):
    data = binding_data(tmp_path, monkeypatch)
    result = collection_type().from_prepared(
        owner.prepare_registered_step_binding(**data),
        collection_policy_id="registered-model-collection-v1",
    )
    foreign = replace(data["original"], proposal_hash="f" * 64)
    with pytest.raises(ValueError, match="binding"):
        worker_owner.registered_collection_effect_conditions(foreign, result)


def test_collection_binding_never_accepts_a_plain_mapping(tmp_path, monkeypatch):
    data = binding_data(tmp_path, monkeypatch)
    prepared = owner.prepare_registered_step_binding(**data)
    with pytest.raises(TypeError):
        collection_type().from_prepared(
            prepared.to_payload(), collection_policy_id="registered-model-collection-v1"
        )


def test_protocol_api():
    from cloud_edge_robot_arm.research import native_calibration_collection as protocol_api

    assert hasattr(protocol_api, "prepare_registered_collection_protocol"), "v7 protocol missing"


def test_collection_consumer_api():
    from cloud_edge_robot_arm.research import native_collection_grounding as collection

    assert hasattr(collection, "registered_collection_step"), (
        "registered collection producer missing"
    )


def test_protocol_does_not_release_an_assignment_or_create_runtime(tmp_path):
    from cloud_edge_robot_arm.research import native_calibration_collection as protocol_api
    from cloud_edge_robot_arm.research.native_collection_application import (
        NativeCollectionApplication,
    )

    destination = tmp_path / "protocol"
    protocol_api.prepare_registered_collection_protocol(output=destination)
    recipe = protocol_api.read_protocol(destination)
    assert recipe["schema_version"] == "native.calibration.operational.v7"
    assert recipe["assignments"] == recipe["released_assignments"] == []
    assert not any(recipe["authorized_actual_budget"].values())
    assert recipe["collection_policy_id"] == "registered-model-collection-v1"
    with pytest.raises(ValueError, match="release"):
        NativeCollectionApplication.from_startup(
            destination, assignment_id="native-r595-0001", output=tmp_path / "run"
        )
    assert not (tmp_path / "run").exists()
    assert not (destination / "claims").exists()


@pytest.mark.parametrize("change", ["release", "budget", "schema", "source"])
def test_v7_recipe_cannot_be_relabelled_or_relaxed(tmp_path, change):
    import json

    from cloud_edge_robot_arm.research import native_calibration_collection as protocol_api

    destination = tmp_path / "protocol"
    protocol_api.prepare_registered_collection_protocol(output=destination)
    recipe = protocol_api.read_protocol(destination)
    if change == "release":
        recipe["execution_release"] = "RELEASED"
    elif change == "budget":
        recipe["authorized_actual_budget"]["actions"] = 1
    elif change == "schema":
        recipe["schema_version"] = "native.calibration.operational.v2"
    else:
        recipe["source_hashes"].pop(next(iter(recipe["source_hashes"])))
        recipe["source_generation"] = protocol_api.digest(recipe["source_hashes"])
    (destination / "protocol.json").write_text(json.dumps(recipe))
    with pytest.raises(ValueError):
        protocol_api.read_protocol(destination)


def consumer_context(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from cloud_edge_robot_arm.research import native_calibration_collection as protocol_api
    from cloud_edge_robot_arm.research import native_collection_application as application
    from cloud_edge_robot_arm.research import native_collection_grounding as collection
    from cloud_edge_robot_arm.vision.native_calibration import NativeGeometryRegistration
    from tests.test_registered_grounding_preparation import ROOT, context

    protocol_path, args, clock = context(tmp_path, monkeypatch)
    monkeypatch.setattr(collection, "datetime", application.datetime)
    protocol_api.prepare_registered_collection_protocol(output=tmp_path / "v7")
    protocol = protocol_api.read_protocol(tmp_path / "v7")
    legacy, evidence = collection.bootstrap_collection_tracker(
        args["reference_observation"], protocol["geometry"]
    )
    registered = collection.bootstrap_registered_collection_tracker_v1(
        args["reference_observation"],
        NativeGeometryRegistration(protocol["geometry"]),
        source_root=ROOT,
        source_hashes=protocol["source_hashes"],
    )
    records = []
    live = SimpleNamespace(
        repository=args["repository"],
        original=args["original"],
        tracker=legacy,
        registered_tracker=registered,
        grounding_evidence=evidence,
        robot=SimpleNamespace(get_state=lambda: args["robot_state"]),
        recorder=SimpleNamespace(
            record_grounding=records.append,
            acquisition_source=lambda: {
                "acquisition_id": "synthetic-current",
                "path": "synthetic",
                "sha256": "a" * 64,
            },
        ),
    )

    def consume():
        return {
            "live_owner": {
                "lease": application._registered_lease(
                    live.repository, live.original.identity
                ).to_payload()
            }
        }

    return application, collection, live, protocol, args, clock, records, consume


def test_actual_collection_helper_uses_new_model_binding_and_preserves_old_unknown(
    tmp_path, monkeypatch
):
    application, _, live, protocol, args, _, records, consume = consumer_context(
        tmp_path, monkeypatch
    )
    _, step, binding, online, checkpoint = application._collect_grounded_step(
        live, 0, args["observation"], protocol, consume_capture=consume
    )
    assert type(binding) is collection_type()
    assert step.parameters["target_pose"]["z"] > 0.1
    assert online.visual_facts == {}
    assert checkpoint.current_step_id == "move"
    assert records[0]["binding"]["schema_version"] == "registered.collection.binding.v1"
    assert records[0]["lease_source"]["lease_id"] == live.original.identity.lease_id
    assert records[0]["inputs"]["object_surface_visibility"] == "UNKNOWN"
    from cloud_edge_robot_arm.edge.evidence.conditions import (
        ConditionSpec,
        OnlineEvidenceSnapshot,
        evaluate_conditions,
    )

    facts = live.tracker.facts(args["observation"], args["robot_state"])
    verdict = evaluate_conditions(
        [ConditionSpec("target_visible", "object")],
        OnlineEvidenceSnapshot(args["observation"], args["robot_state"], facts),
        now=args["observation"].captured_at,
    )[0]
    assert verdict.status.value == "UNKNOWN"


@pytest.mark.parametrize("problem", ["expired", "cancelled", "source", "write"])
def test_registered_collection_does_not_publish_invalid_or_unwritten_binding(
    tmp_path, monkeypatch, problem
):
    from datetime import timedelta

    application, _, live, protocol, args, clock, records, consume = consumer_context(
        tmp_path, monkeypatch
    )
    if problem == "expired":
        clock[0] = args["observation"].captured_at + timedelta(seconds=5)
    elif problem == "cancelled":
        live.repository.request_cancel(live.original.identity.job_id)
    elif problem == "source":
        protocol["source_hashes"] = {**protocol["source_hashes"], "src/foreign.py": "f" * 64}
    else:

        def full_disk(_value):
            raise OSError("synthetic full disk")

        live.recorder.record_grounding = full_disk
    with pytest.raises((ValueError, RuntimeError, OSError)):
        application._collect_grounded_step(
            live, 0, args["observation"], protocol, consume_capture=consume
        )
    assert records == []


def test_registered_collection_cli_prepares_only_its_distinct_protocol(
    tmp_path, monkeypatch, capsys
):
    import json
    import sys

    from scripts.collect_native_calibration import main

    from cloud_edge_robot_arm.research.native_calibration_collection import read_protocol

    output = tmp_path / "cli"
    monkeypatch.setattr(
        sys,
        "argv",
        ["collect", "--prepare-registered-collection-protocol", "--output", str(output)],
    )
    main()
    summary = json.loads(capsys.readouterr().out)
    assert summary["execution_admitted"] is False
    assert read_protocol(output)["schema_version"] == "native.calibration.operational.v7"
    assert not list(output.rglob("*.db"))


def test_registered_collection_cli_rejects_execution_arguments_before_output(tmp_path, monkeypatch):
    import sys

    from scripts.collect_native_calibration import main

    output = tmp_path / "rejected"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "collect",
            "--prepare-registered-collection-protocol",
            "--assignment-id",
            "native-r595-0001",
            "--output",
            str(output),
        ],
    )
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    assert not output.exists()


def test_r643_v8_protocol_and_source_producer(tmp_path):
    from cloud_edge_robot_arm.research import native_calibration_collection as protocol_api
    from cloud_edge_robot_arm.research import native_collection_grounding as grounding
    from cloud_edge_robot_arm.research.native_collection_application import (
        NativeCollectionApplication,
    )

    make = getattr(protocol_api, "prepare_registered_collection_protocol_v2", None)
    assert callable(make), "v8 occlusion protocol missing"
    make(output=tmp_path / "protocol")
    protocol = protocol_api.read_protocol(tmp_path / "protocol")
    assert protocol["schema_version"] == "native.calibration.operational.v8"
    assert protocol["condition_version"] == "registered-model-condition-v2"
    assert protocol["assignments"] == protocol["released_assignments"] == []
    assert not any(protocol["authorized_actual_budget"].values())
    assert callable(getattr(grounding, "build_collection_contract_v2", None))
    assert callable(getattr(grounding, "registered_collection_step_v2", None))
    with pytest.raises(ValueError, match="prepare-only"):
        NativeCollectionApplication.from_startup(
            tmp_path / "protocol", assignment_id="none", output=tmp_path / "never"
        )
    assert not (tmp_path / "never").exists()


def ordered_v8_context(
    tmp_path, monkeypatch, *, explicit=None, shield_fault=None, advancing_clock=False
):
    """Genuine ordered consumer; only sensor/physical horizon uses fresh software fixtures."""
    import base64
    import io
    import time
    from contextlib import ExitStack
    from datetime import timedelta
    from types import SimpleNamespace

    from PIL import Image

    from cloud_edge_robot_arm.edge.runtime.skill_executor import StepExecutionResult
    from cloud_edge_robot_arm.research import native_calibration_collection as protocols
    from cloud_edge_robot_arm.research import native_collection_application as api
    from cloud_edge_robot_arm.research import native_collection_grounding as grounding
    from cloud_edge_robot_arm.research import raw_episode_v3 as raw
    from cloud_edge_robot_arm.research.native_calibration_collection import canonical, digest
    from cloud_edge_robot_arm.simulation.models import SensorFrame
    from cloud_edge_robot_arm.simulation.mujoco import native_horizon
    from cloud_edge_robot_arm.vision import registered_object_tracking, tracking
    from tests.test_native_collection_authority import application, source_recorder
    from tests.test_registered_grounding_preparation import ROOT, context, nominal_scene
    from tests.test_registered_object_geometry import revised

    _, args, clock = context(tmp_path / "sql", monkeypatch)
    actual_clock = api.datetime
    stamp = clock[0]
    if advancing_clock:

        class AdvancingClock(actual_clock):
            @classmethod
            def now(cls, tz=None):
                value = super().now(tz)
                clock[0] += timedelta(microseconds=1)
                return value

        actual_clock = AdvancingClock
    _, ref, destination, reg, _, _, _, state = nominal_scene(tmp_path / "scene", monkeypatch)
    for module in (api, grounding, tracking, registered_object_tracking, worker_owner):
        monkeypatch.setattr(module, "datetime", actual_clock)
    ref = revised(ref, captured_at=stamp, episode_id=args["reference_observation"].episode_id)
    destination = revised(
        destination, captured_at=stamp + timedelta(seconds=0.5), episode_id=ref.episode_id
    )
    protocol = protocols._registered_collection_protocol_v2()
    app = application(tmp_path / "application")
    app.prepare_once()
    live = api._REGISTRY[app]
    recorder, backend, capture, unused_owner, _ = source_recorder(tmp_path / "recorder")
    from cloud_edge_robot_arm.research import native_full_horizon_recorder as recorder_api

    monkeypatch.setattr(recorder_api, "datetime", actual_clock)
    from cloud_edge_robot_arm.vision import raw_recorder_v3 as raw_time

    monkeypatch.setattr(raw_time, "datetime", actual_clock)
    unused_owner.close()
    repository = args["repository"]
    job = repository.get_job(args["original"].identity.job_id)
    app.repository = live.repository = live.worker.repository = repository
    live.worker.worker_id = job.worker_id
    live.worker.active_job_id = live.job_id = job.job_id
    live.worker_origin = (job.job_id, time.monotonic(), stamp)
    live.worker._active_task_origin = live.worker_origin
    live.job_basis = api._job_basis(job)
    live.protocol_json = canonical(protocol)
    live.entered = True
    live.recorder, live.backend, live.capture = recorder, backend, capture
    live.executor, live.robot = recorder.executor, recorder.executor._robot
    current_state = [
        state.model_copy(update={"gripper_open": True, "holding_object_id": None}, deep=True)
    ]
    monkeypatch.setattr(live.robot, "get_state", lambda: current_state[0])
    recorder.application, recorder.owner = app, live.owner
    recorder.source_root, recorder.source_hashes = ROOT, dict(protocol["source_hashes"])
    backend._episode_id = ref.episode_id
    selected = [ref]
    counter = [0]

    def sensor(_data, **_kwargs):
        counter[0] += 1
        obs = selected[0]
        pixels = Image.open(io.BytesIO(base64.b64decode(obs.rgb_png_base64))).tobytes()
        frame = SensorFrame(
            frame_id=f"ordered-{counter[0]}",
            sim_time_s=backend.get_sim_time(),
            width=obs.width,
            height=obs.height,
            rgb=pixels,
            depth=obs.depth_values(),
            intrinsics=tuple(obs.intrinsics),
            camera_to_world=tuple(obs.camera_to_world),
            captured_at=clock[0],
            episode_id=ref.episode_id,
            scene_id=obs.scene_id,
            calibration_version=obs.calibration_version,
            valid_mask=obs.valid_mask_bytes(),
        )
        return frame, (-1,) * (obs.width * obs.height), {-1: "background"}, ("a" * 64,) * 3

    backend._camera = SimpleNamespace(capture_with_instances=sensor)
    calls = []

    def executor(*, contract, step, attempt):
        from cloud_edge_robot_arm.contracts import ActionResult

        calls.append(step.skill.value)
        before = current_state[0].model_dump(mode="json")
        started = clock[0]
        commands_before = len(backend.command_records)
        updates = {}
        if "target_pose" in step.parameters:
            updates["tcp_pose"] = current_state[0].tcp_pose.model_copy(
                update=step.parameters["target_pose"]
            )
        if step.skill.value == "GRASP":
            updates.update(gripper_open=False, holding_object_id="object")
        current_state[0] = current_state[0].model_copy(update=updates, deep=True)
        finished = clock[0]
        assert len(backend.command_records) == commands_before
        action = ActionResult(
            success=True,
            action_id=f"software-{step.step_id}-{attempt}",
            action_type=step.skill.value,
            started_at=started,
            finished_at=finished,
            duration_ms=round((finished - started).total_seconds() * 1000),
            state_before=before,
            state_after=current_state[0].model_dump(mode="json"),
            details=dict(
                scope="SOFTWARE_ONLY_NO_PHYSICS",
                native_authority="UNAVAILABLE",
                physical_commands=0,
                acknowledgement="software_callback_completed",
                state_source="fixture_current_state",
            ),
        )
        return StepExecutionResult(
            task_id=contract.task_id,
            step_id=step.step_id,
            skill=step.skill.value,
            attempt=attempt,
            success=True,
            error=None,
            action_result=action,
            duration_ms=action.duration_ms,
            timestamp=finished,
        )

    monkeypatch.setattr(live.executor, "execute_attempt", executor)

    def software_horizon(**kw):
        import json
        from dataclasses import asdict

        dispatch = backend.total_physics_steps
        result = kw["recorder"].execute_attempt(
            contract=kw["contract"], step=kw["step"], attempt=1, grounding=kw["grounding"]
        )
        returned = backend.total_physics_steps
        capture_fresh()
        step = kw["step"]
        receipt = native_horizon.FullHorizonExecutionReceipt(
            step.step_id,
            step.skill.value,
            live.original.digest(),
            digest(step.model_dump(mode="json")),
            json.dumps(asdict(kw["horizon"])),
            dispatch,
            returned,
            backend.total_physics_steps,
            json.dumps(protocols.detached(asdict(result))),
            None,
            recorder.current_capture()[0],
            True,
            (),
        )
        kw["recorder"].record_horizon(receipt)
        return receipt

    monkeypatch.setattr(native_horizon, "_run_registered_horizon", software_horizon)

    def capture_fresh():
        backend._total_physics_steps += 6
        backend._data.time = backend.total_physics_steps / 240
        clock[0] = stamp + timedelta(seconds=backend.get_sim_time())
        return recorder.capture()

    stack = ExitStack()
    stack.enter_context(capture)
    stack.enter_context(recorder)
    stack.enter_context(backend.enforce_execution_guard(lambda _: None, event_limit=4096))
    stack.enter_context(backend.capture_each_physics_step(max_captures=64))
    backend._total_physics_steps = 114
    backend._data.time = 114 / 240
    ref = capture_fresh()
    compiler_reference = ref
    compiler_reference_source = recorder.acquisition_source()
    lease = api._registered_lease(repository, args["original"].identity)
    live.original = grounding.build_collection_contract_v2(
        assignment={"software": "ordered"},
        current_owner=dict(
            issued_at=stamp,
            deadline_at=stamp + timedelta(seconds=8),
            task_id=job.job_id,
            plan_id="ordered-v8",
            lease=lease,
            role_sha256="a" * 64,
        ),
        geometry=protocol["geometry"],
        source_hashes=protocol["source_hashes"],
        observation=ref,
    )
    if explicit is not None:
        contract = live.original.contract
        steps = list(contract.steps)
        if explicit == "LIFT_POST":
            steps[3] = steps[3].model_copy(update={"success_conditions": ["object_lifted"]})
        elif explicit == "RELEASE_PRE":
            steps[6] = steps[6].model_copy(
                update={"preconditions": ["object_inside_target_region"]}
            )
        else:
            field = "preconditions" if explicit == "PRE" else "success_conditions"
            steps[4] = steps[4].model_copy(update={field: ["target_visible"]})
        contract = contract.model_copy(update={"steps": steps}, deep=True)
        before = live.original
        compiled = worker_owner.compile_worker_original_plan_v2(
            lease_source=lease,
            identity=before.identity,
            contract=contract,
            observation=ref,
            proposal_hash=before.proposal_hash,
            role_bundle_hash=before.role_bundle_hash,
            source_hashes=before.source_hashes,
            registered_at=before.registered_at,
            task_deadline_at=before.task_deadline_at,
            verification_deadline_at=before.verification_deadline_at,
        )
        live.original = owner.freeze_original_visual_plan(
            **{
                **compiled.freeze_inputs(),
                "requirements": {
                    k: replace(v, expected_duration_s=before.requirements[k].expected_duration_s)
                    for k, v in compiled.requirements.items()
                },
            }
        )
    clock[0] += timedelta(microseconds=1)
    ref = recorder.capture()
    reference_source = recorder.acquisition_source()
    grounding.validate_registration_handoff(
        live.original,
        lease.to_payload(),
        compiler_reference,
        ref,
        step_before=120,
        step_after=120,
        now=clock[0],
    )
    live.tracker, live.grounding_evidence = grounding.bootstrap_collection_tracker(
        ref, protocol["geometry"]
    )
    live.registered_tracker = grounding.bootstrap_registered_collection_tracker_v2(
        ref,
        reg,
        source_root=ROOT,
        source_hashes=protocol["source_hashes"],
        nominal_policy=protocol["region_policy"],
    )
    identity = raw.RawEpisodeIdentityV3(
        "software-attempt",
        "software-assignment",
        "a" * 64,
        ref.episode_id,
        "SOFTWARE_ONLY",
        live.original.identity,
        "a" * 64,
        "a" * 64,
        "a" * 64,
        live.original.role_bundle_hash,
        None,
        protocol["source_hashes"],
        "software-clock",
    )
    recorder.bind_source(identity, live.original)
    recorder._write_original("original-plan.json", live.original.to_payload())
    recorder._write_original(
        "registered-tracker-bootstrap.json",
        dict(
            schema_version="native.registered.tracker-bootstrap.v2",
            acquisition=reference_source,
            registration_lease_source=lease.to_payload(),
            compiler_reference_acquisition=compiler_reference_source,
            started_at=clock[0].isoformat(),
            finished_at=clock[0].isoformat(),
            source_generation=protocol["source_generation"],
        ),
    )
    live.session = native_horizon._issue_collection_session(app)
    from cloud_edge_robot_arm.vision.execution import research_safety_shield

    shield = research_safety_shield(protocol["settings"]["task_timeout_s"])
    recorder.record_shield_config(shield)

    def check(index, phase, contract, step, obs):
        ctx = shield.context_builder.build(
            contract=contract,
            step=step,
            robot_state=current_state[0],
            scene_version=contract.scene_version,
            resolved_parameters=dict(step.parameters),
            scene_updated_at=obs.captured_at,
            telemetry_timestamp=clock[0],
            wall_clock_now=clock[0],
            step_started_at_mono=backend.get_sim_time() - 0.025,
            task_started_at_mono=0.0,
            monotonic_now=backend.get_sim_time(),
            requested_velocity=float(step.parameters.get("tcp_velocity", 0.0)),
            requested_acceleration=float(step.parameters.get("acceleration", 0.0)),
            requested_joint_velocities=[0.0] * 7,
        )
        if index == 0 and shield_fault == phase:
            ctx = ctx.model_copy(update={"robot_estop_engaged": True})
        result, source = recorder.check_shield(shield, ctx, index=index, phase=phase)
        assert result.evaluated_rules
        return result, source

    def advance(index, *, do_post=True, do_dispatch=True):
        if index >= 4:
            selected[0] = destination
            if index == 4:
                backend._total_physics_steps += 120
            backend._data.time = backend.total_physics_steps / 240
        obs = capture_fresh()
        contract, step, binding, _, _ = api._collect_grounded_step(
            live, index, obs, protocol, consume_capture=app._consume_capture
        )
        pre, pre_source = check(index, "PRE", contract, step, obs)
        app._evaluate_collection_admission(
            phase="PRE",
            step=step,
            conditions=live.original.requirements[step.step_id].preconditions,
            observation=obs,
            shield=pre,
            binding=binding,
            shield_source=pre_source,
        )
        if not do_dispatch:
            return contract, step, binding, obs, None
        receipt = live.session.execute(index=index, contract=contract, step=step, binding=binding)
        if do_post:
            post = recorder.last_captured_frame.observation
            post_result, post_source = check(index, "POST", contract, step, post)
            app._evaluate_collection_admission(
                phase="POST",
                step=step,
                conditions=worker_owner.registered_collection_effect_conditions_v2(
                    live.original, binding
                ),
                observation=post,
                shield=post_result,
                binding=binding,
                receipt=receipt,
                shield_source=post_source,
            )
            app._complete_collection_step(index=index, step=step, receipt=receipt)
        return contract, step, binding, obs, receipt

    def close():
        stack.close()
        live.owner.close()
        live.closed = True

    return api, app, live, advance, calls, current_state, close


@pytest.mark.parametrize("destination_index", [4, 5])
def test_r643_destination_real_admission_dispatch_once(tmp_path, monkeypatch, destination_index):
    _, app, live, advance, calls, _, close = ordered_v8_context(tmp_path, monkeypatch)
    try:
        for index in range(destination_index + 1):
            contract, step, binding, _, _ = advance(index)
        assert calls.count(step.skill.value) == 1
        assert live.next_index == destination_index + 1
        with pytest.raises(RuntimeError):
            live.session.execute(
                index=destination_index, contract=contract, step=step, binding=binding
            )
        assert calls.count(step.skill.value) == 1
    finally:
        close()


def test_r643_release_default_row(tmp_path, monkeypatch):
    _, app, live, advance, calls, _, close = ordered_v8_context(tmp_path, monkeypatch)
    try:
        for index in range(6):
            advance(index)
        contract, step, binding, _, _ = advance(6, do_post=False)
        row = live.recorder.decisions[-1]
        assert row["decision"]["whitelist_rows"] == ("PRE_RELEASE_REGISTERED_NOMINAL_V1",)
        verdict = next(
            v
            for v in row["inputs"]["verdicts"]
            if v["condition_name"] == "object_inside_target_region"
        )
        assert verdict["status"] == "UNKNOWN" and verdict["reasons"] == [
            "registered_nominal_inside_only"
        ]
        assert calls.count("RELEASE") == 1 and len(live.backend.command_records) == 0
        with pytest.raises(RuntimeError):
            live.session.execute(index=6, contract=contract, step=step, binding=binding)
        assert calls.count("RELEASE") == 1
    finally:
        close()


@pytest.mark.parametrize(
    "explicit,last", [("PRE", 4), ("POST", 4), ("LIFT_POST", 3), ("RELEASE_PRE", 6)]
)
def test_r643_explicit_assertions_never_waived(tmp_path, monkeypatch, explicit, last):
    _, app, live, advance, calls, _, close = ordered_v8_context(
        tmp_path, monkeypatch, explicit=explicit
    )
    try:
        for index in range(last):
            advance(index)
        with pytest.raises(RuntimeError, match="condition_not_admitted"):
            advance(last, do_post=explicit not in {"PRE", "RELEASE_PRE"})
        assert live.next_index == last
        if explicit in {"PRE", "RELEASE_PRE"}:
            assert len(calls) == last
        assert not live.recorder.decisions[-1]["decision"]["allowed"]
        wanted = (
            "object_lifted"
            if explicit == "LIFT_POST"
            else "object_inside_target_region"
            if explicit == "RELEASE_PRE"
            else "target_visible"
        )
        assert (
            "condition_not_admitted:" + wanted in live.recorder.decisions[-1]["decision"]["reasons"]
        )
    finally:
        close()


@pytest.mark.parametrize("phase", ["PRE", "POST"])
def test_r649_real_shield_rejection_blocks_progress(tmp_path, monkeypatch, phase):
    _, app, live, advance, calls, _, close = ordered_v8_context(
        tmp_path, monkeypatch, shield_fault=phase
    )
    try:
        with pytest.raises(RuntimeError, match="shield_gate"):
            advance(0)
        assert len(calls) == (phase == "POST") and live.next_index == 0
    finally:
        close()


@pytest.mark.parametrize("mutation", ["feedback", "UTC_expiry", "OC1_expiry", "cancel", "retry"])
def test_r643_late_dispatch_mutations(tmp_path, monkeypatch, mutation):
    import time
    from datetime import timedelta

    _, app, live, advance, calls, state, close = ordered_v8_context(tmp_path, monkeypatch)
    try:
        contract, step, binding, obs, _ = advance(0, do_dispatch=False)
        if mutation == "feedback":
            state[0] = state[0].model_copy(update={"gripper_open": False})
        elif mutation == "cancel":
            live.repository.request_cancel(live.job_id)
        elif mutation in {"UTC_expiry", "OC1_expiry"}:
            allocate = live.recorder._new_interval

            def delayed(*args):
                value = allocate(*args)
                if args[1] == "EXECUTOR_ATTEMPT":
                    if mutation == "UTC_expiry":
                        # Fixture clock captured by the provider clock class.
                        clock = app.__class__._evaluate_collection_admission.__globals__["datetime"]

                        class Expired(clock):
                            @classmethod
                            def now(cls, tz=None):
                                return obs.captured_at + timedelta(seconds=5)

                        from cloud_edge_robot_arm.research import (
                            native_collection_application as api,
                        )
                        from cloud_edge_robot_arm.research import (
                            native_collection_grounding as grounding,
                        )

                        monkeypatch.setattr(api, "datetime", Expired)
                        monkeypatch.setattr(grounding, "datetime", Expired)
                    else:
                        time.sleep(5.02)
                return value

            monkeypatch.setattr(live.recorder, "_new_interval", delayed)
        if mutation == "retry":
            live.session.execute(index=0, contract=contract, step=step, binding=binding)
            assert len(calls) == 1
        with pytest.raises((ValueError, RuntimeError)):
            live.session.execute(index=0, contract=contract, step=step, binding=binding)
        assert len(calls) == (mutation == "retry")
        assert live.pending is live.registered_dispatch is None
    finally:
        close()


def test_r643_unrelated_unknown_never_rewritten(tmp_path, monkeypatch):
    from cloud_edge_robot_arm.edge.evidence import conditions as predicates

    _, app, live, advance, calls, _, close = ordered_v8_context(tmp_path, monkeypatch)
    try:
        for index in range(6):
            advance(index)
        evaluate = predicates.evaluate_registered_conditions_v2

        def unrelated(*args, **kwargs):
            values = evaluate(*args, **kwargs)
            return [
                replace(v, reasons=("sensor_temporarily_unavailable",))
                if v.condition_name == "object_inside_target_region"
                else v
                for v in values
            ]

        monkeypatch.setattr(predicates, "evaluate_registered_conditions_v2", unrelated)
        with pytest.raises(RuntimeError, match="condition_not_admitted"):
            advance(6, do_post=False, do_dispatch=False)
        assert calls.count("RELEASE") == 0
    finally:
        close()


def test_r643_v8_cli_is_prepare_only(tmp_path, monkeypatch, capsys):
    import json
    import sys

    from scripts.collect_native_calibration import main

    from cloud_edge_robot_arm.research.native_calibration_collection import read_protocol

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "collect",
            "--prepare-registered-occlusion-collection-protocol",
            "--output",
            str(tmp_path / "protocol"),
        ],
    )
    main()
    result = json.loads(capsys.readouterr().out)
    assert result["execution_admitted"] is False
    assert (
        read_protocol(tmp_path / "protocol")["schema_version"]
        == "native.calibration.operational.v8"
    )


def test_r660_fixture_shield_matches_production_protocol(tmp_path, monkeypatch):
    import json

    from cloud_edge_robot_arm.research.native_full_horizon_originals import _shield_recipe
    from cloud_edge_robot_arm.vision.execution import research_safety_shield

    _, app, live, _, _, _, close = ordered_v8_context(tmp_path, monkeypatch)
    try:
        expected = research_safety_shield(app.protocol["settings"]["task_timeout_s"])
        recorded = json.loads((live.recorder.directory / "shield/config.json").read_text())
        assert {k: v for k, v in recorded.items() if k != "policy_hash"} == _shield_recipe(
            expected, app.protocol["source_generation"]
        )
        assert recorded["policy_hash"] == expected.config.policy_hash
        actions = app.protocol["actions"]
        assert len(live.original.contract.steps) == len(actions)
        assert [(s.skill.value, s.timeout_ms) for s in live.original.contract.steps] == [
            (row["skill"], row["original_timeout_ms"]) for row in actions
        ]
    finally:
        close()


def test_r661_feedback_requires_complete_current_envelope(tmp_path, monkeypatch):
    import json

    _, _, live, _, _, _, close = ordered_v8_context(tmp_path, monkeypatch)
    recorder = live.recorder
    original = recorder._captured_feedback_json
    mutations = [
        ("schema_version", "foreign"),
        ("scope", "foreign"),
        ("observation_id", "foreign"),
        ("checksum_sha256", "f" * 64),
        ("physics_step", 99999),
        ("physics_step", True),
        ("observed_at", "2026-11-12T00:00:00"),
        ("extra", "foreign"),
        ("missing", None),
        ("acquisition_id", "foreign"),
        ("path", "foreign"),
        ("sha256", "f" * 64),
    ]
    try:
        for field, value in mutations:
            payload = json.loads(original)
            if field == "missing":
                del payload["scope"]
            elif field in {"acquisition_id", "path", "sha256"}:
                payload["acquisition"][field] = value
            else:
                payload[field] = value
            recorder._captured_feedback_json = json.dumps(payload)
            with pytest.raises((ValueError, TypeError, RuntimeError)):
                recorder.captured_feedback()
            assert not live.completed and live.pending is None
        recorder._captured_feedback_json = original
        a = recorder.captured_feedback()
        a["scope"] = "caller mutation"
        assert recorder.captured_feedback()["scope"] == "RECORDED_GRIPPER_TCP_READ_ONLY"
    finally:
        recorder._captured_feedback_json = original
        close()


@pytest.mark.parametrize(
    "field",
    [
        "horizon_json",
        "step_id",
        "skill",
        "original_plan_sha256",
        "executed_step_sha256",
        "schema_version",
        "native_authority",
        "terminal_acquisition_id",
        "dispatch_step",
        "controller_return_step",
        "terminal_step",
        "failure_type",
    ],
)
def test_r661_foreign_receipt_cannot_allow_post(tmp_path, monkeypatch, field):
    from cloud_edge_robot_arm.simulation.mujoco import native_horizon

    _, _, live, advance, calls, _, close = ordered_v8_context(tmp_path, monkeypatch)
    original_horizon = native_horizon._run_registered_horizon

    def foreign(**kwargs):
        receipt = original_horizon(**kwargs)
        value = 999999 if field.endswith("_step") else "foreign"
        if field == "horizon_json":
            value = '{"foreign":true}'
        return replace(receipt, **{field: value})

    monkeypatch.setattr(native_horizon, "_run_registered_horizon", foreign)
    try:
        with pytest.raises((RuntimeError, ValueError, TypeError)):
            advance(0)
        assert calls == ["MOVE_ABOVE"]
        assert not live.completed and live.next_index == 0
        assert not any(
            row["inputs"]["phase"] == "POST" and row["decision"]["allowed"]
            for row in live.recorder.decisions
        )
        assert live.pending is None
    finally:
        close()


def test_r661_failed_capture_invalidates_feedback(tmp_path, monkeypatch):
    _, _, live, _, calls, _, close = ordered_v8_context(tmp_path, monkeypatch)
    try:
        live.recorder.captured_feedback()

        def fail(*args, **kwargs):
            raise RuntimeError("expected failed current capture")

        monkeypatch.setattr(live.backend._camera, "capture_with_instances", fail)
        with pytest.raises(RuntimeError, match="expected failed current capture"):
            live.recorder.capture()
        with pytest.raises(RuntimeError, match="feedback unavailable"):
            live.recorder.captured_feedback()
        assert not calls and not live.completed and live.pending is None
    finally:
        close()


def test_r661_advancing_clock_trace_is_enclosed(tmp_path, monkeypatch):
    from datetime import datetime

    from cloud_edge_robot_arm.research.native_calibration_collection import (
        prepare_registered_collection_protocol_v2,
    )
    from cloud_edge_robot_arm.research.native_full_horizon_originals import (
        verify_registered_occlusion_trace_v2,
    )

    _, _, live, advance, _, _, close = ordered_v8_context(
        tmp_path / "run", monkeypatch, advancing_clock=True
    )
    try:
        advance(0)
        for row in live.recorder.decisions:
            item = row["inputs"]
            clock = item["tracker_clock"]
            assert datetime.fromisoformat(clock["started_at"]) < datetime.fromisoformat(
                clock["finished_at"]
            )
            assert datetime.fromisoformat(clock["finished_at"]) <= datetime.fromisoformat(
                clock["consumption_after"]["live_owner"]["lease"]["observed_at"]
            )
        live.recorder.freeze()
        root = live.recorder.directory.parent
    finally:
        close()
    protocol = tmp_path / "protocol"
    prepare_registered_collection_protocol_v2(output=protocol)
    result = verify_registered_occlusion_trace_v2(protocol, root=root)
    assert result["completed_software_prefix"] == 1
    assert result["full_group_complete"] is False and result["execution_admitted"] is False


def test_r668_late_source_work_cannot_outlive_oc1(tmp_path, monkeypatch):
    import time

    api, _, live, advance, calls, _, close = ordered_v8_context(tmp_path, monkeypatch)
    try:
        contract, step, binding, _, _ = advance(0, do_dispatch=False)
        original = api._check_protocol_sources
        reads = [0]

        def delayed(protocol):
            original(protocol)
            reads[0] += 1
            if reads[0] == 3:
                time.sleep(5.02)

        monkeypatch.setattr(api, "_check_protocol_sources", delayed)
        with pytest.raises(RuntimeError):
            live.session.execute(index=0, contract=contract, step=step, binding=binding)
        assert reads[0] >= 3
        assert not calls and not live.completed
        assert 0 in live.registered_attempted_indices
        assert live.pending is live.registered_dispatch is None
        with pytest.raises(RuntimeError):
            live.session.execute(index=0, contract=contract, step=step, binding=binding)
        assert not calls
    finally:
        close()


def test_r668_failed_controller_envelope_cannot_complete(tmp_path, monkeypatch):
    import json

    from cloud_edge_robot_arm.simulation.mujoco import native_horizon

    _, _, live, advance, calls, _, close = ordered_v8_context(tmp_path, monkeypatch)
    original = native_horizon._run_registered_horizon

    def contradictory(**kwargs):
        receipt = original(**kwargs)
        result = json.loads(receipt.controller_result_json)
        result["success"] = False
        serialized = json.dumps(result)
        live.recorder.horizons[-1]["controller_result_json"] = serialized
        return replace(receipt, controller_result_json=serialized)

    monkeypatch.setattr(native_horizon, "_run_registered_horizon", contradictory)
    try:
        with pytest.raises((ValueError, RuntimeError)):
            advance(0)
        assert calls == ["MOVE_ABOVE"] and not live.completed
        assert not any(
            r["inputs"]["phase"] == "POST" and r["decision"]["allowed"]
            for r in live.recorder.decisions
        )
    finally:
        close()
