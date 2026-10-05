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
from cloud_edge_robot_arm.research import mujoco_state_guard as state_guard
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
        {**scene.model_dump(), "group_id": "dev-marker-continuous-v3-" + scene.scene_hash[:24]}
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


def model_array_state(value) -> str:
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


PROTOCOL = "research.custom-whole-step-guarded-rgbd.v3"
GUARD_PROTOCOL = "research.mujoco-support-aware-state.v1"


def capture_state(backend, contract):
    """Hash all real data views; never call the legacy aggregate on MjData."""
    model, data = backend._model, backend._data
    runtime = backend._mujoco
    if (
        runtime.__version__ != "3.3.7"
        or type(data) is not runtime.MjData
        or type(model) is not runtime.MjModel
    ):
        raise RuntimeError("exact pinned live MuJoCo runtime classes/version required")
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
    protected = {
        "sim_time_s": float(data.time),
        "model_arrays_sha256": model_array_state(model),
        "model_options_sha256": digest(json_bytes(model_scalars)),
        "controller_state_sha256": digest(json_bytes(controls)),
        "rng_state_sha256": digest(json_bytes(backend._rng.bit_generator.state)),
        "sensor_cache_object_id": id(backend._sensor_frame),
        "camera_object_id": id(backend._camera),
        "physical_step": backend.total_physics_steps,
        "command_count": len(backend.command_records),
        "sensor_noise_std_m": backend._sensor_noise_std_m,
        "physics_state_sha256": MuJoCoRGBDCamera._physics_state_hash(data),
    }
    arrays = state_guard.snapshot_data_arrays(
        data, model, contract=contract, runtime_version=runtime.__version__
    )
    guarded = state_guard.attach_protected_state(arrays, protected)
    return {
        "protocol": GUARD_PROTOCOL,
        "guard": plain(guarded),
        "state": {**protected, "data_arrays_sha256": arrays.digest},
    }


class CaptureAdapter:
    def __init__(self, backend, journal, contract):
        if backend._camera is None:
            raise RuntimeError("explicit bootstrap must initialize the sole camera")
        self.backend, self.journal, self.contract = backend, journal, contract
        self.camera = backend._camera
        self.camera_context = self.context()
        self.last_capture = None
        self.allocated = self.calls = 0

    def context(self):
        camera, backend = self.camera, self.backend
        if (
            type(camera) is not MuJoCoRGBDCamera
            or camera._model is not backend._model
            or camera._mujoco is not backend._mujoco
            or (camera._width, camera._height) != (640, 480)
            or camera._camera_id != backend._model.camera("rgbd").id
        ):
            raise RuntimeError("exact sole configured 640 top camera required")
        return (
            id(camera._model),
            id(camera._mujoco),
            camera._width,
            camera._height,
            camera._camera_id,
            id(camera._renderer),
        )

    def __call__(self):
        self.allocated += 1
        self.last_capture = None
        backend = self.backend
        self.journal.ensure(backend)
        if backend._sensor_noise_std_m != 0.0:
            raise RuntimeError("extra RGBD requires exact zero noise")
        if backend._camera is not self.camera or self.context() != self.camera_context:
            raise RuntimeError("same-camera identity changed")
        before = capture_state(backend, self.contract)
        started = time.monotonic_ns()
        self.last_capture = {
            "guard_protocol": GUARD_PROTOCOL,
            "before_guard": before["guard"],
            "before_state": before["state"],
            "camera_call_started": False,
        }
        self.calls += 1
        self.last_capture["camera_call_started"] = True
        frame, ids, labels, hashes = self.camera._capture(
            backend._data,
            rng=backend._rng,
            noise_std_m=0.0,
            scene_id=backend._scenario.scenario_id,
            episode_id=backend._episode_id,
            include_instances=False,
        )
        ended = time.monotonic_ns()
        after = capture_state(backend, self.contract)
        if self.context() != self.camera_context:
            raise RuntimeError("camera context changed during extra capture")
        self.last_capture.update(
            capture_monotonic_begin_ns=started,
            capture_monotonic_end_ns=ended,
            sensor_latency_ms=frame.latency_ms,
            after_guard=after["guard"],
            after_state=after["state"],
            state_unchanged=before == after,
            pass_state_hashes=hashes,
        )
        if before != after:
            raise RuntimeError("extra RGBD changed complete support-aware guarded state")
        if (
            ids
            or labels
            or len(hashes) != 2
            or hashes[0] != hashes[1]
            or hashes[0] != before["state"]["physics_state_sha256"]
        ):
            raise RuntimeError("two truth-free registered guarded passes required")
        return observation_from_sensor_frame(frame, source="mujoco_camera"), hashes


class AcquisitionCoordinator:
    """One allocated attempt per callback, with publication and camera denominators separate."""

    def __init__(self, backend, journal, series, tracker, adapter):
        self.backend, self.journal, self.series = backend, journal, series
        self.tracker, self.adapter = tracker, adapter
        self.allocated = self.completed = self.failed = 0
        self.failure_journal_errors = []
        self.stopped = False

    def record(self, snapshot):
        if self.stopped:
            raise RuntimeError("acquisition stopped; no retry")
        self.allocated += 1
        identity = {
            "episode_id": snapshot.episode_id,
            "physics_step": snapshot.physics_step,
            "sim_time_s": snapshot.sim_time_s,
        }
        action = self.tracker.current
        self.adapter.last_capture = None
        try:
            self.journal.ensure(self.backend)
            self.journal.emit(
                "ACQUISITION_BEGIN",
                **identity,
                action_ordinal=action,
                phase="ACTION" if action else "SETTLING",
                control_operation_id=self.journal.last_control,
                physics_operation_id=self.journal.last_physics,
                command_seq_next=len(self.backend.command_records) + 1,
                physical_source=snapshot,
            )
            row = self.series.record_step(**identity)
            self.journal.emit(
                "ACQUISITION_END",
                **identity,
                action_ordinal=action,
                control_operation_id=self.journal.last_control,
                physics_operation_id=self.journal.last_physics,
                saved=row,
                camera=self.adapter.last_capture,
            )
            self.completed += 1
            return row
        except BaseException as error:
            self.failed += 1
            self.stopped = True
            try:
                self.journal.emit(
                    "ACQUISITION_FAILED",
                    **identity,
                    action_ordinal=action,
                    camera=self.adapter.last_capture,
                    error_type=type(error).__name__,
                    error=str(error),
                )
            except BaseException as publication_error:
                note = "FAILED journal publication failed: " + repr(publication_error)
                self.failure_journal_errors.append(note)
                error.add_note(note)
            raise


class ActionTracker:
    """Delegate an original action once and retain failed publication attempts."""

    def __init__(self, backend, journal):
        self.backend, self.journal = backend, journal
        self.current = None
        self.begins = self.ends = self.failed = self.delegated = 0
        self.failure_journal_errors = []
        self.returned = []
        self.stopped = False

    def invoke(self, action_type, original, *args, **kwargs):
        if self.stopped:
            raise RuntimeError("action tracker stopped; no retry")
        if self.current is not None:
            raise RuntimeError("unexpected nested original action")
        self.begins += 1
        ordinal = self.begins
        start_step = self.backend.total_physics_steps
        command_start = len(self.backend.command_records) + 1
        identity = dict(
            action_ordinal=ordinal,
            action_type=action_type,
            episode_id=self.backend._episode_id,
            start_step=start_step,
            command_seq_start=command_start,
        )
        result = None
        try:
            self.journal.ensure(self.backend)
            self.journal.emit(
                "ACTION_BEGIN",
                **identity,
                sim_time_s=self.backend.get_sim_time(),
                arguments=args,
                keyword_arguments=kwargs,
            )
            self.current = ordinal
            self.delegated += 1
            result = original(*args, **kwargs)
            span = dict(
                action_ordinal=ordinal,
                start_step=start_step,
                end_step=self.backend.total_physics_steps,
                command_seq_start=command_start,
                command_seq_end=len(self.backend.command_records) + 1,
            )
            self.journal.emit(
                "ACTION_END",
                **identity,
                end_step=span["end_step"],
                command_seq_end=span["command_seq_end"],
                sim_time_s=self.backend.get_sim_time(),
                result=result,
                error_type=None,
                error=None,
            )
            self.ends += 1
            self.journal.ensure(self.backend)
            self.returned.append(span)
            return result
        except BaseException as error:
            self.failed += 1
            self.stopped = True
            try:
                self.journal.emit(
                    "ACTION_FAILED",
                    **identity,
                    end_step=self.backend.total_physics_steps,
                    command_seq_end=len(self.backend.command_records) + 1,
                    result=result,
                    error_type=type(error).__name__,
                    error=str(error),
                )
            except BaseException as publication_error:
                note = "ACTION_FAILED journal publication failed: " + repr(publication_error)
                self.failure_journal_errors.append(note)
                error.add_note(note)
            raise
        finally:
            self.current = None


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


def source_preflight(header, directory=HERE):
    manifest_path = directory / "execution-source-hashes.json"
    index_path = directory / "execution-archive-index.json"
    if (
        digest(manifest_path.read_bytes()) != header["source_manifest_sha256"]
        or digest(index_path.read_bytes()) != header["source_archive_index_sha256"]
    ):
        raise RuntimeError("prepared manifest/archive index changed")
    sources, archives = json.loads(manifest_path.read_text()), json.loads(index_path.read_text())
    if (
        set(sources) != set(archives)
        or len(sources) != header["source_count"]
        or len(sources) != 32
    ):
        raise RuntimeError("prepared source inventory differs")
    for name, expected in sources.items():
        data = (ROOT / name).read_bytes()
        archived = (HERE.parent / archives[name]["archive"]).read_bytes()
        if (
            digest(data) != expected
            or digest(archived) != expected
            or len(data) != archives[name]["bytes"]
            or archives[name]["sha256"] != expected
        ):
            raise RuntimeError("frozen source/archive changed: " + name)
    guard_name = "src/cloud_edge_robot_arm/research/mujoco_state_guard.py"
    if (
        sources.get(guard_name) != header["guard_core_sha256"]
        or digest(Path(state_guard.__file__).read_bytes()) != header["guard_core_sha256"]
    ):
        raise RuntimeError("loaded guard/source pin differs")
    for member in header["environment"]["files"].values():
        if digest(Path(member["path"]).read_bytes()) != member["sha256"]:
            raise RuntimeError("frozen environment dependency changed")
    if header["protocol"] != PROTOCOL or header["raw_v3_status"] != "CUSTOM_PROTOCOL_NOT_RAW_V3":
        raise RuntimeError("custom protocol/source authority differs")
    return state_guard.MujocoStateContract(
        Path(header["guard_headers"]["mjxmacro.h"]).read_bytes(),
        Path(header["guard_headers"]["mjdata.h"]).read_bytes(),
        header["guard_binding_sha256"],
        header["environment"]["mujoco_version"],
    )


def runtime_preflight(header, loader=importlib.import_module):
    """Import and verify actual runtime provenance; never instantiate a model or data."""
    runtime = loader("mujoco")
    environment = header.get("environment", {})
    if (
        runtime.__version__ != state_guard.VERSION
        or runtime.__version__ != environment.get("mujoco_version")
        or np.__version__ != environment.get("numpy_version")
    ):
        raise RuntimeError("actual imported MuJoCo/NumPy version differs from frozen contract")
    module_origin = Path(getattr(runtime, "__file__", "")).resolve(strict=True)
    module_expected = environment["files"].get("mujoco/__init__.py")
    if (
        module_expected is None
        or module_origin != Path(module_expected["path"]).resolve(strict=True)
        or getattr(runtime.__spec__, "origin", None) != str(module_origin)
        or digest(module_origin.read_bytes()) != module_expected["sha256"]
    ):
        raise RuntimeError("actual public module origin/bytes differ")
    origins = {}
    for name in ("_structs", "_functions", "_enums"):
        module = loader("mujoco." + name)
        origin = Path(module.__file__).resolve(strict=True)
        expected = environment["files"].get("mujoco/" + origin.name)
        if (
            expected is None
            or origin != Path(expected["path"]).resolve(strict=True)
            or digest(origin.read_bytes()) != expected["sha256"]
            or module.__spec__.origin != str(origin)
        ):
            raise RuntimeError("actual imported binding origin/bytes differ: " + name)
        origins[name] = {"path": str(origin), "sha256": expected["sha256"]}
    structs = loader("mujoco._structs")
    classes = {}
    for name in ("MjModel", "MjData"):
        public, bound = getattr(runtime, name), getattr(structs, name)
        if (
            public is not bound
            or public.__module__ != "mujoco._structs"
            or public.__name__ != name
            or not isinstance(public, type)
        ):
            raise RuntimeError("actual public/binding class identity differs: " + name)
        classes[name] = {
            "module": public.__module__,
            "name": public.__name__,
            "public_binding_identity": True,
        }
    if origins["_structs"]["sha256"] != header["guard_binding_sha256"]:
        raise RuntimeError("actual structs binding differs from guard contract")
    contract = state_guard.MujocoStateContract(
        Path(header["guard_headers"]["mjxmacro.h"]).read_bytes(),
        Path(header["guard_headers"]["mjdata.h"]).read_bytes(),
        origins["_structs"]["sha256"],
        runtime.__version__,
    )
    return {
        "scope": "ACTUAL_MODULE_IMPORT_ONLY_BEFORE_FIRST_MODEL_RESET_CAMERA",
        "actual_mujoco_version": runtime.__version__,
        "actual_numpy_version": np.__version__,
        "classes": classes,
        "public_module_origin": {"path": str(module_origin), "sha256": module_expected["sha256"]},
        "binding_origins": origins,
        "contract_digest": contract.digest,
        "models_or_data_instantiated": 0,
        "source_authenticity": "UNKNOWN",
    }


def protocol_path(directory=None):
    directory = (HERE / "fix-round-1" if directory is None else Path(directory)).resolve(
        strict=True
    )
    if directory == HERE.resolve():
        raise RuntimeError("initial V3 protocol directory is immutable; use reviewed fix-round-1")
    return directory


def prepare(protocol_directory=None):
    frozen = protocol_path(protocol_directory)
    scene, config = specification()
    previous = HERE.parent / "t7b-continuous-visibility"
    inherited = json.loads((previous / "execution-source-hashes.json").read_text())
    inherited_archives = json.loads(
        (HERE.parent / "capture-state-diagnosis/execution-archive-index.json").read_text()
    )
    excluded = {
        str((previous / name).relative_to(ROOT)) for name in ("run_once.py", "verify_offline.py")
    }
    excluded.add("tests/test_step_rgbd.py")
    own = {str((HERE / name).relative_to(ROOT)) for name in ("run_once.py", "verify_offline.py")}
    guard_source = "src/cloud_edge_robot_arm/research/mujoco_state_guard.py"
    guard_fix = HERE.parent / "capture-state-guard/fix-round-1"
    guard_pin = json.loads((guard_fix / "source-hashes.json").read_text())[guard_source]
    if digest((ROOT / guard_source).read_bytes()) != guard_pin["sha256"]:
        raise RuntimeError("reviewed guard source changed")
    source_names = (set(inherited) - excluded) | own | {guard_source}
    archive = frozen / "source-final"
    archive.mkdir()
    sources, indices = {}, {}
    for name in sorted(source_names):
        data = (ROOT / name).read_bytes()
        value = digest(data)
        sources[name] = value
        if name in own:
            dest = archive / Path(name).name
            dest.write_bytes(data)
            indices[name] = {
                "sha256": value,
                "bytes": len(data),
                "archive": str(dest.relative_to(HERE.parent)),
            }
        elif name == guard_source:
            indices[name] = {
                "sha256": value,
                "bytes": len(data),
                "archive": "capture-state-guard/fix-round-1/source-final/mujoco_state_guard.py",
            }
        else:
            if value != inherited[name]:
                raise RuntimeError("fixed necessary source changed: " + name)
            indices[name] = inherited_archives[name]
    write_new(frozen / "execution-source-hashes.json", sources)
    write_new(frozen / "execution-archive-index.json", indices)
    environment = json.loads((HERE.parent / "capture-state-diagnosis/header.json").read_text())[
        "environment"
    ]
    helper = ROOT / ".venv/lib/python3.12/site-packages/numpy/lib/_format_impl.py"
    environment["files"]["numpy/lib/_format_impl.py"] = {
        "path": str(helper),
        "sha256": digest(helper.read_bytes()),
    }
    package_file = ROOT / ".venv/lib/python3.12/site-packages/mujoco/__init__.py"
    environment["files"]["mujoco/__init__.py"] = {
        "path": str(package_file),
        "sha256": digest(package_file.read_bytes()),
    }
    headers = ROOT / ".venv/lib/python3.12/site-packages/mujoco/include/mujoco"
    header = {
        "protocol": PROTOCOL,
        "fix_round": 1,
        "initial_v3_header_sha256": digest((HERE / "header.json").read_bytes()),
        "scope": "EXCLUDED_SAME_COMPONENT_CUSTOM_WHOLE_STEP_RGBD",
        "attempt_limit": 1,
        "component": "t7b-continuous-visibility",
        "independent_calibration_group": False,
        "old_attempt_retried": False,
        "scene": scene.model_dump(mode="json"),
        "config": config.model_dump(mode="json"),
        "scene_hash": scene.scene_hash,
        "asset_sha256": ASSET_HASH,
        "settle_steps": 120,
        "planned_teacher_actions": 9,
        "capture_policy": "STEP_ZERO_AND_EVERY_REAL_PHYSICS_END",
        "original_max_sample_gap_s": CompletionCriteria("object", "target_region").max_sample_gap_s,
        "guard_protocol": GUARD_PROTOCOL,
        "guard_binding_sha256": state_guard.BINDING_SHA256,
        "guard_headers": {name: str(headers / name) for name in ("mjxmacro.h", "mjdata.h")},
        "guard_core_sha256": guard_pin["sha256"],
        "environment": environment,
        "source_manifest_sha256": digest((frozen / "execution-source-hashes.json").read_bytes()),
        "source_archive_index_sha256": digest(
            (frozen / "execution-archive-index.json").read_bytes()
        ),
        "source_count": len(sources),
        "source_bytes": sum((ROOT / name).stat().st_size for name in sources),
        "source_root": str(ROOT),
        "archive_root": str(HERE.parent),
        "raw_v3_status": "CUSTOM_PROTOCOL_NOT_RAW_V3",
        "source_authenticity": "UNKNOWN",
        "decoder_scope": "POST_TERMINAL_SAVED_RGBD_AND_REGISTERED_MARKER_ONLY",
        "teacher_truth_scope": "OFFLINE_TARGETS_AND_INDEPENDENT_SCORER_ONLY",
        "formal_accepted": False,
        "native_admission": "NOT_PROMOTED",
        "continuous_motion": "NOT_CERTIFIED",
        "future_stability": "UNAVAILABLE",
    }
    write_new(frozen / "header.json", header)
    source_preflight(header, frozen)
    print(
        json.dumps(
            {
                "status": "PREPARED_NO_ACTUAL_CALLS",
                "source_count": len(sources),
                "source_bytes": header["source_bytes"],
                "group_id": scene.group_id,
            }
        )
    )


def execute_once(protocol_directory=None):
    frozen = protocol_path(protocol_directory)
    header = json.loads((frozen / "header.json").read_text())
    state_contract = source_preflight(header, frozen)
    runtime_provenance = runtime_preflight(header)
    scene, config = specification()
    if (
        scene.model_dump(mode="json") != header["scene"]
        or config.model_dump(mode="json") != header["config"]
    ):
        raise RuntimeError("prepared scene/config changed")
    directory = frozen / "attempt-1"
    directory.mkdir()  # No replay, resume, overwrite, or second attempt.
    header_bytes = (frozen / "header.json").read_bytes()
    (directory / "execution-header.json").write_bytes(header_bytes)
    write_new(directory / "runtime-preflight.json", runtime_provenance)
    journal = NominalJournal(directory / "nominal-journal.jsonl.gz")
    recorder = teacher.EpisodeRecorder()
    series = tracker = adapter = coordinator = None
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
        journal.emit(
            "SETUP_BEGIN",
            scope="OFFLINE_SCENE_APPLICATION_NOT_OBSERVED_RESET",
            runtime_preflight=runtime_provenance,
        )
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
                setup_state=capture_state(backend, state_contract),
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
                    adapter = CaptureAdapter(backend, journal, state_contract)
                    tracker = ActionTracker(backend, journal)
                    series = StepRGBDRecorder(
                        directory / "whole-step",
                        adapter,
                        episode_id=backend._episode_id,
                        max_sample_gap_s=header["original_max_sample_gap_s"],
                    )

                    coordinator = AcquisitionCoordinator(backend, journal, series, tracker, adapter)

                    def physical(snapshot):
                        coordinator.record(snapshot)
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
            "protocol": PROTOCOL,
            "component": "t7b-continuous-visibility",
            "independent_calibration_group": False,
            "source_authenticity": "UNKNOWN",
            "execution_header_sha256": digest(header_bytes),
            "acquisition_allocated": coordinator.allocated if coordinator else 0,
            "acquisition_completed": coordinator.completed if coordinator else 0,
            "acquisition_failed": coordinator.failed if coordinator else 0,
            "acquisition_failure_journal_errors": coordinator.failure_journal_errors
            if coordinator
            else [],
            "group_id": scene.group_id,
            "scene_hash": scene.scene_hash,
            "run_status": "PARTIAL_OR_FAILED" if failure else "COMPLETED_SINGLE_ATTEMPT",
            "wall_elapsed_s": (time.monotonic_ns() - started) / 1e9,
            "counts": counts,
            "whole_step_capture_calls": adapter.calls if adapter else 0,
            "action_begins": tracker.begins if tracker else 0,
            "action_ends": tracker.ends if tracker else 0,
            "action_failed": tracker.failed if tracker else 0,
            "action_delegated": tracker.delegated if tracker else 0,
            "action_failure_journal_errors": tracker.failure_journal_errors if tracker else [],
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
    parser.add_argument(
        "--protocol-directory",
        type=Path,
        required=True,
        help="Reviewed new fix-round-1 metadata/raw directory; initial V3 is immutable",
    )
    args = parser.parse_args()
    prepare(args.protocol_directory) if args.prepare else execute_once(args.protocol_directory)
