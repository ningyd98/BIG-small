"""One exclusive immutable development attempt through the native eight-stage owner."""

import argparse
import os
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from functools import wraps
from inspect import getsourcelines
from pathlib import Path

import mujoco
import numpy as np
from scripts.graduation import dynamic_vision as native
from scripts.graduation import g1_complete_trials as trials
from scripts.graduation import (
    g1_dual_observer,
    g1_dual_trials,
    g1_visibility_runtime,
    g1_visibility_trials,
    guarded_clock,
)
from scripts.graduation.g1_complete_cv_clearance import LocalClearance, camera_encoder_pose
from scripts.graduation.g1_formal_runtime import bind_scene, check_tree
from scripts.graduation.perception_io import ROOT, pinned, read, sha, write
from scripts.graduation.proposal_translated_cases import TranslatedEpisode

from cloud_edge_robot_arm.simulation.mujoco.skill_robot import _DOWNWARD
from cloud_edge_robot_arm.simulation.mujoco.visual_servo import MuJoCoVisualServoController


def native_reset_ids(events, scene, episode):
    """Read only the reset operation's identity and clock, independently of its pixels."""
    trials.require(len(events) == 2, "missing native reset transaction")
    begin, end = events
    trials.require(
        isinstance(scene, str)
        and scene
        and isinstance(episode, str)
        and episode
        and begin.get("phase") == "BEGIN"
        and end.get("phase") == "END"
        and begin.get("operation_id") == end.get("operation_id")
        and type(begin.get("operation_id")) is int
        and begin.get("parameters") == end.get("parameters")
        and end.get("parameters", {}).get("requested", {}).get("scenario_id") == scene
        and end.get("episode_id") == episode
        and end.get("result", {}).get("physics_dt_s") == 1 / 240
        and all(
            e.get("physics_step") == 0
            and e.get("sim_time_s") == 0
            and e.get("kind") == "RESET"
            and e.get("error") is None
            and e.get("error_type") is None
            for e in events
        ),
        "native reset, scene or episode identity differs",
    )
    return scene, episode


@contextmanager
def observe_sample_failures(events):
    """On native exceptions only, read sampling start and the throw location from traceback."""
    originals = {}

    def wrap(method):
        source, first = getsourcelines(method)
        start = next(
            first + n for n, line in enumerate(source) if "sampled_at = time.perf_counter()" in line
        )
        end = next(first + n for n, line in enumerate(source) if "session.records.append(" in line)

        @wraps(method)
        def invoke(controller, *args, **kwargs):
            try:
                return method(controller, *args, **kwargs)
            except Exception as exc:
                ended = time.perf_counter_ns()
                trace = exc.__traceback__
                while trace is not None:
                    if trace.tb_frame.f_code is method.__code__ and start <= trace.tb_lineno <= end:
                        data = trace.tb_frame.f_locals
                        began = round(data["sampled_at"] * 1e9)
                        # Native measured deadline violations contain the precise original duration.
                        native_duration = (
                            data.get("latency") if "deadline exceeded" in str(exc) else None
                        )
                        events.append(
                            dict(
                                phase="FAILED_FEEDBACK",
                                method=method.__name__,
                                physics_step=controller.backend.total_physics_steps,
                                sim_time_s=controller.backend.get_sim_time(),
                                sample_start_ns=began,
                                exception_seen_ns=ended,
                                elapsed_to_unwind_s=(ended - began) / 1e9,
                                native_sample_and_ik_s=native_duration,
                                exception_type=type(exc).__name__,
                                reason=str(exc),
                            )
                        )
                        break
                    trace = trace.tb_next
                raise

        return invoke

    try:
        for name in ("_move_tcp", "monitor_hold"):
            original = getattr(MuJoCoVisualServoController, name)
            originals[name] = original
            setattr(MuJoCoVisualServoController, name, wrap(original))
        yield
    finally:
        for name, original in originals.items():
            setattr(MuJoCoVisualServoController, name, original)


class ClearanceEpisode(TranslatedEpisode):
    def __init__(
        self,
        directory,
        allocation,
        allocation_sha,
        catalog,
        measured,
        events,
        preflight,
        payload_samples,
    ):
        super().__init__(directory, allocation, allocation_sha, catalog)
        self.backend = g1_dual_trials.RegisteredAssemblyBackend(directory, allocation["case"])
        self.robot = native.MuJoCoSkillRobot(self.backend)
        self.executor = guarded_clock.RecordedExecutor(
            self, native.SkillExecutor(robot=self.robot, registry=native.SkillRegistry.default())
        )
        self.measurements = measured
        self.events = events
        self.asset_path = ROOT / self.geometry["asset_path"]
        self.certificate = None
        self.calibration = Path(allocation["calibration_directory"])
        self.calibration_hash = allocation["calibration_sha256"]
        self.clock_starts = {}
        self.last_handoff = None
        self.entry_command = None
        self.observed_command_count = 0
        self.last_gripper_command = None
        self.payload_samples = payload_samples
        self.preflight = preflight
        self.approach_diagnostic = (
            allocation["case"]["release"].split("-train-")[-1].startswith("approach-probe-")
        )

    def run(self):
        try:
            return super().run()
        finally:
            if self.certificate is not None:
                self.certificate.close()

    def payload_command_context(self):
        commands = self.backend._command_records
        for command in commands[self.observed_command_count :]:
            if command.get("type") == "gripper" and command.get("accepted") is True:
                self.last_gripper_command = command
        self.observed_command_count = len(commands)
        last = self.last_gripper_command or {}
        completed = next(
            (
                r
                for r in reversed(self.report["actions"])
                if r.get("controller_result", {}).get("success") is True
                and type(r.get("controller_return_step")) is int
            ),
            {},
        )
        return dict(
            native_last_command_seq=self.backend.next_command_sequence - 1,
            previous_native_successful_skill=completed.get("skill"),
            previous_native_return_step=completed.get("controller_return_step"),
            previous_native_terminal_step=completed.get("end_step")
            if completed.get("status") == "PASS"
            else None,
            last_accepted_gripper_open=last.get("target_open"),
            last_accepted_gripper_command_step=last.get("physics_step"),
        )

    def robot_observation(self, frame):
        backend = self.backend
        joints = backend.get_joint_state()
        trials.require(
            joints.sim_time_s == frame.sim_time_s == backend.get_sim_time(),
            "current encoder and image simulation clock differ",
        )
        tcp = backend.get_tcp_pose()
        rotation = np.empty(4)
        # The tcp site is a robot encoder forward-kinematic output.
        mujoco.mju_mat2Quat(rotation, backend._data.site("tcp").xmat)
        return dict(
            frame_id=frame.frame_id,
            checksum=frame.checksum_sha256,
            checksum_sha256=frame.checksum_sha256,
            sim_time_s=joints.sim_time_s,
            physics_step=backend.total_physics_steps,
            joint_positions_rad=list(joints.positions),
            joint_velocities_rad_s=list(joints.velocities),
            tcp_position_m=[tcp.x, tcp.y, tcp.z],
            tcp_quaternion_wxyz=rotation.tolist(),
            finger_positions_m=[
                float(backend._data.joint(n).qpos[0])
                for n in ("finger_left_joint", "finger_right_joint")
            ],
            finger_velocities_m_s=[
                float(backend._data.joint(n).qvel[0])
                for n in ("finger_left_joint", "finger_right_joint")
            ],
            **camera_encoder_pose(backend._model, backend._data),
            **self.payload_command_context(),
        )

    def command_handoff(self, skill, phase, robot, frame):
        """Bind a continuous native stage transition to encoders and applied actuator targets."""
        if phase == "STATIC_SELECTION" or skill == g1_visibility_trials.STAGES[0]:
            return None
        index = g1_visibility_trials.STAGES.index(skill)
        prior = self.report["actions"][index - 1]
        backend = self.backend
        step = backend.total_physics_steps
        # Applied drive setpoints, independently of any queued or planned target.
        joint_targets = [float(x) for x in backend._data.ctrl[:7]]
        finger_targets = [float(x) for x in backend._data.ctrl[7:9]]
        seq = backend.next_command_sequence - 1
        if phase == "PRE":
            trials.require(
                prior.get("status") == "PASS" and prior.get("end_step") == step,
                "previous native stage did not return at this physical step",
            )
            self.entry_command = dict(
                source_skill=prior["skill"],
                destination_skill=skill,
                prior_end_step=prior["end_step"],
                entry_step=step,
                entry_command_seq=seq,
                entry_target_rad=joint_targets,
                entry_finger_target_m=finger_targets,
                entry_effective_arm_goal_rad=[float(x) for x in backend._target_positions],
                entry_native_arm_velocity_rad_s=list(
                    backend.get_joint_command_state().velocity_rad_s
                ),
                entry_gripper_open=bool(backend._gripper_open),
                entry_frame_id=frame.frame_id,
                entry_checksum_sha256=frame.checksum_sha256,
                entry_joint_positions_rad=robot["joint_positions_rad"],
                entry_joint_velocities_rad_s=robot["joint_velocities_rad_s"],
                entry_finger_positions_m=robot["finger_positions_m"],
                entry_finger_velocities_m_s=robot["finger_velocities_m_s"],
            )
        trials.require(
            self.entry_command is not None
            and self.entry_command["destination_skill"] == skill
            and self.entry_command["entry_step"] <= step
            and self.entry_command["entry_command_seq"] <= seq,
            "unbound native command handoff",
        )
        return dict(
            self.entry_command,
            current_step=step,
            last_command_seq=seq,
            effective_joint_target_rad=joint_targets,
            effective_finger_target_m=finger_targets,
        )

    def check_current(self, frame, skill, target, phase):
        started = time.perf_counter_ns()
        if self.certificate is None:
            from scripts.graduation.g1_complete_cv_optical_identity import bind_allocation

            cfg = self.backend._config
            scene, episode = native_reset_ids(
                read(self.raw / "reset-observed.json"),
                self.backend._scenario.scenario_id,
                self.backend._episode_id,
            )
            binding = bind_allocation(
                (self.raw.parent / "allocation.json").read_bytes(),
                allocation_sha256=self.alloc_sha,
                generation_sha256=sha(ROOT / "runtime-build.json"),
                calibration_sha256=sha(self.calibration / "manifest.json"),
                asset_sha256=sha(self.asset_path),
                reset_scene_id=scene,
                reset_episode_id=episode,
            )
            isolated = (
                type(self.backend) is g1_dual_trials.RegisteredAssemblyBackend
                and self.backend.view == "nominal"
                and not cfg.domain_randomization
                and Path(cfg.model_path).resolve() == self.asset_path
                and sha(self.asset_path) == self.alloc["asset_sha256"]
            )
            self.certificate = LocalClearance(
                self.geometry,
                self.asset_path,
                self.calibration,
                calibration_sha256=self.calibration_hash,
                isolated_scene=isolated,
                optical_identity=binding,
            )
        if frame.frame_id in self.measurements:
            marker = self.measurements[frame.frame_id]["measurement"]
        else:
            marker = g1_dual_observer.measure_frame(
                frame, self.geometry, consumer="local_clearance"
            )
        robot = self.robot_observation(frame)
        robot["handoff"] = self.command_handoff(skill, phase, robot, frame)
        status = self.certificate.check(
            frame,
            marker,
            robot,
            skill,
            target,
            _DOWNWARD,
            phase="PRE" if phase == "STATIC_SELECTION" else phase,
        )
        finish = time.perf_counter_ns()
        began = self.clock_starts.get(frame.frame_id)
        row = dict(
            phase=phase,
            skill=skill,
            frame_id=frame.frame_id,
            checksum_sha256=frame.checksum_sha256,
            physics_step=self.backend.total_physics_steps,
            sim_time_s=frame.sim_time_s,
            status=status["status"],
            reason=status.get("reason"),
            gate_ms=(finish - started) / 1e6,
            capture_start_ns=began,
            local_end_ns=finish,
            capture_through_gate_ms=(finish - began) / 1e6 if began is not None else None,
            object_offset_m=[0.0, 0.0, 0.0],
            target_xyz=target,
            robot=robot,
            evidence=native.plain(status),
        )
        self.events.append(row)
        if status["status"] != "CLEAR":
            raise native.ComponentStopped(
                f"{skill} {phase} local RGB-D {status['status']}: {row['reason']}"
            )

    def capture(self, label):
        if label == "registration-handoff":
            # First viable fixed-wrist candidate is the registered object center. Its selection
            # uses the stopped bootstrap frame; the native handoff then acquires a new frame.
            _, _, frame = self.frames[-1]
            target = self.report["bootstrap"]["resolver_candidate_m"]
            self.check_current(frame, "MOVE_ABOVE", target, "STATIC_SELECTION")
        start = time.perf_counter_ns()
        frame = super().capture(label)
        terminals = {"GRASP/POST", "LIFT/POST", "MOVE_TO_REGION/POST", "PLACE/POST", "RELEASE/POST"}
        if label in terminals or label.startswith(("LIFT/dwell-", "RELEASE/dwell-")):
            # Observe the already scheduled native dwell exposures and handoff frames.
            # Record their current encoder and command context without an additional physics step.
            skill, phase = label.split("/", 1)
            marker = (
                self.measurements[frame.frame_id]["measurement"]
                if frame.frame_id in self.measurements
                else g1_dual_observer.measure_frame(
                    frame, self.geometry, consumer="payload_support"
                )
            )
            robot = self.robot_observation(frame)
            result = self.certificate.observe_payload_frame(frame, marker, robot, skill, phase)
            self.payload_samples.append(
                dict(
                    label=label,
                    frame_id=frame.frame_id,
                    checksum_sha256=frame.checksum_sha256,
                    physics_step=self.backend.total_physics_steps,
                    sim_time_s=frame.sim_time_s,
                    robot=robot,
                    evidence=native.plain(result),
                    elapsed_ms=(time.perf_counter_ns() - start) / 1e6,
                )
            )
        if label == "reset":
            from OpenGL import GL

            self.report["development_environment"] = {
                "renderer": GL.glGetString(GL.GL_RENDERER).decode(),
                "vendor": GL.glGetString(GL.GL_VENDOR).decode(),
                "gpu_version": GL.glGetString(GL.GL_VERSION).decode(),
                "affinity": sorted(os.sched_getaffinity(0)),
                "threads": {
                    key: os.environ.get(key) for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS")
                },
                "camera": self.geometry["camera"],
            }
        if label not in {"PRE", "POST"} and not label.endswith(("/PRE", "/POST")):
            self.clock_starts[frame.frame_id] = start
        if label == "registration-handoff":
            self.last_handoff = frame
        return frame

    def bootstrap(self):
        try:
            super().bootstrap()
        finally:
            frame = self.last_handoff
            if frame is not None:
                end = time.perf_counter_ns()
                start = self.clock_starts[frame.frame_id]
                self.report["registered_handoff_clock"] = dict(
                    frame_id=frame.frame_id,
                    checksum_sha256=frame.checksum_sha256,
                    start_ns=start,
                    end_ns=end,
                    capture_through_bootstrap_ms=(end - start) / 1e6,
                )

    def check_shield(self, obs, phase, contract, step, started, clearance):
        verdict = super().check_shield(obs, phase, contract, step, started, clearance)
        if phase == "FEEDBACK" and verdict["allowed"] and verdict["unmodified"]:
            self.check_current(obs, step.skill.value, step.parameters.get("target_pose"), phase)
        return verdict

    def admission(self, obs, phase, contract, step, binding, started, clearance):
        super().admission(obs, phase, contract, step, binding, started, clearance)
        if phase == "PRE":
            self.check_current(obs, step.skill.value, step.parameters.get("target_pose"), phase)
            if self.preflight:
                raise native.ComponentStopped("DEVELOPMENT_PREFLIGHT_PASSED_BEFORE_FIRST_DISPATCH")
            if self.approach_diagnostic and step.skill.value == "GRASP":
                raise native.ComponentStopped("DEVELOPMENT_APPROACH_PROBE_STOP_BEFORE_GRASP")


def run(repo, label, allocation_sha, case_id, *, preflight=False):
    directory = repo / trials.PRIVATE / "batches" / label
    batch = pinned(directory / "allocation.json", allocation_sha)
    generation = batch["runtime_build_sha256"]
    lock = pinned(ROOT / "runtime-build.json", generation)
    trials.require(
        ROOT == repo / trials.PRIVATE / "builds" / generation / "runtime-source"
        and batch["plan_sha256"] == lock["plan_sha256"] == trials.PLAN_SHA,
        "foreign generation",
    )
    check_tree(ROOT, lock["runtime_files_sha256"], inherited=True)
    reg = pinned(repo / trials.PRIVATE / "registration.json", batch["registration_sha256"])
    slots = trials.select_slots(reg, label)
    trials.require(
        label.startswith("train-preflight-") == preflight, "preflight claim label differs"
    )
    trials.require(
        len(slots) == len(batch["cases"])
        and all(
            all(row.get(k) == v for k, v in slot.items() if k != "scope")
            for slot, row in zip(slots, batch["cases"], strict=True)
        ),
        "allocated placements differ",
    )
    row = next(r for r in batch["cases"] if r["id"] == case_id)
    if label == "evaluation":
        sources = batch["training_scores_sha256"]
        trials.training_gate(
            [trials.read_sealed_score(repo / trials.PRIVATE / p, h) for p, h in sources.items()],
            generation,
            batch["calibration_sha256"],
        )
        for earlier in batch["cases"][: row["slot"] - 1]:
            prior = trials.read_sealed_score(directory / earlier["id"] / "independent-score.json")
            result = prior["result"]
            trials.require(
                result["independent_physical_outcome"].get("safety_violation") is False
                and result["hand_contacts"]["board_or_support_hand_or_finger_steps"] == [],
                "earlier independent slot has a physical safety stop",
            )
    pinned(Path(batch["calibration_directory"]) / "manifest.json", batch["calibration_sha256"])
    events = []
    payload_samples = []
    claimed = None
    instance = directory / case_id / "instance"

    def reserve():
        nonlocal claimed
        claimed = g1_visibility_trials.reserve_attempt(
            instance.parent / "attempt.json",
            dict(
                id=case_id,
                slot=row["slot"],
                scope=batch["scope"],
                attempt=1,
                release=batch["release"],
                runtime_build_sha256=generation,
                allocation_sha256=allocation_sha,
                calibration_sha256=batch["calibration_sha256"],
                claimed_at=datetime.now(UTC).isoformat(),
                hardware_actions=0,
                formal_claims=0,
                pid=os.getpid(),
            ),
        )
        return claimed

    failures = []
    with (
        g1_dual_trials.exclusive_egl(repo / trials.OLD),
        bind_scene(row["scene_id"]),
        g1_visibility_runtime.log_measurements() as measured,
        observe_sample_failures(failures),
    ):
        try:
            g1_dual_trials.g1_mount_trials.capture(
                repo / trials.ROUND / "plan.json",
                directory,
                allocation_sha,
                case_id,
                context=lambda *_: (batch, lock),
                case_reader=g1_visibility_trials.load_case,
                episode_factory=lambda *args: ClearanceEpisode(
                    *args, measured, events, preflight, payload_samples
                ),
                before_start=reserve,
            )
        finally:
            if claimed and instance.is_dir():
                acquisition = instance / "acquisition-seal.json"
                acq_sha = sha(acquisition) if acquisition.exists() else None
                vision = instance / "online-vision.json"
                write(
                    vision,
                    dict(
                        attempt_sha256=claimed,
                        source_files_sha256=lock["detector_files_sha256"],
                        frames=measured,
                    ),
                )
                write(
                    instance / "online-vision-seal.json",
                    dict(
                        online_vision_sha256=sha(vision),
                        attempt_sha256=claimed,
                        acquisition_sha256=acq_sha,
                    ),
                )
                local = instance / "local-clearance.json"
                write(
                    local,
                    dict(
                        schema="g1.development.local-clearance.v2",
                        runtime_build_sha256=generation,
                        calibration_sha256=batch["calibration_sha256"],
                        plan_sha256=trials.PLAN_SHA,
                        rows=events,
                        passive_payload_samples=payload_samples,
                        failed_feedback=failures,
                        preflight=preflight,
                    ),
                )
                write(
                    instance / "local-clearance-seal.json",
                    dict(
                        local_clearance_sha256=sha(local),
                        acquisition_seal_sha256=acq_sha,
                        attempt_sha256=claimed,
                    ),
                )
    return read(instance / "receipt.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path)
    parser.add_argument("label")
    parser.add_argument("batch_sha256")
    parser.add_argument("case_id")
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()
    result = run(
        args.repo.resolve(), args.label, args.batch_sha256, args.case_id, preflight=args.preflight
    )
    print(
        f"{args.case_id} captured {result['captured_frames']} frames over "
        f"{result['actual_physics_steps']} physics steps"
    )
