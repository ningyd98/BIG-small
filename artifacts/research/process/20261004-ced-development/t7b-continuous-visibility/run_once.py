"""One excluded teacher attempt with lossless RGBD at every real physics step.

Preparation is CPU/read-only with respect to the simulator. Execution requires
the root's separately frozen command; there is no retry, provider, or decoder.
"""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import importlib.util
import json
import subprocess
import time
import traceback
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import fields, is_dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from cloud_edge_robot_arm.datasets.rgbd import teacher
from cloud_edge_robot_arm.datasets.rgbd.models import SceneSpec
from cloud_edge_robot_arm.research.step_rgbd import StepRGBDRecorder
from cloud_edge_robot_arm.simulation.mujoco.camera import MuJoCoRGBDCamera
from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
    CompletionCriteria,
    evaluate_episode,
)
from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot
from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession
from cloud_edge_robot_arm.vision.observations import observation_from_sensor_frame

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
PRIOR = HERE.parent / "t7b-visible-marker-next"
ASSET_HASH = "ddc34b13d8df403f3fdeeab94be75ca988541f2eac0a3e534704f68200c39a23"
ROBOT_ACTIONS = ("move_above", "approach", "grasp", "lift", "move_to_region", "place", "release")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def plain(value):
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: plain(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, bytes):
        return {"bytes_base64": base64.b64encode(value).decode(), "sha256": digest(value)}
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return {"opaque_type": type(value).__module__ + "." + type(value).__qualname__}


def json_bytes(value) -> bytes:
    return json.dumps(plain(value), sort_keys=True, allow_nan=False).encode()


def write_new(path: Path, value) -> None:
    with path.open("x") as stream:
        stream.write(json.dumps(plain(value), indent=2, allow_nan=False) + "\n")


def save_observation_gzip(path: Path, observation) -> dict:
    raw = observation.model_dump_json().encode()
    zipped = gzip.compress(raw, compresslevel=1, mtime=0)
    with path.open("xb") as stream:
        stream.write(zipped)
    return {
        "file": path.name,
        "original_sha256": digest(raw),
        "compressed_sha256": digest(zipped),
        "original_bytes": len(raw),
        "compressed_bytes": len(zipped),
        "observation_checksum_sha256": observation.checksum_sha256,
    }


def prior_specification():
    spec = importlib.util.spec_from_file_location(
        "ced_frozen_boundary_runner", PRIOR / "run_once.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("frozen prior specification unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.specification()


def specification():
    scene, config = prior_specification()
    scene = SceneSpec.model_validate(
        {**scene.model_dump(), "group_id": "dev-marker-continuous-" + scene.scene_hash[:24]}
    )
    if scene.asset_family_hash != ASSET_HASH or config.physics_dt_s > 0.005:
        raise RuntimeError("frozen asset/physical cadence differs")
    return scene, config


def read_jsonl_gzip(path: Path):
    with gzip.open(path, "rt") as stream:
        for line in stream:
            yield json.loads(line)


class NominalJournal:
    def __init__(self, path: Path):
        self.raw = path.open("xb")
        self.stream = gzip.GzipFile(fileobj=self.raw, mode="wb", compresslevel=1, mtime=0)
        self.sequence = 0
        self.failed = None
        self.last_control = None
        self.last_physics = None

    def emit(self, event: str, **payload):
        if self.failed is not None:
            raise RuntimeError("nominal journal stopped")
        self.sequence += 1
        before = time.monotonic_ns()
        utc = datetime.now(UTC)
        after = time.monotonic_ns()
        row = {
            "record_seq": self.sequence,
            "event": event,
            "clock": {
                "monotonic_before_ns": before,
                "utc": utc.isoformat(),
                "monotonic_after_ns": after,
                "external_utc_uncertainty": "UNAVAILABLE",
            },
            **plain(payload),
        }
        try:
            self.stream.write(json_bytes(row) + b"\n")
            self.stream.flush()
            self.raw.flush()
        except BaseException as error:
            self.failed = f"{type(error).__name__}: {error}"
            raise
        return row

    def operation(self, event):
        self.emit("OPERATION", source=event)
        if event.phase == "END" and event.error_type is None:
            if event.kind == "CONTROL":
                self.last_control = event.operation_id
            elif event.kind == "PHYSICS":
                self.last_physics = event.operation_id

    def ensure(self, backend):
        if self.failed:
            raise RuntimeError("nominal journal persistence failure: " + self.failed)
        if backend._operation_observer_failures:
            raise RuntimeError("operation observer failure retained by backend")

    def close(self):
        try:
            self.stream.close()
        finally:
            self.raw.close()


def array_state(value) -> str:
    """Hash every exposed NumPy array; include names/shapes/dtypes in the domain."""
    hashed = hashlib.sha256()
    for name in sorted(dir(value)):
        if name.startswith("_"):
            continue
        member = getattr(value, name)
        if isinstance(member, np.ndarray):
            hashed.update(json_bytes((name, member.shape, member.dtype.str)))
            hashed.update(member.tobytes())
    return hashed.hexdigest()


def scalar_struct(value, depth=0):
    result = {}
    for name in sorted(dir(value)):
        if name.startswith("_"):
            continue
        member = getattr(value, name)
        if isinstance(member, (str, int, float, bool, np.ndarray, np.generic)):
            result[name] = plain(member)
        elif depth < 2 and type(member).__module__.startswith("mujoco"):
            result[name] = scalar_struct(member, depth + 1)
    return result


def capture_state(backend) -> dict:
    model, data = backend._model, backend._data
    model_scalars = {
        name: scalar_struct(getattr(model, name))
        for name in ("opt", "stat", "vis")
        if hasattr(model, name)
    }
    controls = {
        name: getattr(backend, name)
        for name in (
            "_target_positions",
            "_pending_joint_targets",
            "_gripper_open",
            "_estop_engaged",
            "_actuator_delay_steps",
        )
    }
    return {
        "data_arrays_sha256": array_state(data),
        "sim_time_s": float(data.time),
        "model_arrays_sha256": array_state(model),
        "model_options_sha256": digest(json_bytes(model_scalars)),
        "controller_state_sha256": digest(json_bytes(controls)),
        "rng_state_sha256": digest(json_bytes(backend._rng.bit_generator.state)),
        "sensor_cache_object_id": id(backend._sensor_frame),
        "camera_object_id": id(backend._camera),
        "physical_step": backend.total_physics_steps,
        "command_count": len(backend.command_records),
        "sensor_noise_std_m": backend._sensor_noise_std_m,
    }


class CaptureAdapter:
    def __init__(self, backend, journal):
        if backend._camera is None:
            raise RuntimeError("explicit bootstrap must initialize the sole camera")
        self.backend, self.journal = backend, journal
        self.camera = backend._camera
        self.last_capture = None
        self.calls = 0

    def __call__(self):
        backend = self.backend
        self.journal.ensure(backend)
        if backend._sensor_noise_std_m != 0.0:
            raise RuntimeError("extra RGBD requires exact zero noise")
        if backend._camera is not self.camera:
            raise RuntimeError("same-camera identity changed")
        before = capture_state(backend)
        self.calls += 1
        started = time.monotonic_ns()
        frame, ids, labels, hashes = self.camera._capture(
            backend._data,
            rng=backend._rng,
            noise_std_m=0.0,
            scene_id=backend._scenario.scenario_id,
            episode_id=backend._episode_id,
            include_instances=False,
        )
        after = capture_state(backend)
        self.last_capture = {
            "capture_monotonic_begin_ns": started,
            "capture_monotonic_end_ns": time.monotonic_ns(),
            "sensor_latency_ms": frame.latency_ms,
            "before_state": before,
            "after_state": after,
            "state_unchanged": before == after,
            "pass_state_hashes": hashes,
        }
        if before != after:
            raise RuntimeError("extra RGBD capture changed data/model/control/RNG/cache state")
        if ids or labels or len(hashes) != 2 or hashes[0] != hashes[1]:
            raise RuntimeError("two truth-free registered passes required")
        observation = observation_from_sensor_frame(frame, source="mujoco_camera")
        return observation, hashes


class ActionTracker:
    def __init__(self, backend, journal):
        self.backend, self.journal = backend, journal
        self.current = None
        self.begins = self.ends = 0
        self.returned = []

    def invoke(self, action_type, original, *args, **kwargs):
        self.journal.ensure(self.backend)
        if self.current is not None:
            raise RuntimeError("unexpected nested original action")
        ordinal = self.begins + 1
        start_step = self.backend.total_physics_steps
        command_start = len(self.backend.command_records) + 1
        self.journal.emit(
            "ACTION_BEGIN",
            action_ordinal=ordinal,
            action_type=action_type,
            episode_id=self.backend._episode_id,
            start_step=start_step,
            sim_time_s=self.backend.get_sim_time(),
            command_seq_start=command_start,
            arguments=args,
            keyword_arguments=kwargs,
        )
        self.begins += 1
        self.current = ordinal
        result = error = None
        try:
            result = original(*args, **kwargs)
            self.returned.append(
                {
                    "action_ordinal": ordinal,
                    "start_step": start_step,
                    "end_step": self.backend.total_physics_steps,
                    "command_seq_start": command_start,
                    "command_seq_end": len(self.backend.command_records) + 1,
                }
            )
            return result
        except BaseException as exception:
            error = exception
            raise
        finally:
            self.current = None
            self.ends += 1
            try:
                self.journal.emit(
                    "ACTION_END",
                    action_ordinal=ordinal,
                    action_type=action_type,
                    episode_id=self.backend._episode_id,
                    start_step=start_step,
                    end_step=self.backend.total_physics_steps,
                    sim_time_s=self.backend.get_sim_time(),
                    command_seq_start=command_start,
                    command_seq_end=len(self.backend.command_records) + 1,
                    result=result,
                    error_type=type(error).__name__ if error else None,
                    error=str(error) if error else None,
                )
                if error is None:
                    self.journal.ensure(self.backend)
            except BaseException:
                if error is None:
                    raise


@contextmanager
def wrap_original_actions(robot, teacher_module, tracker):
    absent = object()
    saved = {name: robot.__dict__.get(name, absent) for name in ROBOT_ACTIONS}
    original_dwell = teacher_module._dwell
    try:
        for name in ROBOT_ACTIONS:
            original = getattr(robot, name)

            def wrapper(*args, _original=original, _name=name, **kwargs):
                return tracker.invoke(_name.upper(), _original, *args, **kwargs)

            setattr(robot, name, wrapper)

        def dwell(*args, **kwargs):
            return tracker.invoke("OBSERVE", original_dwell, *args, **kwargs)

        teacher_module._dwell = dwell
        yield
    finally:
        teacher_module._dwell = original_dwell
        for name, value in saved.items():
            if value is absent:
                robot.__dict__.pop(name, None)
            else:
                setattr(robot, name, value)


def prepare():
    scene, config = specification()
    old = json.loads((PRIOR / "source-hashes.json").read_text())
    for name, expected in old.items():
        if digest((ROOT / name).read_bytes()) != expected:
            raise RuntimeError("prior frozen input changed: " + name)
    source_names = set(old) | {
        "src/cloud_edge_robot_arm/research/step_rgbd.py",
        "tests/test_step_rgbd.py",
        str((HERE / "run_once.py").relative_to(ROOT)),
        str((HERE / "verify_offline.py").relative_to(ROOT)),
    }
    snapshot = HERE / "source-before"
    snapshot.mkdir()
    sources = {}
    for name in sorted(source_names):
        original = ROOT / name
        data = original.read_bytes()
        sources[name] = digest(data)
        destination = snapshot / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    write_new(HERE / "execution-source-hashes.json", sources)
    write_new(
        HERE / "header.json",
        {
            "scope": "EXCLUDED_DEVELOPMENT_WHOLE_STEP_TEACHER_RGBD",
            "attempt_limit": 1,
            "scene": scene.model_dump(mode="json"),
            "config": config.model_dump(mode="json"),
            "scene_hash": scene.scene_hash,
            "asset_sha256": ASSET_HASH,
            "settle_steps": 120,
            "capture_policy": "STEP_ZERO_AND_EVERY_REAL_PHYSICS_STEP",
            "original_max_sample_gap_s": CompletionCriteria(
                "object", "target_region"
            ).max_sample_gap_s,
            "source_manifest_sha256": digest((HERE / "execution-source-hashes.json").read_bytes()),
            "source_count": len(sources),
            "source_bytes": sum((ROOT / p).stat().st_size for p in sources),
            "preparation_git_head_historical": subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True
            ).stdout.strip(),
            "git_head_live_equality_required": False,
            "frame_payload_format": "GZIP1_FULL_OBSERVATION_JSON_EXACT_PNG_DEPTH_F32_MASK_BASE64",
            "teacher_truth_scope": "OFFLINE_TARGETS_AND_INDEPENDENT_SCORER_ONLY",
            "decoder_scope": "SEPARATE_OFFLINE_RGBD_AND_MARKER_REGISTRATION_ONLY",
            "raw_v3_status": "NOT_PRODUCED_OFFLINE_SCENE_SETUP_HAS_NO_OBSERVED_RESET",
            "clock_scope": "SAME_PROCESS_NOMINAL_BRACKETS_EXTERNAL_UNCERTAINTY_UNAVAILABLE",
            "formal_accepted": False,
            "native_admission": "NOT_PROMOTED",
            "continuous_motion": "NOT_CERTIFIED",
            "future_stability": "UNAVAILABLE",
        },
    )
    print(
        json.dumps(
            {
                "status": "PREPARED_NO_ACTUAL_CALLS",
                "source_count": len(sources),
                "group_id": scene.group_id,
                "scene_hash": scene.scene_hash,
            }
        )
    )


def execute_once():
    header = json.loads((HERE / "header.json").read_text())
    sources = json.loads((HERE / "execution-source-hashes.json").read_text())
    if (
        digest((HERE / "execution-source-hashes.json").read_bytes())
        != header["source_manifest_sha256"]
    ):
        raise RuntimeError("prepared source manifest changed")
    for name, expected in sources.items():
        if digest((ROOT / name).read_bytes()) != expected:
            raise RuntimeError("frozen actual input changed: " + name)
    scene, config = specification()
    if (
        scene.model_dump(mode="json") != header["scene"]
        or config.model_dump(mode="json") != header["config"]
    ):
        raise RuntimeError("prepared scene/config changed")
    directory = HERE / "attempt-1"
    directory.mkdir()  # No replay, resume, overwrite, or second attempt.
    journal = NominalJournal(directory / "nominal-journal.jsonl.gz")
    recorder = teacher.EpisodeRecorder()
    series = tracker = adapter = None
    failure = outcome = None
    counts = {
        "session_setup_capture_calls": 0,
        "bootstrap_capture_calls": 0,
        "teacher_boundary_capture_calls": 0,
        "cached_updates_suppressed": 0,
    }
    setup_frames, boundary_frames = [], []
    original_capture = MuJoCoRGBDCamera.capture
    original_instances = MuJoCoRGBDCamera.capture_with_instances
    original_teacher_capture = teacher._capture
    phase = "SETUP"
    started = time.monotonic_ns()

    def counted_setup(camera, *args, **kwargs):
        counts["session_setup_capture_calls"] += 1
        value = original_capture(camera, *args, **kwargs)
        setup_frames.append(value)
        return value

    def counted_instances(camera, *args, **kwargs):
        key = (
            "bootstrap_capture_calls" if phase == "BOOTSTRAP" else "teacher_boundary_capture_calls"
        )
        counts[key] += 1
        return original_instances(camera, *args, **kwargs)

    def retain_teacher_boundary(backend):
        value = original_teacher_capture(backend)
        boundary_frames.append(value)
        return value

    MuJoCoRGBDCamera.capture = counted_setup
    MuJoCoRGBDCamera.capture_with_instances = counted_instances
    teacher._capture = retain_teacher_boundary
    try:
        journal.emit("SETUP_BEGIN", scope="OFFLINE_SCENE_APPLICATION_NOT_OBSERVED_RESET")
        with MuJoCoCaptureSession(config) as session:
            session.apply_scene(scene)
            backend = session._backend
            if backend._sensor_noise_std_m != 0.0:
                raise RuntimeError("applied scene must have exact zero noise")
            journal.emit(
                "SETUP_END",
                episode_id=backend._episode_id,
                physics_step=backend.total_physics_steps,
                sim_time_s=backend.get_sim_time(),
                setup_state=capture_state(backend),
                reset_source="DIRECT_OFFLINE_SCENE_ADAPTER",
            )
            original_update, original_get_sensor = (
                backend._update_sensor_frame,
                backend.get_sensor_frame,
            )

            def suppress_cached_render():
                counts["cached_updates_suppressed"] += 1

            def forbidden_cached_sensor(*args, **kwargs):
                raise RuntimeError("cached sensor use violates declared capture policy")

            robot = MuJoCoSkillRobot(backend)
            original_robot_observe = robot.__dict__.get("observe")
            backend._update_sensor_frame = suppress_cached_render
            backend.get_sensor_frame = forbidden_cached_sensor
            robot.observe = forbidden_cached_sensor
            try:
                with backend.observe_operation_boundaries(journal.operation):
                    phase = "BOOTSTRAP"
                    sensor, _, _, hashes = backend.capture_sensor_frame_with_instances()
                    if len(hashes) != 3 or len(set(hashes)) != 1:
                        raise RuntimeError("bootstrap registered state mismatch")
                    bootstrap = observation_from_sensor_frame(sensor, source="mujoco_camera")
                    journal.emit(
                        "BOOTSTRAP_SAVED",
                        **save_observation_gzip(
                            directory / "bootstrap-observation.json.gz", bootstrap
                        ),
                        pass_state_hashes=hashes,
                        sensor_latency_ms=sensor.latency_ms,
                    )
                    phase = "TEACHER"
                    adapter = CaptureAdapter(backend, journal)
                    tracker = ActionTracker(backend, journal)
                    series = StepRGBDRecorder(
                        directory / "whole-step",
                        adapter,
                        episode_id=backend._episode_id,
                        max_sample_gap_s=header["original_max_sample_gap_s"],
                    )

                    def physical(snapshot):
                        journal.ensure(backend)
                        identity = {
                            "episode_id": snapshot.episode_id,
                            "physics_step": snapshot.physics_step,
                            "sim_time_s": snapshot.sim_time_s,
                        }
                        journal.emit(
                            "ACQUISITION_BEGIN",
                            **identity,
                            action_ordinal=tracker.current,
                            phase="ACTION" if tracker.current else "SETTLING",
                            control_operation_id=journal.last_control,
                            physics_operation_id=journal.last_physics,
                            command_seq_next=len(backend.command_records) + 1,
                            physical_source=snapshot,
                        )
                        try:
                            row = series.record_step(**identity)
                        except BaseException as error:
                            try:
                                journal.emit(
                                    "ACQUISITION_FAILED",
                                    **identity,
                                    action_ordinal=tracker.current,
                                    camera=adapter.last_capture,
                                    error_type=type(error).__name__,
                                    error=str(error),
                                )
                            except BaseException:
                                pass  # Retain original failure and stopped recorder.
                            raise
                        journal.emit(
                            "ACQUISITION_END",
                            **identity,
                            action_ordinal=tracker.current,
                            control_operation_id=journal.last_control,
                            physics_operation_id=journal.last_physics,
                            saved=row,
                            camera=adapter.last_capture,
                        )
                        if snapshot.physics_step % 240 == 0:
                            print(
                                json.dumps(
                                    {
                                        "captured_step": snapshot.physics_step,
                                        "sim_time_s": snapshot.sim_time_s,
                                    }
                                ),
                                flush=True,
                            )

                    def action(event):
                        journal.ensure(backend)
                        expected = tracker.returned[-1]
                        for key in (
                            "start_step",
                            "end_step",
                            "command_seq_start",
                            "command_seq_end",
                        ):
                            if event[key] != expected[key]:
                                raise RuntimeError("teacher/original wrapper action span mismatch")
                        journal.emit(
                            "TEACHER_ACTION",
                            action_ordinal=expected["action_ordinal"],
                            source=event,
                        )

                    with backend.observe_actuator_steps(
                        lambda value: journal.emit(
                            "ACTUATOR",
                            action_ordinal=tracker.current,
                            control_operation_id=journal.last_control,
                            source=value,
                        )
                    ):
                        with wrap_original_actions(robot, teacher, tracker):
                            outcome = teacher.run_teacher_episode(
                                scene,
                                robot,
                                recorder,
                                case="NORMAL",
                                settle_steps=120,
                                physical_observer=physical,
                                action_observer=action,
                            )
                    journal.ensure(backend)
                    rescored = evaluate_episode(
                        backend,
                        CompletionCriteria("object", "target_region"),
                        evidence=recorder.physical_samples,
                        evaluation_start_step=recorder.evaluation_start_step,
                    )
                    if rescored != outcome:
                        raise RuntimeError("independent scorer changed")
            except BaseException:
                failure = traceback.format_exc()
            finally:
                backend._update_sensor_frame = original_update
                backend.get_sensor_frame = original_get_sensor
                if original_robot_observe is None:
                    robot.__dict__.pop("observe", None)
                else:
                    robot.observe = original_robot_observe
                terminal = {
                    "final_step": backend.total_physics_steps,
                    "final_sim_time_s": backend.get_sim_time(),
                }
                series_summary = series.finish(**terminal) if series else None
                if series_summary is None or series_summary["status"] != "COMPLETE":
                    failure = failure or "whole-step terminal horizon incomplete"
                write_new(
                    directory / "terminal.json",
                    {
                        **terminal,
                        "episode_id": backend._episode_id,
                        "whole_step": series_summary,
                        "commands": backend.command_records,
                        "operation_ledger": backend._operation_ledger,
                        "operation_observer_failures": backend._operation_observer_failures,
                        "observer_overhead_ns": backend._operation_observer_overhead_ns,
                    },
                )
    except BaseException:
        failure = failure or traceback.format_exc()
    finally:
        MuJoCoRGBDCamera.capture = original_capture
        MuJoCoRGBDCamera.capture_with_instances = original_instances
        teacher._capture = original_teacher_capture
        if failure:
            (directory / "failure.txt").write_text(failure)
        for name, frames_ in (
            ("session-setup", setup_frames),
            ("teacher-boundaries", boundary_frames),
        ):
            target = directory / name
            target.mkdir()
            members = []
            for ordinal, frame in enumerate(frames_):
                value = (
                    observation_from_sensor_frame(frame, source="mujoco_camera")
                    if name == "session-setup"
                    else frame
                )
                member = save_observation_gzip(target / f"{ordinal:02d}.json.gz", value)
                if name == "session-setup":
                    member["sensor_latency_ms"] = frame.latency_ms
                members.append(member)
            write_new(target / "members.json", members)
        write_new(
            directory / "teacher-evidence.json",
            {
                "physical_samples": recorder.physical_samples,
                "evaluation_start_step": recorder.evaluation_start_step,
                "actions": [frame.action for frame in recorder.frames],
                "unframed_actions": recorder.unframed_actions,
                "outcome": outcome,
            },
        )
        summary = {
            "scope": header["scope"],
            "group_id": scene.group_id,
            "scene_hash": scene.scene_hash,
            "run_status": "PARTIAL_OR_FAILED" if failure else "COMPLETED_SINGLE_ATTEMPT",
            "wall_elapsed_s": (time.monotonic_ns() - started) / 1e9,
            "counts": counts,
            "whole_step_capture_calls": adapter.calls if adapter else 0,
            "action_begins": tracker.begins if tracker else 0,
            "action_ends": tracker.ends if tracker else 0,
            "framed_actions": len(recorder.frames),
            "unframed_actions": len(recorder.unframed_actions),
            "nominal_journal_failure": journal.failed,
            "formal_accepted": False,
            "native_admission": "NOT_PROMOTED",
            "continuous_motion": "NOT_CERTIFIED",
            "future_stability": "UNAVAILABLE",
            "raw_v3_status": header["raw_v3_status"],
            "decoder_calls": 0,
        }
        write_new(directory / "summary.json", summary)
        journal.close()
        print(json.dumps(summary, indent=2), flush=True)
    if failure:
        raise RuntimeError("single attempt failed; evidence preserved; no retry")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--prepare", action="store_true")
    choice.add_argument("--execute-once", action="store_true")
    args = parser.parse_args()
    prepare() if args.prepare else execute_once()
