"""Replay recorded-time admission and Shield results with software boundary inputs."""

from dataclasses import replace
from datetime import datetime, timedelta
from types import MethodType, SimpleNamespace

import pytest

from cloud_edge_robot_arm.contracts import ActionResult
from cloud_edge_robot_arm.edge.runtime.skill_executor import StepExecutionResult
from cloud_edge_robot_arm.research import native_calibration_collection as protocols
from cloud_edge_robot_arm.research import native_collection_application as application
from cloud_edge_robot_arm.research import native_collection_grounding as grounding
from cloud_edge_robot_arm.research import native_full_horizon_originals as reader
from cloud_edge_robot_arm.research.native_calibration_collection import (
    ROOT,
    canonical,
    detached,
    digest,
)
from cloud_edge_robot_arm.research.native_full_horizon_recorder import NativeFullHorizonRecorder
from cloud_edge_robot_arm.research.raw_episode_v3 import (
    RawEpisodeIdentityV3,
    _camera_hash,
    _owner_decode,
)
from cloud_edge_robot_arm.simulation.mujoco.native_horizon import FullHorizonExecutionReceipt
from cloud_edge_robot_arm.vision import registered_object_tracking, tracking, worker_owner
from cloud_edge_robot_arm.vision.execution import research_safety_shield
from cloud_edge_robot_arm.vision.owner_registration import VisualOriginalPlan
from tests.test_registered_grounding_preparation import nominal_scene
from tests.test_registered_object_geometry import revised


class SoftwareTraceRecorder:
    """Real grounding/Shield writes with an in-memory software acquisition owner."""

    record_grounding = NativeFullHorizonRecorder.record_grounding
    record_shield_config = NativeFullHorizonRecorder.record_shield_config
    check_shield = NativeFullHorizonRecorder.check_shield

    def __init__(self, directory, source_hashes):
        self.directory = directory
        self.source_hashes = source_hashes
        self.inventory = {}
        self.grounding_sources = {}
        self.shield_config_source = None
        self.frame_sources = {}
        self.intervals = {}
        self.states = {}
        self.operational_events = []
        self.capture_source_roles = {}
        self.consumptions = []
        self.decisions = []
        self.horizons = []
        self.actions = []
        self.joins = []
        self.holds = []

    def _write_original(self, name, value):
        return self.write_bytes(name, canonical(detached(value)))

    def write_bytes(self, name, data):
        import hashlib

        path = self.directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        sha = hashlib.sha256(data).hexdigest()
        self.inventory[name] = dict(bytes=len(data), sha256=sha)
        return sha

    def acquisition_source(self):
        name = self.frame_sources[self.aid]
        return dict(path=name, sha256=self.inventory[name]["sha256"], acquisition_id=self.aid)

    def captured_feedback(self):
        return self.feedback

    def current_capture(self):
        return self.aid, None, self.operational_events[-1]["bracket"]

    def clock_boundary(self, stamp):
        self.tick += 1000
        return [self.tick, self.tick, stamp.isoformat(), self.tick]

    def bracket(self, stamp):
        _, nanos, _, _ = self.clock_boundary(stamp)
        # Raw interval samples use MONOTONIC, while this owner samples BOOTTIME.
        nanos += 10**12
        return dict(domain=self.domain, lower_ns=nanos, upper_ns=nanos)

    def acquire(self, template, step, state, stamp):
        op = len(self.frame_sources) + 1
        aid = f"capture-{op}"
        obs = revised(
            template,
            observation_id=aid,
            frame_id=aid,
            sim_time_s=step / 240,
            captured_at=stamp,
        )
        physical = dict(
            physics_step=step,
            episode_id=obs.episode_id,
            joint_positions_rad=[0.0] * 7,
            joint_velocities_rad_s=[-0.1, *[0.0] * 6],
            tcp_position_m=[state.tcp_pose.x, state.tcp_pose.y, state.tcp_pose.z],
        )
        self.states[step] = physical
        camera = dict(
            sim_time_s=obs.sim_time_s,
            qpos=[0.0] * 9,
            qvel=[0.0] * 9,
            act=[],
            ctrl=[0.0] * 9,
        )
        interval_id = f"operation-{op}"
        self.intervals[interval_id] = dict(
            kind="ACQUISITION",
            interval_id=interval_id,
            start_step=step,
            end_step=step,
            start=self.clock_boundary(stamp),
            end=self.clock_boundary(stamp),
            disposition="COMPLETE",
        )
        name = f"frames/{aid}/metadata.json"
        instances = f"frames/{aid}/instances.i32"
        instance_count = obs.width * obs.height
        instance_hash = self.write_bytes(instances, b"\xff\xff\xff\xff" * instance_count)
        frame = dict(
            record_seq=op,
            acquisition_id=aid,
            interval_id=interval_id,
            observation_payload=obs.model_dump(mode="json"),
            camera_state_payload=camera,
            joined_physics_observation_hash=digest(physical),
            pass_state_hashes=[_camera_hash(camera)] * 3,
            file_hashes={instances: instance_hash},
            input_role="SOURCE",
            source_acquisition_id=None,
            transform_payload=None,
            transform_source_hashes={},
        )
        role = dict(role="REGISTERED_ACTION_BOUNDARY", physics_step=step, operation_id=op)
        self.capture_source_roles[str(op)] = role
        self._write_original(
            name,
            dict(
                frame=frame,
                capture_source=role,
                observation_payload_sha256=digest(frame["observation_payload"]),
                encoded_fields={},
                pass_count=3,
                instance_ids_present=True,
                instance_labels_present=True,
                instances_available=True,
                instance_count=instance_count,
                instance_labels={},
            ),
        )
        self.frame_sources[aid] = name
        self.operational_events.append(dict(acquisition_id=aid, bracket=self.bracket(stamp)))
        self.aid = aid
        self.last_captured_frame = SimpleNamespace(observation=obs)
        self.feedback = dict(
            schema_version="native.registered.capture-feedback.v2",
            acquisition=self.acquisition_source(),
            observation_id=obs.observation_id,
            checksum_sha256=obs.checksum_sha256,
            physics_step=step,
            observed_at=stamp.isoformat(),
            robot_state=state.model_dump(mode="json"),
            scope="RECORDED_GRIPPER_TCP_READ_ONLY",
        )
        self._write_original(f"frames/{aid}/feedback.json", self.feedback)
        return obs

    def record_action(
        self, original, binding, recipe, dispatch, returned, result, identity, interval_clock
    ):
        index = len(self.actions)
        step = binding.grounded_step
        span = f"span-{index + 1}"
        hold = f"hold-{index + 1}"
        terminal = self.feedback["physics_step"]
        executed = step.model_dump(mode="json")
        self.intervals[span] = dict(
            kind="EXECUTOR_ATTEMPT",
            start_step=dispatch,
            end_step=returned,
            start=interval_clock[0],
            end=interval_clock[1],
            disposition="COMPLETE",
        )
        self.intervals[hold] = dict(
            kind="HOLD",
            interval_id=hold,
            start_step=returned,
            end_step=terminal,
        )
        self.holds.append(
            dict(interval_id=hold, action_span_id=span, semantic_kind="FULL_HORIZON_HOLD")
        )
        self.actions.append(
            dict(
                schema_version="native.registered.action-span.v2",
                record_seq=11 + index,
                identity=identity.to_payload(),
                span_id=span,
                original_plan=original.to_payload(),
                step_id=step.step_id,
                attempt=1,
                grounding=binding.to_payload(),
                interval_id=span,
                command_seq_start=1,
                command_seq_end=1,
                returned_result=detached(result.action_result),
                disposition="RETURNED",
                error=None,
                executed_step_payload=executed,
            )
        )
        receipt = FullHorizonExecutionReceipt(
            step.step_id,
            step.skill.value,
            original.digest(),
            digest(executed),
            canonical(recipe).decode(),
            dispatch,
            returned,
            terminal,
            canonical(detached(result)).decode(),
            hold,
            self.aid,
            True,
            (),
        )
        self.horizons.append(detached(receipt))
        pre = self.decisions[-1]["inputs"]
        self.joins.append(
            dict(
                record_seq=19 + index,
                span_id=span,
                acquisition_id=pre["capture"]["acquisition_id"],
                observation_id=pre["tracker_clock"]["observation_id"],
                checksum_sha256=pre["tracker_clock"]["checksum_sha256"],
                relation="BEFORE_SUBMIT",
            )
        )
        return receipt

    def freeze(self, identity, protocol):
        self._write_original("capture-consumptions.json", self.consumptions)
        self._write_original(
            "partial-originals.json",
            dict(
                schema_version="native.registered.full-horizon.originals.v2",
                source_scope="REGISTERED_MODEL_TEACHER_COLLECTION",
                source_hashes=protocol["source_hashes"],
                identity=identity.to_payload(),
                actions=self.actions,
                horizons=self.horizons,
                allocated_actions=[row["span_id"] for row in self.actions],
                joins=self.joins,
                commands=[],
                hold_mappings=self.holds,
                frame_sources=self.frame_sources,
                decisions=self.decisions,
                operational_events=self.operational_events,
                capture_source_roles=self.capture_source_roles,
                total_physics_steps=self.feedback["physics_step"],
            ),
        )
        return self.manifest()

    def manifest(self):
        value = dict(
            schema_version="native.registered.full-horizon.inventory.v2",
            files=self.inventory,
            inventory_sha256=digest(self.inventory),
            file_count=len(self.inventory),
            original_bytes=sum(row["bytes"] for row in self.inventory.values()),
        )
        (self.directory / "inventory.json").write_bytes(canonical(value))


def _completion_facts(facts, observation):
    """Supply known values at the software sensor seam for the explicit final criteria."""
    facts = dict(facts)
    for name in ("object_inside_target_region", "placement_stable"):
        facts[name] = dict(
            source="rgbd_estimate",
            target_id="object",
            identity_confirmed=True,
            value=True,
            observation_id=observation.observation_id,
            observation_sha256=observation.checksum_sha256,
            pixel=[132, 74],
        )
    return facts


def _software_trace(path, protocol, monkeypatch, *, completion=True):
    _, reference, placed, registration, _, _, utc, state = nominal_scene(
        path / "pixels", monkeypatch
    )
    state = state.model_copy(
        update={"gripper_open": True, "holding_object_id": None, "connected": True}
    )
    stamp = utc[0]

    class SoftwareUTC(datetime):
        @classmethod
        def now(cls, tz=None):
            utc[0] += timedelta(microseconds=1)
            return utc[0]

    for module in (application, grounding, registered_object_tracking, tracking, worker_owner):
        monkeypatch.setattr(module, "datetime", SoftwareUTC)

    recorder = SoftwareTraceRecorder(path / "originals", protocol["source_hashes"])
    recorder.tick = 100_000_000_000
    recorder.domain = {"source": "software-clock"}
    origin = recorder.bracket(stamp)
    deadline = dict(origin=origin, deadline_ns=origin["lower_ns"] + 1800 * 10**9)
    assignment = protocol["assignments"][0]
    worker_origin = ["software-job", 100.0, stamp.isoformat()]

    def lease():
        return worker_owner.WorkerLeaseObservation(
            worker_origin[0],
            "software-run",
            "software-worker",
            "software-lease",
            1,
            stamp - timedelta(seconds=1),
            SoftwareUTC.now(),
            stamp + timedelta(seconds=60),
            "a" * 64,
            "b" * 64,
            "c" * 64,
        )

    def active_source():
        return dict(
            lease=lease().to_payload(),
            task_origin=worker_origin,
            current=recorder.bracket(utc[0]),
            original_deadline_ns=deadline["deadline_ns"],
        )

    def consume():
        aid, _, capture = recorder.current_capture()
        owner = active_source()
        value = dict(
            acquisition_id=aid,
            capture=capture,
            consumed=recorder.bracket(utc[0]),
            step=backend.total_physics_steps,
            live_owner=owner,
        )
        recorder.consumptions.append(value)
        return value

    backend = SimpleNamespace(total_physics_steps=120)
    live = SimpleNamespace(
        recorder=recorder,
        backend=backend,
        origin=origin,
        deadline=deadline,
        repository=None,
        robot=SimpleNamespace(get_state=lambda: state),
        next_index=0,
        completed=[],
        executed_steps=[],
        registered_attempted_indices=set(),
        registered_execution=None,
    )
    app = SimpleNamespace(protocol=protocol, _consume_capture=consume)
    for name in (
        "_registered_current_receipt_v2",
        "_nominal_registered_release_v2",
        "_complete_collection_step",
        "_evaluate_registered_admission_v2",
    ):
        setattr(app, name, MethodType(getattr(application.NativeCollectionApplication, name), app))
    monkeypatch.setattr(application, "_live", lambda _: live)
    monkeypatch.setattr(application, "_registered_lease", lambda *_: lease())

    def capture(template):
        return recorder.acquire(template, backend.total_physics_steps, state, SoftwareUTC.now())

    before = capture(reference)
    compiler_ref = recorder.acquisition_source()
    _, evidence = application._record_bootstrap_tracker(
        live,
        before,
        protocol,
        purpose="BOOTSTRAP_B",
        name="tracker-clock/bootstrap.json",
        consume_capture=consume,
    )
    registration_lease = lease()
    # The registration/handoff retain the first snapshot. E sees the renewed epoch.
    registration_lease = replace(
        registration_lease,
        expires_at=registration_lease.observed_at + timedelta(microseconds=6),
    )
    live.original = grounding.build_collection_contract_v2(
        assignment=assignment,
        current_owner=dict(
            issued_at=stamp,
            deadline_at=stamp + timedelta(seconds=60),
            task_id=worker_origin[0],
            plan_id="software-collection",
            lease=registration_lease,
            role_sha256=digest(protocol["role"]),
        ),
        geometry=protocol["geometry"],
        source_hashes=protocol["source_hashes"],
        observation=before,
        protocol_settings=protocol["settings"],
    )
    original = live.original
    recorder._write_original(
        "source-binding.json", dict(origin=origin, deadline=deadline, source=active_source())
    )
    recorder._write_original("original-plan.json", original.to_payload())
    recorder._write_original("bootstrap.json", evidence)
    recorder.capture = lambda: capture(reference)
    obs = application._handoff_registered_capture(
        live, before, registration_lease, protocol, consume_capture=consume
    )
    started = SoftwareUTC.now()
    live.registered_tracker = grounding.bootstrap_registered_collection_tracker_v2(
        obs,
        registration,
        source_root=ROOT,
        source_hashes=protocol["source_hashes"],
        nominal_policy=protocol["region_policy"],
    )
    recorder._write_original(
        "registered-tracker-bootstrap.json",
        dict(
            schema_version="native.registered.tracker-bootstrap.v2",
            acquisition=recorder.acquisition_source(),
            compiler_reference_acquisition=compiler_ref,
            registration_lease_source=registration_lease.to_payload(),
            started_at=started.isoformat(),
            finished_at=SoftwareUTC.now().isoformat(),
            source_generation=protocol["source_generation"],
        ),
    )
    raw_facts = live.tracker.facts

    def facts(observation, robot_state):
        result = raw_facts(observation, robot_state)
        return (
            _completion_facts(result, observation)
            if completion and recorder.aid == "capture-10"
            else result
        )

    monkeypatch.setattr(live.tracker, "facts", facts)
    identity = RawEpisodeIdentityV3(
        "software-attempt",
        assignment["assignment_id"],
        "a" * 64,
        obs.episode_id,
        "SOFTWARE_ONLY",
        original.identity,
        "a" * 64,
        "a" * 64,
        "a" * 64,
        original.role_bundle_hash,
        None,
        protocol["source_hashes"],
        "software-clock",
    )
    shield = research_safety_shield(protocol["settings"]["task_timeout_s"])
    recorder.record_shield_config(shield)
    v10 = protocol["schema_version"] == protocols.REGISTERED_TEACHER_V10_SCHEMA
    for index, action in enumerate(protocol["actions"]):
        dispatch = backend.total_physics_steps
        contract, step, binding, _, _ = application._collect_grounded_step(
            live, index, obs, protocol, consume_capture=consume
        )
        velocity = float(step.parameters.get("tcp_velocity", 0.0))
        step_start = 100.0 + (index + 1) * 10.0
        context = shield.context_builder.build(
            contract=contract,
            step=step,
            robot_state=state,
            scene_version=contract.scene_version,
            scene_updated_at=obs.captured_at,
            telemetry_timestamp=SoftwareUTC.now(),
            wall_clock_now=SoftwareUTC.now(),
            step_started_at_mono=step_start,
            task_started_at_mono=worker_origin[1],
            monotonic_now=step_start,
            physics_step=0 if v10 else dispatch,
            requested_velocity=velocity,
            requested_acceleration=float(step.parameters.get("acceleration", 0.0)),
            requested_joint_velocities=[0.1, *[0.0] * 6, velocity / 0.3],
        )
        result, source = recorder.check_shield(shield, context, index=index, phase="PRE")
        app._evaluate_registered_admission_v2(
            phase="PRE",
            step=step,
            conditions=grounding.registered_expected_conditions_v2(original, binding, "PRE"),
            observation=obs,
            shield=result,
            binding=binding,
            shield_source=source,
        )
        begin = recorder.clock_boundary(SoftwareUTC.now())
        state_at_dispatch = state
        start = SoftwareUTC.now()
        if "target_pose" in step.parameters:
            state = state.model_copy(
                update={
                    "tcp_pose": state.tcp_pose.model_copy(update=step.parameters["target_pose"])
                }
            )
        if step.skill.value == "GRASP":
            state = state.model_copy(update={"gripper_open": False, "holding_object_id": "object"})
        if step.skill.value == "RELEASE":
            state = state.model_copy(update={"gripper_open": True, "holding_object_id": None})
        elapsed = 121 if step.skill.value == "LIFT" else 1
        finished = SoftwareUTC.now()
        action_result = ActionResult(
            action_id=f"software-{index}",
            action_type=step.skill.value,
            success=True,
            started_at=start,
            finished_at=finished,
            duration_ms=0,
            state_before=state_at_dispatch.model_dump(mode="json"),
            state_after=state.model_dump(mode="json"),
            details=dict(
                contact_hold_s=0.5 if step.skill.value == "LIFT" else 0.0,
                physics_steps=elapsed,
                scope="SOFTWARE_ONLY",
            ),
        )
        controller = StepExecutionResult(
            original.contract.task_id,
            step.step_id,
            step.skill.value,
            1,
            True,
            None,
            action_result,
            0,
            SoftwareUTC.now(),
        )
        end = recorder.clock_boundary(SoftwareUTC.now())
        backend.total_physics_steps = dispatch + action["horizon"]["total_steps"]
        obs = capture(placed if index >= 4 else reference)
        receipt = recorder.record_action(
            original,
            binding,
            action["horizon"],
            dispatch,
            dispatch + elapsed,
            controller,
            identity,
            (begin, end),
        )
        live.registered_execution = dict(
            index=index,
            receipt=receipt,
            receipt_json=canonical(detached(receipt)),
            original_sha256=original.digest(),
            binding_sha256=binding.digest(),
            step_sha256=digest(step.model_dump(mode="json")),
            dispatch_step=dispatch,
            terminal_capture=recorder.current_capture(),
        )
        post = context.model_copy(
            update=dict(
                tcp_x=state.tcp_pose.x,
                tcp_y=state.tcp_pose.y,
                tcp_z=state.tcp_pose.z,
                scene_updated_at=obs.captured_at,
                wall_clock_now=SoftwareUTC.now(),
                telemetry_timestamp=SoftwareUTC.now(),
                monotonic_now=step_start + ((8.5 if v10 else 8.0) if index == 0 else 0.25),
                physics_step=backend.total_physics_steps - dispatch
                if v10
                else backend.total_physics_steps,
                joint_velocities=[0.1, *[0.0] * 6],
                holding_object=state.holding_object_id is not None,
            )
        )
        result, source = recorder.check_shield(shield, post, index=index, phase="POST")
        args = dict(
            step=step,
            conditions=grounding.registered_expected_conditions_v2(original, binding, "POST"),
            observation=obs,
            shield=result,
            binding=binding,
            receipt=receipt,
        )
        if index == 7 and not completion:
            with pytest.raises(RuntimeError, match="condition_not_admitted:placement_stable"):
                app._evaluate_registered_admission_v2(phase="POST", shield_source=source, **args)
            break
        app._evaluate_registered_admission_v2(phase="POST", shield_source=source, **args)
        app._complete_collection_step(index=index, step=step, receipt=receipt)
    if completion:
        app._evaluate_registered_admission_v2(
            phase="TERMINAL", shield_source=dict(source, reused_from="POST"), **args
        )
    recorder.freeze(identity, protocol)
    return recorder, deadline, identity


@pytest.fixture(scope="module", params=["v9", "v10"])
def trace(request, tmp_path_factory):
    protocol = {
        "v9": protocols._registered_teacher_protocol,
        "v10": protocols._registered_teacher_v10_protocol,
    }[request.param]()
    root = tmp_path_factory.mktemp("replay-" + request.param)
    with pytest.MonkeyPatch.context() as monkeypatch:
        recorder, deadline, identity = _software_trace(root, protocol, monkeypatch)
    return protocol, root, recorder, deadline, identity


def _prepare_audit(audit, recorder, deadline, identity):
    """Supply the boundary subset that preceding source/physics/geometry stages decode."""
    audit.identity = identity
    audit.original = _owner_decode(VisualOriginalPlan, audit.read("original-plan.json"))
    audit.domain, audit.deadline = recorder.domain, deadline["deadline_ns"]
    audit.intervals, audit.states = recorder.intervals, recorder.states
    audit.sequences = list(range(1, 11))
    for aid in audit.raw["frame_sources"]:
        obs, meta, state = audit.frame(aid)
        audit.frames[aid] = dict(
            step=state["physics_step"],
            observation_id=obs.observation_id,
            checksum_sha256=obs.checksum_sha256,
            role=meta["capture_source"]["role"],
        )


@pytest.fixture
def software_facts(monkeypatch):
    actual_facts = reader._ArchivedTargetTracker.facts_at

    def facts(self, observation, state, *, evaluated_at):
        result = actual_facts(self, observation, state, evaluated_at=evaluated_at)
        return (
            _completion_facts(result, observation)
            if observation.observation_id == "capture-10"
            else result
        )

    monkeypatch.setattr(reader._ArchivedTargetTracker, "facts_at", facts)


def test_complete_registered_admission_replays_actual_shield(trace, software_facts, monkeypatch):
    from cloud_edge_robot_arm.edge.safety.shield import SafetyShield

    protocol, root, recorder, deadline, identity = trace
    registration = root / "registration"
    registration.mkdir()
    protocols.save_exclusive(registration / "protocol.json", protocol)
    audits = []

    def seed_boundary_inputs(audit):
        _prepare_audit(audit, recorder, deadline, identity)
        audit.source_ok = True
        audits.append(audit)

    monkeypatch.setattr(reader._Audit, "source", seed_boundary_inputs)
    for phase in ("physics", "operations", "geometry", "physical_outcome", "metrics", "lifecycle"):
        monkeypatch.setattr(reader._Audit, phase, lambda self: None)
    calls = []
    depth = 0

    def observe(method):
        real = getattr(SafetyShield, method)

        def check(shield, context):
            nonlocal depth
            if not depth:
                calls.append((method, context))
            depth += 1
            try:
                return real(shield, context)
            finally:
                depth -= 1

        monkeypatch.setattr(SafetyShield, method, check)

    observe("pre_check")
    observe("post_check")
    result = reader.read_native_full_horizon_group(
        registration,
        assignment_id=protocol["assignments"][0]["assignment_id"],
        root=root,
    )
    assert result.source_complete, result.reasons
    assert result.horizon_complete and len(result.actions) == 8
    assert not result.execution_admitted and result.group_score is None
    (audit,) = audits
    assert audit.decision_ok and len(audit.tracker_clock_keys) == 27
    timeline = audit.read("registration-timeline.json")
    bootstrap = audit.read("registered-tracker-bootstrap.json")
    old_lease = timeline["lease"]
    new_lease = audit.read("tracker-clock/dispatch.json")["consumption_after"]["live_owner"][
        "lease"
    ]
    assert old_lease == bootstrap["registration_lease_source"]
    for key in ("job_id", "run_id", "worker_id", "lease_id", "attempt", "acquired_at"):
        assert old_lease[key] == new_lease[key]
    assert (
        datetime.fromisoformat(timeline["checked_at"])
        < datetime.fromisoformat(old_lease["expires_at"])
        < datetime.fromisoformat(bootstrap["finished_at"])
        < datetime.fromisoformat(new_lease["expires_at"])
    )
    assert len(calls) == 16 and len(audit.policies) == 8
    assert [method for method, _ in calls] == ["pre_check", "post_check"] * 8
    grasp = calls[5][1]
    release = calls[13][1]
    assert grasp.holding_object and grasp.holding_object_id is None
    assert not release.holding_object and release.holding_object_id == "object"
    assert recorder.decisions[-1]["inputs"]["shield_source"] == dict(
        recorder.decisions[-2]["inputs"]["shield_source"],
        reused_from="POST",
    )
    pre, post = calls[0][1], calls[1][1]
    if protocol["schema_version"] == protocols.REGISTERED_TEACHER_V10_SCHEMA:
        assert (pre.physics_step, post.physics_step) == (0, 1920)
        assert post.monotonic_now - post.step_started_at == 8.5
    else:
        assert (pre.physics_step, post.physics_step) == (120, 2040)
        assert post.monotonic_now - post.step_started_at == 8.0


def _replay(trace, root):
    protocol, _, recorder, deadline, identity = trace
    audit = reader._Audit(protocol, protocol["assignments"][0], root)
    audit.inventory()
    _prepare_audit(audit, recorder, deadline, identity)
    audit.horizons()
    return audit


@pytest.fixture
def resealed_trace(trace, tmp_path):
    import shutil

    _, root, recorded, _, _ = trace
    shutil.copytree(root / "originals", tmp_path / "originals")
    clone = SoftwareTraceRecorder(tmp_path / "originals", recorded.source_hashes)
    clone.inventory = protocols.load_json(clone.directory / "inventory.json")["files"]
    raw_path = "partial-originals.json"
    raw = protocols.load_json(clone.directory / raw_path)

    def reseal():
        for row in raw["decisions"]:
            row["decision"]["original_inputs_sha256"] = digest(row["inputs"])
        clone._write_original(raw_path, raw)
        clone.manifest()
        return _replay(trace, tmp_path)

    return clone, raw, reseal


@pytest.mark.parametrize(
    "field", ["feedback_source", "registered_inputs", "tracker_clock", "evaluation_at", "receipt"]
)
def test_v2_admission_requires_complete_fields(resealed_trace, field):
    _, raw, reseal = resealed_trace
    del raw["decisions"][0]["inputs"][field]
    audit = reseal()
    with pytest.raises(ValueError, match="exact registered v2 envelope"):
        audit.admissions()
    assert not audit.decision_ok


def test_v2_admission_rejects_v1_decision(resealed_trace):
    _, raw, reseal = resealed_trace
    raw["decisions"][0]["decision"]["schema_version"] = "teacher.registered.collection.admission.v1"
    with pytest.raises(ValueError, match="v2 admission version differs"):
        reseal().admissions()


def test_v2_admission_rejects_v1_resealed_feedback(resealed_trace):
    clone, raw, reseal = resealed_trace
    item = raw["decisions"][0]["inputs"]
    item["feedback_source"]["schema_version"] = "native.registered.capture-feedback.v1"
    clone._write_original("frames/capture-2/feedback.json", item["feedback_source"])
    with pytest.raises(ValueError, match="registered v2 source association differs"):
        reseal().admissions()


def test_v2_admission_rejects_wrong_receipt_version(resealed_trace):
    _, raw, reseal = resealed_trace
    raw["decisions"][1]["inputs"]["receipt"]["schema_version"] = "native.full-horizon.execution.v2"
    with pytest.raises(ValueError, match="registered v2 source association differs"):
        reseal().admissions()


@pytest.mark.parametrize("change", ["expired_handoff", "crossed_epoch", "expired_bootstrap"])
def test_v2_bootstrap_rejects_invalid_lease_or_frame(resealed_trace, change):
    clone, _, reseal = resealed_trace
    timeline = protocols.load_json(clone.directory / "registration-timeline.json")
    bootstrap = protocols.load_json(clone.directory / "registered-tracker-bootstrap.json")
    if change == "expired_handoff":
        timeline["lease"]["expires_at"] = timeline["checked_at"]
        bootstrap["registration_lease_source"] = timeline["lease"]
        match = "original registration/capture/lease chronology mismatch"
    elif change == "crossed_epoch":
        clock_ref = timeline["dispatch"]["tracker_clock"]
        payload = protocols.load_json(clone.directory / clock_ref["path"])
        consumptions = protocols.load_json(clone.directory / "capture-consumptions.json")
        at = consumptions.index(payload["consumption_before"])
        payload["consumption_before"]["live_owner"]["lease"]["attempt"] += 1
        consumptions[at] = payload["consumption_before"]
        clone._write_original("capture-consumptions.json", consumptions)
        clock_ref["sha256"] = clone._write_original(clock_ref["path"], payload)
        match = "tracker crossed original lease:attempt"
    else:
        captured = datetime.fromisoformat(timeline["dispatch"]["captured_at"])
        bootstrap["finished_at"] = (captured + timedelta(seconds=5)).isoformat()
        match = "registered bootstrap original time invalid"
    clone._write_original("registration-timeline.json", timeline)
    clone._write_original("registered-tracker-bootstrap.json", bootstrap)
    with pytest.raises(ValueError, match=match):
        reseal().admissions()


@pytest.mark.parametrize("clock_domain", ["raw monotonic", "operational clock"])
def test_v2_receipt_checks_each_clock_domain(trace, clock_domain):
    from copy import deepcopy

    from cloud_edge_robot_arm.contracts import TaskStep

    _, root, *_ = trace
    audit = _replay(trace, root)
    pre, post = (deepcopy(row["inputs"]) for row in audit.raw["decisions"][:2])
    obs, metadata, _ = audit.frame(post["capture"]["acquisition_id"])
    terminal_id = metadata["frame"]["interval_id"]
    terminal = deepcopy(audit.intervals[terminal_id])
    audit.intervals = {**audit.intervals, terminal_id: terminal}
    attempt = audit.intervals[audit.raw["actions"][0]["interval_id"]]
    pre_consumed = pre["tracker_clock"]["consumption_after"]["consumed"]["upper_ns"]
    terminal["start"][1] = attempt["end"][3]
    post["capture"]["capture"]["lower_ns"] = pre_consumed
    args = (post, 0, TaskStep.model_validate(post["step"]), metadata, obs.captured_at)
    audit.admission_receipt_v2(*args)
    if clock_domain == "raw monotonic":
        terminal["start"][1] -= 1
    else:
        post["capture"]["capture"]["lower_ns"] -= 1
    with pytest.raises(ValueError, match=f"v2 receipt {clock_domain} order differs"):
        audit.admission_receipt_v2(*args)


def _reseal_shield(clone, row, *, change_context=None, change_result=None):
    item = row["inputs"]
    sources = item["shield_source"]
    inp, out = (
        protocols.load_json(clone.directory / sources[key]["path"]) for key in ("input", "result")
    )
    if change_context:
        change_context(inp["context"])
    if change_result:
        change_result(out["result"])
        item["shield"] = out["result"]
    sources["input"]["sha256"] = clone._write_original(sources["input"]["path"], inp)
    out["input_sha256"] = sources["input"]["sha256"]
    sources["result"]["sha256"] = clone._write_original(sources["result"]["path"], out)


@pytest.mark.parametrize(
    "change",
    ["missing_count", "bool_count", "wrong_basis", "refreshed_step_clock", "forged_output"],
)
def test_v2_shield_rejects_resealed_context_or_result(resealed_trace, change):
    clone, raw, reseal = resealed_trace
    row = raw["decisions"][1 if change == "refreshed_step_clock" else 0]
    current = protocols.load_json(
        clone.directory / row["inputs"]["shield_source"]["input"]["path"]
    )["context"]
    changes = {
        "missing_count": lambda ctx: ctx.pop("physics_step"),
        "bool_count": lambda ctx: ctx.update(physics_step=True),
        "wrong_basis": lambda ctx: ctx.update(physics_step=120 - current["physics_step"]),
        "refreshed_step_clock": lambda ctx: ctx.update(
            step_started_at=ctx["step_started_at"] + 0.5
        ),
    }
    result = (lambda value: value["evaluated_rules"].pop()) if change == "forged_output" else None
    _reseal_shield(clone, row, change_context=changes.get(change), change_result=result)
    match = "v2 Shield output replay differs" if result else "v2 Shield context differs"
    with pytest.raises(ValueError, match=match):
        reseal().admissions()


def test_step_wall_clock_overrun_uses_registered_basis(trace, resealed_trace, software_facts):
    protocol, *_ = trace
    clone, raw, reseal = resealed_trace
    _reseal_shield(
        clone,
        raw["decisions"][1],
        change_context=lambda ctx: ctx.update(monotonic_now=ctx["monotonic_now"] + 0.001),
    )
    audit = reseal()
    if protocol["schema_version"] == protocols.REGISTERED_TEACHER_SCHEMA:
        with pytest.raises(ValueError, match="v2 Shield output replay differs"):
            audit.admissions()
    else:
        audit.admissions()
        assert audit.decision_ok  # The physical equality boundary is unchanged.


def test_v2_terminal_must_reuse_final_post(resealed_trace, software_facts):
    _, raw, reseal = resealed_trace
    previous = raw["decisions"][13]["inputs"]["shield_source"]
    raw["decisions"][-1]["inputs"]["shield_source"].update(
        input=previous["input"],
        result=previous["result"],
    )
    with pytest.raises(ValueError, match="v2 TERMINAL Shield reuse differs"):
        reseal().admissions()


def test_original_colour_evidence_stops_on_explicit_completion(tmp_path, monkeypatch):
    protocol = protocols._registered_teacher_protocol()
    recorder, deadline, identity = _software_trace(
        tmp_path, protocol, monkeypatch, completion=False
    )
    row = recorder.decisions[-1]
    assert len(recorder.decisions) == 16 and row["inputs"]["phase"] == "POST"
    assert row["decision_kind"] == "STOP"
    assert "condition_not_admitted:placement_stable" in row["decision"]["reasons"]
    assert "placement_stable" in row["decision"]["retained_unknown_conditions"]
    audit = _replay((protocol, tmp_path, recorder, deadline, identity), tmp_path)
    with pytest.raises(ValueError, match="complete v2 admission inventory required"):
        audit.admissions()
