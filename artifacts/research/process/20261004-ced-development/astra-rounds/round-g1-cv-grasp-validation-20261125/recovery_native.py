"""Acquire isolated recovery-qualification evidence with the frozen 130 mm worker."""

# The code below pins the original source tree before importing any worker module.
# ruff: noqa: E402
from __future__ import annotations

import argparse
import shutil
import sys
import time
import traceback
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from recovery_boundary import Acquisition, Boundary, Refused, check_stationary, still_sample

WORK = Path(__file__).resolve().parents[6]
ROUND = Path(__file__).resolve().parent
OLD = WORK / "experiments/results/g1-visibility-pose-repair-20261124"
GEN = "5c09e38b82e09a8c52de407bee97775aca8b8a48b4d14a3bfc387ffd626fa212"
FROZEN = OLD / "builds" / GEN / "runtime-source"
PLAN = "596158c29f9d43573a92c2be22a5b9db55e5d8b21f08cc8382e65e3d8b7ffb1a"
RAW = WORK / "experiments/results/g1-cv-grasp-validation-20261125/recovery-qualification"
sys.path[:0] = [str(FROZEN), str(FROZEN / "src")]

import mujoco
import numpy as np
from scripts.graduation import dynamic_vision as native
from scripts.graduation import g1_dual_probe as probe
from scripts.graduation import g1_dual_trials as dual
from scripts.graduation import g1_visibility_trials as trials
from scripts.graduation import guarded_clock
from scripts.graduation.g1_formal_runtime import bind_scene
from scripts.graduation.g1_formal_trials import identities
from scripts.graduation.g1_visibility_runtime import log_measurements
from scripts.graduation.perception_io import pinned, sha, write

from cloud_edge_robot_arm.simulation.mujoco.skill_robot import _DOWNWARD
from cloud_edge_robot_arm.simulation.mujoco.visual_servo import (
    MuJoCoVisualServoController,
    VisualServoConfig,
)


@contextmanager
def optical_fault(backend, kind):
    """Stimulus copied only into the rendering scene; every physical step is outside this scope."""
    model, data = backend._model, backend._data
    positions = model.geom_pos.copy() if kind == "disagree" else None
    try:
        if kind == "disagree":
            prefix = probe.asset.MARKER_PREFIXES[8]
            for name in ("quiet", *(f"r{r}c{c}" for r in range(6) for c in range(6))):
                model.geom_pos[model.geom(prefix + name).id, 1] += 0.025
            mujoco.mj_forward(model, data)
        with probe.render_intervention(model, kind):
            yield
    finally:
        if positions is not None:
            model.geom_pos[:] = positions
            mujoco.mj_forward(model, data)


def measured_state(backend):
    joint = backend.get_joint_state()
    pose = backend.get_tcp_pose()
    q = np.empty(4)
    site = backend._model.site("tcp").id
    mujoco.mju_mat2Quat(q, backend._data.site_xmat[site])
    return still_sample(
        backend.total_physics_steps, joint.sim_time_s, joint.velocities, [pose.x, pose.y, pose.z], q
    )


def measured_robot(backend, frame):
    current = measured_state(backend)
    fingers = [
        float(backend._data.qpos[int(backend._model.joint(j).qposadr[0])])
        for j in ("finger_left_joint", "finger_right_joint")
    ]
    return dict(
        frame_id=frame.frame_id,
        checksum_sha256=frame.checksum_sha256,
        sim_time_s=current.sim_time_s,
        tcp_position_m=list(current.tcp),
        tcp_quaternion_wxyz=list(current.quaternion),
        joint_positions_rad=list(backend.get_joint_state().positions),
        finger_positions_m=fingers,
    )


class Rig:
    def __init__(self, directory):
        self.directory = directory
        self.events = []
        self.physics = []
        self.controls = []
        self.sources = {}
        self.measurements = {}
        self.robot_frames = {}
        self.native_prefixes = []
        self.operations = []
        template_name = OLD / "batches/train-radial30-contact-d02-02/d02/allocation.json"
        plan = pinned(ROUND / "plan.json", PLAN)
        template = pinned(
            template_name, plan["inputs_sha256"][str(template_name.relative_to(WORK))]
        )
        full = template["sources_sha256"]
        assert native.digest(full) == template["component_catalog_sha256"]
        for name, expected in full.items():
            assert sha(FROZEN / name) == expected, name
        qual = trials.qualified_preflight_pose(WORK)
        self.pose = qual["pose_xyzyaw"]
        self.scene = "g1-cv-recovery-qualification-20261125/" + directory.name
        self.allocation = dict(
            baseline=plan["baseline"],
            runtime_build_sha256=GEN,
            component_catalog_sha256=native.digest(full),
            intent_descriptor={
                "type": "isolated stationary sensor qualification",
                "stages": trials.STAGES,
            },
            case={
                **identities(self.scene),
                "visual_id": self.scene,
                "visual_seed": qual["seed"],
                "visual_stages_in_order": trials.STAGES,
                "release": "g1-cv-recovery-qualification-20261125",
            },
            geometry=template["geometry"],
            qualification_pose=qual,
            plan_sha256=PLAN,
            parent_allocation_sha256=sha(template_name),
        )
        write(directory / "allocation.json", self.allocation)
        self.ep = guarded_clock.GuardedClockEpisode(
            directory, self.allocation, sha(directory / "allocation.json"), full
        )
        self.backend = self.ep.backend
        self.ep.action = self.ep.report["actions"][0]
        self.controller = MuJoCoVisualServoController(self.backend)

    def initialize(self):
        cfg = probe.config({"geometry": self.ep.geometry}, self.allocation["case"]["visual_seed"])
        self.backend.initialize(cfg)
        x, y, z, yaw = self.pose
        scenario = native.PhysicalScenarioConfig(
            scenario_id=self.scene,
            seed=cfg.seed,
            object_pose=native.Pose(x=x, y=y, z=z),
            object_yaw_rad=yaw,
        )
        scenario = dual.bind_scenario_mass(
            scenario, probe.asset.BODY_MASS_KG, dual.mass_properties(self.backend._model)["mass_kg"]
        )
        self.backend.reset(scenario)
        self.ep.capture("reset")
        self.audit_state()
        # The unmodified registration handoff requires absolute step 120.
        with (
            self.backend.observe_physics_steps(self.guard_step),
            self.backend.sensor_capture_on_demand(),
        ):
            self.backend.step(120)
        self.ep.bootstrap()
        self.fixed = self.ep.original.contract
        self.step = self.fixed.steps[0]
        self.key = self.identity()
        self.anchor = self.ep.report["bootstrap"]["resolver_candidate_m"]
        self.scope_origin = self.backend.total_physics_steps

    def identity(self):
        ep = self.ep
        src = ep.active()
        assert self.allocation["runtime_build_sha256"] == GEN
        if (
            ep.action_clock is not None
            or ep.pending_dispatch is not None
            or ep.action.get("dispatched")
        ):
            raise Refused("registered action already issued; cannot replace its source")
        now = datetime.now(UTC)
        if now >= ep.original.effective_deadline_at:
            raise Refused("native original task deadline exceeded")
        return (
            GEN,
            src.job_id,
            src.lease_id,
            src.attempt,
            ep.case["task_id"],
            ep.case["plan_id"],
            self.fixed.command_seq,
            self.step.skill.value,
            ep.original.identity.episode_id,
        )

    def audit_state(self):
        s = measured_state(self.backend)
        self.physics.append({**asdict(s), "owner_lease_id": self.ep.owner.lease.lease_id})
        return s

    def guard_step(self, snapshot):
        self.ep.active()
        assert snapshot.physics_step < 16000
        self.audit_state()

    def operation(self, boundary):
        row = dict(
            number=boundary.operation_id,
            kind=boundary.kind,
            phase=boundary.phase,
            step=boundary.physics_step,
            sim_time_s=boundary.sim_time_s,
            monotonic=time.monotonic(),
            error=boundary.error,
        )
        if boundary.kind == "CAPTURE" and boundary.phase == "END" and boundary.error is None:
            sensor = boundary.result["sensor_frame"]
            row["frame_id"] = sensor["frame_id"]
            row["captured_at"] = native.plain(sensor["captured_at"])
        self.operations.append(row)

    def acquire(self, name, stimulus="both"):
        start = time.monotonic()
        with optical_fault(self.backend, stimulus):
            sensor = self.backend.capture_sensor_frame()
        frame = native.observation_from_sensor_frame(
            sensor, source="mujoco_camera", png_compress_level=1
        )
        event = Acquisition(
            len(self.events) + 1, start, time.monotonic(), self.backend.total_physics_steps, frame
        )
        self.sources[event.number] = frame
        self.robot_frames[frame.frame_id] = measured_robot(self.backend, frame)
        self.events.append(
            {
                "number": event.number,
                "label": name,
                "stimulus": stimulus,
                "step": event.step,
                "started": start,
                "finished": event.finished,
                "frame_id": frame.frame_id,
                "checksum_sha256": frame.checksum_sha256,
                "captured_at": frame.captured_at.isoformat(),
                "sim_time_s": frame.sim_time_s,
                "calibration": frame.calibration_version,
            }
        )
        return event

    def stages(self, event, selected_table=None):
        """Read-only check of the original owner, registered target, native IK and SafetyShield."""
        ep = self.ep
        frame = event.frame
        started = time.monotonic()
        kwargs = dict(
            index=0,
            observation=frame,
            state=ep.robot.get_state(),
            tracker=ep.registered,
            lease_source=ep.active(),
            evidence_sink=ep.audit.append,
        )
        if selected_table is None:
            contract, stage, binding, *_ = native.registered_collection_step_v2(
                ep.original, **kwargs
            )
        else:
            from binding import BoundAttempt

            row = selected_table["selected"]
            if row["full_physical_clearance"] != "CLEAR":
                raise Refused("selected row lacks full physical clearance")
            table = {
                "frame_id": frame.frame_id,
                "checksum_sha256": frame.checksum_sha256,
                "rows": [row],
            }
            active = BoundAttempt.select(
                ep.original,
                ep.active(),
                frame,
                table,
                row["candidate_id"],
                ledger=self.directory / "selected-attempt.sqlite",
            )
            contract, stage, binding, *_ = active.issue_step(ep.original, table=table, **kwargs)
            active.verify_issue(binding)
        target = stage.parameters["target_pose"]
        t0 = time.perf_counter()
        ik = self.controller.kinematics._inverse_kinematics(
            np.array([target[k] for k in "xyz"]),
            np.array(_DOWNWARD),
            self.backend._model.site("tcp").id,
        )
        t1 = time.perf_counter()
        # Check the real original PRE conditions and GuardedClockEpisode's bound Shield.
        # No recorder dispatch occurs in these independent read-only probes.
        ep.current = (self.backend.total_physics_steps, frame)
        before = len(ep.audit)
        try:
            ep.admission(frame, "PRE", contract, stage, binding, self.started, None)
            checks = ep.action["pre"]
            ep.active()
        finally:
            ep.action_clock = None
            ep.pending_binding = None
            ep.pending_dispatch = None
        if ik is None:
            raise Refused("native IK unreachable")
        elapsed = time.monotonic() - started
        out = dict(
            frame_id=frame.frame_id,
            checksum_sha256=frame.checksum_sha256,
            native_target=target,
            native_binding=binding.digest(),
            valid_until=binding.valid_until.isoformat(),
            issued_sequence=contract.command_seq,
            original_task_deadline=ep.original.effective_deadline_at.isoformat(),
            native_ik_joint_positions_rad=ik.tolist(),
            ik_ms=1000 * (t1 - t0),
            fresh_capture_to_ik_ms=1000 * (t1 - event.started),
            capture_to_final_pre_recheck_ms=1000 * (time.monotonic() - event.started),
            whole_readback_ms=1000 * elapsed,
            original_attempt_begin=ep.owner.begin,
            original_action_begin=self.started,
            conditions=native.plain(checks),
            audit_count=len(ep.audit) - before,
        )
        self.native_prefixes.append(out)
        return out

    def begin_case(self, name):
        self.started = time.monotonic()
        self.granted_end = self.started + self.step.timeout_ms / 1000
        self.case_row = dict(
            case=name,
            entered_monotonic=self.started,
            original_action_timeout_ms=self.step.timeout_ms,
            original_action_deadline=self.granted_end,
            physics_origin=self.backend.total_physics_steps,
            command_origin=len(self.backend.command_records),
            events_before=len(self.events),
            operations_before=len(self.operations),
            owner=native.plain(self.ep.owner.current()),
            native_measurements=[],
        )
        self.controls.append(self.case_row)
        self.previous = self.acquire(name + "/reference")
        self.provider = native.OpenCVServoFeedback(
            self.previous.frame,
            self.ep.color,
            self.ep.evidence,
            skill="MOVE_ABOVE",
            initial_target=native.Pose.model_validate(self.anchor),
            marker_family_id=self.ep.registration.marker_family_id,
            verify_mujoco_calibration=True,
        )

    def validate(self, event):
        original = self.sources.get(event.number)
        if event.frame is not original:
            raise Refused("substituted native acquisition receipt")
        native.validate_camera(event.frame, self.ep.geometry)
        self.provider._validate(event.frame)
        if self.backend.total_physics_steps != event.step:
            raise Refused("capture no longer at measured robot state")

    def measure(self, event):
        frame = event.frame
        with log_measurements() as readings:
            try:
                target = self.provider.update(frame)
                error = None
            except ValueError as exc:
                target = None
                error = str(exc)
            record = readings.get(frame.frame_id)
        if record is None:
            raise Refused(error or "no native current-frame measure")
        m = record["measurement"]
        if not (record["callers"].get("servo_measure") and m["checksum"] == frame.checksum_sha256):
            raise Refused("servo observer attribution mismatch")
        if (target is None) == bool(m["usable"]):
            raise Refused("native measurement and servo admission differ")
        self.measurements[frame.frame_id] = record
        self.case_row["native_measurements"].append(
            dict(
                frame_id=frame.frame_id,
                reason=m["reason"],
                observed_ids=m["observed_ids"],
                usable_ids=m["usable_ids"],
                disagreement_m=m["target_disagreement_m"],
                target=native.plain(target),
                servo_error=error,
            )
        )
        return m

    def rest(self):
        states = [measured_state(self.backend)]
        for _ in range(2):
            self.identity()
            if time.monotonic() >= self.granted_end:
                raise Refused("original action deadline exhausted during hold")
            self.backend.step(8)
            states.append(measured_state(self.backend))
        result = check_stationary(states)
        self.case_row["stationarity"] = {"readings": [asdict(x) for x in states], **result}

    def hold(self):
        before = len(self.backend.command_records)
        self.backend.hold_current_joints()
        command = native.plain(self.backend.command_records[before:])
        assert (
            len(command) == 1
            and command[0]["type"] == "hold_current_joints"
            and command[0]["accepted"]
        )
        self.case_row["hold"] = command[0]

    def run_case(self, name, *, full=False):
        self.begin_case(name)
        case = self.case_row
        kind = {
            "missing_then_visible": "no-marker",
            "missing_twice": "no-marker",
            "replayed_failed_frame": "no-marker",
            "foreign": "unknown-id",
            "conflict": "disagree",
            "sample_timeout": "both",
            "full_recovery": "no-marker",
        }.get(name, "both")
        first = self.acquire(name + "/initial", kind)
        case["initial_native_acquisition"] = first.frame.frame_id
        gate_key = self.key if name != "foreign_generation" else ("0" * 64, *self.key[1:])
        gate = Boundary(gate_key, self.granted_end, time.monotonic, self.identity)

        def recapture():
            if name == "replayed_failed_frame":
                return first
            return self.acquire(
                name + "/reobserve", "no-marker" if name == "missing_twice" else "both"
            )

        def admit(event):
            if full:
                from sweep_replay import screen_frame

                table = screen_frame(
                    event.frame,
                    self.ep.geometry,
                    FROZEN / self.ep.geometry["asset_path"],
                    robot_measurement=self.robot_frames[event.frame.frame_id],
                )
                timing = {
                    "from_initial_capture_ms": 1000 * (time.monotonic() - first.started),
                    "from_selected_capture_ms": 1000 * (time.monotonic() - event.started),
                    "native_sample_and_ik_limit_ms": 1000
                    * VisualServoConfig().max_sample_latency_s,
                }
                case["sweep_timing"] = timing
                case["sweep"] = table
                if table["selected"] is None:
                    raise Refused("current sweep has no executable CLEAR")
                self.identity()
                if time.monotonic() >= self.granted_end:
                    raise Refused("original action deadline exhausted during full sweep")
                outcome = self.stages(event, selected_table=table)
                if time.monotonic() - event.started > VisualServoConfig().max_sample_latency_s:
                    raise Refused("whole current capture/screen/IK exceeds original 100 ms")
                return outcome
            if name == "fresh_repeated_native":
                self.provider.update(event.frame)
                raise AssertionError("native servo accepted its already consumed current frame")
            if name == "sample_timeout":

                def delayed(prior):
                    time.sleep(VisualServoConfig().max_sample_latency_s + 0.01)
                    return prior

                target = native.MotionTarget(self.ep.robot.get_state().tcp_pose, _DOWNWARD)
                self.controller.monitor_hold(target, native.VisualServoSession(delayed))
            return self.stages(event)

        why = None
        try:
            if name == "stale":
                time.sleep(VisualServoConfig().max_sample_latency_s + 0.02)
            if name == "expired_original_action":
                time.sleep(max(0, self.granted_end - time.monotonic()) + 0.01)
            if name == "wrong_camera":
                self.backend.set_camera_position((0.40, 0.08, 1.35))
                first = self.acquire(name + "/different-actual-camera")
            gate.read(
                first,
                previous=self.previous,
                validate=self.validate,
                measure=self.measure,
                hold=self.hold,
                stationary=self.rest,
                capture=recapture,
                admit=admit,
            )
        except Exception as exc:
            why = {
                "type": type(exc).__name__,
                "reason": str(exc),
                "origin": traceback.extract_tb(exc.__traceback__)[-1].name,
            }
        if name == "wrong_camera":
            self.backend.set_camera_position((0.35, 0.0, 1.4))
        second_refusal = None
        if name == "missing_then_visible":
            try:
                gate.read(
                    first,
                    previous=self.previous,
                    validate=self.validate,
                    measure=self.measure,
                    hold=self.hold,
                    stationary=self.rest,
                    capture=recapture,
                    admit=admit,
                )
            except Refused as exc:
                second_refusal = str(exc)
        finished = time.monotonic()
        case["acquisition_full_window_ms"] = 1000 * (finished - first.started)
        case["native_captures"] = [
            o["frame_id"]
            for o in self.operations[case["operations_before"] :]
            if o["kind"] == "CAPTURE" and o["phase"] == "END"
        ]
        case.update(
            status=gate.status,
            recaptures_attempted=gate.recapture_count,
            refusal=why,
            second_request_refusal=second_refusal,
            finished_monotonic=finished,
            remaining_original_action_s=self.granted_end - finished,
            elapsed_wall_s=finished - self.started,
            physics_end=self.backend.total_physics_steps,
            commands=native.plain(self.backend.command_records[case["command_origin"] :]),
            acquisitions=len(self.events) - case["events_before"],
            actual_skill_dispatches=0,
        )

    def close(self):
        for number, frame in self.sources.items():
            write(self.directory / f"frame-{number:03}.json", frame.model_dump(mode="json"))
        for idx, (_, _, frame) in enumerate(self.ep.frames):
            write(self.directory / f"bootstrap-{idx:02}.json", frame.model_dump(mode="json"))
        write(self.directory / "telemetry.json", native.plain(self.physics))
        write(self.directory / "operation-boundaries.json", self.operations)
        write(self.directory / "observations.json", native.plain(self.events))
        write(self.directory / "robot-measurements.json", self.robot_frames)
        write(self.directory / "native-pixels.json", self.measurements)
        write(self.directory / "original-audit.json", native.plain(self.ep.audit))
        write(self.directory / "shield-ik.json", self.native_prefixes)
        write(self.directory / "controls.json", self.controls)
        write(self.directory / "commands.json", native.plain(self.backend.command_records))
        if self.ep.owner.repo.get_job(self.ep.owner.job.job_id).status.value == "RUNNING":
            self.ep.owner.close(False)
        self.backend.shutdown()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("components", "full"))
    parser.add_argument("label")
    parser.add_argument("--screen-directory", type=Path, default=RAW / "sweep-v1")
    parser.add_argument(
        "--screen-manifest-sha256",
        default="47320a259d520729cbe9b922d50556f49ceffc228bcee86c6a938d8e000a14d0",
    )
    a = parser.parse_args()
    if not a.label.isalnum() or len(a.label) > 24:
        raise ValueError("alphanumeric independent qualification label required")
    RAW.mkdir(parents=True, exist_ok=True)
    directory = RAW / a.label
    directory.mkdir()
    source = directory / "source"
    source.mkdir()
    for name in ("recovery_native.py", "recovery_boundary.py", "test_recovery_boundary.py"):
        shutil.copyfile(ROUND / name, source / name)
    if a.mode == "full":
        manifest = pinned(a.screen_directory / "sources.json", a.screen_manifest_sha256)
        for name, expected in manifest.items():
            if sha(a.screen_directory / name) != expected:
                raise ValueError("changed captured screen source: " + name)
        sys.path.insert(0, str(a.screen_directory.resolve()))
        write(directory / "screen-sources.json", manifest)
    rig = Rig(directory)
    with trials.device(OLD), bind_scene(rig.scene):
        try:
            rig.initialize()
            with (
                rig.backend.observe_operation_boundaries(rig.operation),
                rig.backend.observe_physics_steps(rig.guard_step),
                rig.backend.sensor_capture_on_demand(),
            ):
                # The native current tracker requires advancing simulation time after its
                # step-120 handoff. Its ordinary route consumes one high, unchanged dwell.
                rig.backend.step(8)
                if a.mode == "components":
                    for name in (
                        "normal",
                        "missing_then_visible",
                        "missing_twice",
                        "replayed_failed_frame",
                        "stale",
                        "wrong_camera",
                        "foreign",
                        "conflict",
                        "foreign_generation",
                        "sample_timeout",
                        "expired_original_action",
                    ):
                        rig.run_case(name)
                    rig.backend.emergency_stop()
                    stop_cursor = len(rig.backend.command_records)
                    try:
                        rig.ep.active()
                    except Exception as exc:
                        rig.controls.append(
                            {
                                "case": "latched_estop",
                                "refusal": str(exc),
                                "estop": rig.backend.estop_engaged,
                                "commands_after": native.plain(
                                    rig.backend.command_records[stop_cursor:]
                                ),
                                "physics_step": rig.backend.total_physics_steps,
                            }
                        )
                    src = rig.ep.owner.current()
                    rig.ep.owner.repo.release_lease(src.lease_id)
                    stop_cursor = len(rig.backend.command_records)
                    try:
                        rig.ep.owner.current()
                    except Exception as exc:
                        rig.controls.append(
                            {
                                "case": "released_sqlite_lease",
                                "refusal": str(exc),
                                "lease_id": src.lease_id,
                                "commands_after": native.plain(
                                    rig.backend.command_records[stop_cursor:]
                                ),
                                "physics_step": rig.backend.total_physics_steps,
                            }
                        )
                else:
                    for name in ("full_normal", "full_recovery"):
                        rig.run_case(name, full=True)
                    rig.run_case("fresh_repeated_native")
        except BaseException:
            write(directory / "exception.json", {"traceback": traceback.format_exc()})
            raise
        finally:
            rig.close()
    print(directory)


if __name__ == "__main__":
    main()
