"""One passive ten-step diagnosis, separate from the failed teacher attempt.

No original input or guard is changed. --prepare is CPU/read-only; the root alone
may authorize --execute-once after independent review of the frozen sources.
"""

from __future__ import annotations

import argparse
import base64
import copy
import gzip
import hashlib
import importlib.metadata
import importlib.util
import json
import time
import traceback
from contextlib import contextmanager
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
PRIOR = HERE.parent / "t7b-continuous-visibility"
ABSENT = object()
PHYSICAL_STEPS = 10
MAX_SNAPSHOT_BYTES = 32 * 1024 * 1024
MAX_STORED_BYTES = 256 * 1024 * 1024


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def load_prior():
    spec = importlib.util.spec_from_file_location(
        "ced_frozen_capture_reference", PRIOR / "run_once.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("frozen reference unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def json_bytes(value):
    return json.dumps(value, sort_keys=True, allow_nan=False).encode()


def write_new(path, value):
    with path.open("x") as stream:
        stream.write(json.dumps(value, indent=2, allow_nan=False) + "\n")


def copy_arrays(value, *, topology=None):
    """Exactly one attribute read, followed immediately by a real C-order copy."""
    result, views = {}, {}
    for name in sorted(dir(value)):
        if name.startswith("_"):
            continue
        member = getattr(value, name)
        if isinstance(member, np.ndarray):
            if member.dtype.hasobject:
                raise RuntimeError("object array cannot provide numeric original bytes: " + name)
            result[name] = np.array(member, copy=True, order="C", subok=False)
            if topology is not None:
                views[name] = member
                topology[name] = {
                    "data_address": int(member.__array_interface__["data"][0]),
                    "strides": list(member.strides),
                    "owns_data": bool(member.flags.owndata),
                    "base_type": type(member.base).__module__
                    + "."
                    + type(member.base).__qualname__,
                    "shares_memory_with": [],
                }
    for index, name in enumerate(views):
        for other in list(views)[index + 1 :]:
            if np.shares_memory(views[name], views[other]):
                topology[name]["shares_memory_with"].append(other)
                topology[other]["shares_memory_with"].append(name)
    return result


def describe_arrays(arrays):
    members, aggregate = {}, hashlib.sha256()
    for name in sorted(arrays):
        array = arrays[name]
        raw = array.tobytes(order="C")
        shape = list(array.shape)
        aggregate.update(json_bytes((name, shape, array.dtype.str)))
        aggregate.update(raw)
        members[name] = {
            "shape": shape,
            "dtype": array.dtype.str,
            "dtype_descr": array.dtype.descr,
            "bytes": len(raw),
            "sha256": digest(raw),
        }
    return {"aggregate_sha256": aggregate.hexdigest(), "members": members}


def changed_members(before, after):
    left, right = before["members"], after["members"]
    return sorted(name for name in left.keys() | right.keys() if left.get(name) != right.get(name))


def copy_contract(live, detached):
    """Prove bytes/shapes/dtypes and no shared memory for every exposed array."""
    original_views, detached_views = {}, {}
    for value, target in ((live, original_views), (detached, detached_views)):
        for name in sorted(dir(value)):
            if not name.startswith("_"):
                member = getattr(value, name)
                if isinstance(member, np.ndarray):
                    target[name] = member
    if original_views.keys() != detached_views.keys():
        raise RuntimeError("detached data array inventory differs")
    for name in original_views:
        original, replica = original_views[name], detached_views[name]
        if (
            original.shape != replica.shape
            or original.dtype != replica.dtype
            or original.tobytes(order="C") != replica.tobytes(order="C")
        ):
            raise RuntimeError("detached data array bytes differ: " + name)
        for original_name, other in original_views.items():
            if np.shares_memory(replica, other):
                raise RuntimeError(
                    "detached data shares live memory: " + name + "/" + original_name
                )
    if float(live.time) != float(detached.time):
        raise RuntimeError("detached data time differs")
    return {"array_count": len(original_views), "all_bytes_equal": True, "no_shared_memory": True}


class SnapshotStore:
    def __init__(self, directory, reference):
        self.directory, self.reference = directory, reference
        self.ordinal, self.stored_bytes = 0, 0
        directory.mkdir()

    def state(self, backend, data=None):
        data = backend._data if data is None else data
        topology = {}
        arrays = copy_arrays(data, topology=topology)
        model = describe_arrays(copy_arrays(backend._model))
        described = describe_arrays(arrays)
        if sum(array.nbytes for array in arrays.values()) > MAX_SNAPSHOT_BYTES:
            raise RuntimeError("snapshot budget exceeded; no fields dropped")
        reference = self.reference
        model_scalars = {
            name: reference.scalar_struct(getattr(backend._model, name))
            for name in ("opt", "stat", "vis")
            if hasattr(backend._model, name)
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
        state = {
            "data_arrays_sha256": described["aggregate_sha256"],
            "sim_time_s": float(data.time),
            "model_arrays_sha256": model["aggregate_sha256"],
            "model_options_sha256": digest(reference.json_bytes(model_scalars)),
            "controller_state_sha256": digest(reference.json_bytes(controls)),
            "rng_state_sha256": digest(reference.json_bytes(backend._rng.bit_generator.state)),
            "sensor_cache_object_id": id(backend._sensor_frame),
            "camera_object_id": id(backend._camera),
            "physical_step": backend.total_physics_steps,
            "command_count": len(backend.command_records),
            "sensor_noise_std_m": backend._sensor_noise_std_m,
            "physics_state_sha256": reference.MuJoCoRGBDCamera._physics_state_hash(data),
        }
        return {
            "state": state,
            "data_arrays": described,
            "model_arrays": model,
            "data_array_topology": topology,
        }, arrays

    def save(self, backend, phase, data=None):
        started = time.monotonic_ns()
        snapshot, arrays = self.state(backend, data)
        payload = {
            "phase": phase,
            **snapshot,
            "array_bytes_base64": {
                name: base64.b64encode(array.tobytes(order="C")).decode()
                for name, array in arrays.items()
            },
        }
        saved = self.persist(json_bytes(payload), "snapshot")
        return {
            **snapshot,
            "phase": phase,
            "saved": saved,
            "monotonic_begin_ns": started,
            "monotonic_end_ns": time.monotonic_ns(),
        }

    def persist(self, raw, role):
        zipped = gzip.compress(raw, compresslevel=1, mtime=0)
        if self.stored_bytes + len(zipped) > MAX_STORED_BYTES:
            raise RuntimeError("storage budget exceeded; no overwrite or dropped fields")
        self.ordinal += 1
        name = f"{self.ordinal:04d}-{role}.gz"
        with (self.directory / name).open("xb") as stream:
            stream.write(zipped)
        self.stored_bytes += len(zipped)
        return {
            "file": "snapshots/" + name,
            "original_sha256": digest(raw),
            "compressed_sha256": digest(zipped),
            "original_bytes": len(raw),
            "compressed_bytes": len(zipped),
        }


@contextmanager
def renderer_phases(renderer, before, after):
    """Delegate each original bound method exactly once; restore even on failure."""
    originals = {name: getattr(renderer, name) for name in ("update_scene", "render")}
    saved = {name: renderer.__dict__.get(name, ABSENT) for name in originals}
    counts = {name: 0 for name in originals}
    try:
        for name, original in originals.items():

            def wrapped(*args, _name=name, _original=original, **kwargs):
                counts[_name] += 1
                ordinal = counts[_name]
                token = before(_name, ordinal)
                value = error = None
                try:
                    value = _original(*args, **kwargs)
                    return value
                except BaseException as exception:
                    error = exception
                    raise
                finally:
                    try:
                        after(_name, ordinal, token, value, error)
                    except BaseException as diagnostic_error:
                        if error is not None:
                            error.add_note(
                                "after-phase diagnostic failed: " + repr(diagnostic_error)
                            )
                        else:
                            raise

            setattr(renderer, name, wrapped)
        yield counts
    finally:
        for name, value in saved.items():
            if value is ABSENT:
                renderer.__dict__.pop(name, None)
            else:
                setattr(renderer, name, value)


def passive_horizon(backend, callback):
    """The sole existing backend executor performs one bulk ten-step call."""
    if backend.total_physics_steps != 0 or backend.command_records:
        raise RuntimeError("diagnosis must start at step zero without commands")
    snapshot = backend.current_physics_observation()
    backend._in_observer_callback = True
    try:
        callback(snapshot)
    finally:
        backend._in_observer_callback = False
    with backend.observe_physics_steps(callback):
        backend.step(steps=PHYSICAL_STEPS)
    if backend.total_physics_steps != PHYSICAL_STEPS or backend.command_records:
        raise RuntimeError("passive horizon/zero-command invariant failed")


class CaptureProbe:
    def __init__(self, backend, reference, store, journal, directory):
        self.backend, self.reference = backend, reference
        self.store, self.journal, self.directory = store, journal, directory
        self.camera = backend._camera
        self.calls = self.completed = self.failed = self.state_differences = 0
        self.camera_calls_started = 0
        self.failure_journal_errors = []

    def snapshot(self, phase, data):
        value = self.store.save(self.backend, phase, data)
        self.journal.emit("DATA_SNAPSHOT", capture_ordinal=self.calls, snapshot=value)
        return value

    def capture(self, data=None, *, detached=False):
        backend = self.backend
        data = backend._data if data is None else data
        self.journal.ensure(backend)
        if backend._camera is not self.camera or backend._sensor_noise_std_m != 0.0:
            raise RuntimeError("same-camera/zero-noise invariant failed")
        self.calls += 1
        started = time.monotonic_ns()
        error = before = after = None
        camera_call_started = False
        phases, renderer_counts = [], {}
        try:
            self.journal.emit(
                "CAPTURE_BEGIN",
                capture_ordinal=self.calls,
                detached=detached,
                episode_id=backend._episode_id,
                physics_step=backend.total_physics_steps,
                sim_time_s=float(data.time),
            )
            before = self.snapshot("CAPTURE_BEFORE", data)
            legacy_first = self.reference.array_state(data)
            legacy_repeat = self.reference.array_state(data)
            repeated = self.snapshot("BEFORE_REPEAT", data)
            self.journal.emit(
                "REPEATED_BEFORE",
                capture_ordinal=self.calls,
                legacy_first_sha256=legacy_first,
                legacy_repeat_sha256=legacy_repeat,
                copied_before_sha256=before["state"]["data_arrays_sha256"],
                copied_repeat_sha256=repeated["state"]["data_arrays_sha256"],
                changed_members=changed_members(before["data_arrays"], repeated["data_arrays"]),
            )

            def phase_before(name, ordinal):
                token = self.snapshot(f"{name}:{ordinal}:BEFORE", data)
                if detached:
                    token["live_state_before"] = self.store.state(backend)[0]
                return token

            def phase_after(name, ordinal, token, value, exception):
                ending = self.snapshot(f"{name}:{ordinal}:AFTER", data)
                render_payload = None
                if isinstance(value, np.ndarray):
                    original = np.array(value, copy=True, order="C", subok=False)
                    render_payload = {
                        **self.store.persist(original.tobytes(order="C"), f"render-{ordinal}"),
                        "shape": list(original.shape),
                        "dtype": original.dtype.str,
                    }
                row = {
                    "method": name,
                    "ordinal": ordinal,
                    "before_snapshot": token["saved"],
                    "after_snapshot": ending["saved"],
                    "before_state": token["state"],
                    "after_state": ending["state"],
                    "changed_members": changed_members(token["data_arrays"], ending["data_arrays"]),
                    "render_payload": render_payload,
                    "error_type": type(exception).__name__ if exception else None,
                    "error": str(exception) if exception else None,
                }
                if detached:
                    live_after = self.store.state(backend)[0]
                    row["live_state_before"] = token["live_state_before"]
                    row["live_state_after"] = live_after
                    if live_after != token["live_state_before"]:
                        raise RuntimeError("detached render altered original live state")
                phases.append(row)
                self.journal.emit(
                    "RENDER_PHASE", capture_ordinal=self.calls, detached=detached, **row
                )

            with renderer_phases(
                self.camera._renderer, phase_before, phase_after
            ) as renderer_counts:
                self.camera_calls_started += 1
                camera_call_started = True
                frame, ids, labels, hashes = self.camera._capture(
                    data,
                    rng=backend._rng,
                    noise_std_m=0.0,
                    scene_id=backend._scenario.scenario_id,
                    episode_id=backend._episode_id,
                    include_instances=False,
                )
            if renderer_counts != {"update_scene": 1, "render": 2}:
                raise RuntimeError("original registered two-pass delegation count differs")
            if ids or labels or len(hashes) != 2 or hashes[0] != hashes[1]:
                raise RuntimeError("truth-free registered passes failed")
            after = self.snapshot("CAPTURE_AFTER", data)
            changed = changed_members(before["data_arrays"], after["data_arrays"])
            if before["state"] != after["state"]:
                self.state_differences += 1
            # Array changes remain unresolved findings, never accepted stability.
            # The original whole-step guard and failed attempt stay unchanged.
            protected = set(before["state"]) - {"data_arrays_sha256"}
            if any(before["state"][key] != after["state"][key] for key in protected):
                raise RuntimeError("protected physics/model/controller/RNG/cache state changed")
            observation = self.reference.observation_from_sensor_frame(
                frame, source="mujoco_camera"
            )
            saved = self.reference.save_observation_gzip(
                self.directory / f"capture-{self.calls:02d}.json.gz", observation
            )
            self.journal.emit(
                "CAPTURE_END",
                capture_ordinal=self.calls,
                detached=detached,
                episode_id=backend._episode_id,
                physics_step=backend.total_physics_steps,
                sim_time_s=float(data.time),
                before_state=before["state"],
                after_state=after["state"],
                changed_members=changed,
                pass_state_hashes=hashes,
                saved=saved,
                renderer_counts=renderer_counts,
                monotonic_begin_ns=started,
                monotonic_end_ns=time.monotonic_ns(),
                sensor_latency_ms=frame.latency_ms,
                original_whole_step_guard_would_accept=before["state"] == after["state"],
                camera_call_started=camera_call_started,
            )
            self.completed += 1
        except BaseException as exception:
            self.failed += 1
            error = exception
            raise
        finally:
            if error is not None:
                try:
                    self.journal.emit(
                        "CAPTURE_FAILED",
                        capture_ordinal=self.calls,
                        detached=detached,
                        error_type=type(error).__name__,
                        error=str(error),
                        before_state=before["state"] if before else None,
                        after_state=after["state"] if after else None,
                        renderer_counts=renderer_counts,
                        phase_count=len(phases),
                        camera_call_started=camera_call_started,
                        monotonic_begin_ns=started,
                        monotonic_end_ns=time.monotonic_ns(),
                    )
                except BaseException as journal_error:
                    note = "CAPTURE_FAILED journal publication failed: " + repr(journal_error)
                    self.failure_journal_errors.append(note)
                    error.add_note(note)


def environment_pins():
    distribution = importlib.metadata.distribution("mujoco")
    if distribution.version != "3.3.7":
        raise RuntimeError("diagnosis requires the original MuJoCo 3.3.7")
    names = [
        str(item)
        for item in distribution.files or ()
        if str(item).startswith("mujoco/")
        and (
            str(item).endswith(".so")
            or "libmujoco.so" in str(item)
            or str(item)
            in {
                "mujoco/renderer.py",
                "mujoco/include/mujoco/mjdata.h",
                "mujoco/include/mujoco/mjxmacro.h",
                "mujoco/include/mujoco/mujoco.h",
            }
        )
    ]
    return {
        "mujoco_version": distribution.version,
        "numpy_version": np.__version__,
        "files": {
            name: {
                "path": str(distribution.locate_file(name)),
                "sha256": digest(distribution.locate_file(name).read_bytes()),
            }
            for name in sorted(names)
        },
    }


def prepare():
    original = json.loads((PRIOR / "fix-round-1/execution-source-hashes.json").read_text())
    archives = json.loads((PRIOR / "fix-round-1/execution-archive-index.json").read_text())
    sources = dict(original)
    new_name = str((HERE / "run_once.py").relative_to(ROOT))
    sources[new_name] = digest((HERE / "run_once.py").read_bytes())
    index = {}
    for name, expected in original.items():
        source = ROOT / name
        archived = PRIOR / archives[name]["archive"]
        if digest(source.read_bytes()) != expected or digest(archived.read_bytes()) != expected:
            raise RuntimeError("original frozen source changed: " + name)
        index[name] = {
            "sha256": expected,
            "bytes": source.stat().st_size,
            "archive": str(archived.relative_to(HERE.parent)),
        }
    snapshot = HERE / "source-final"
    snapshot.mkdir()
    (snapshot / "run_once.py").write_bytes((HERE / "run_once.py").read_bytes())
    index[new_name] = {
        "sha256": sources[new_name],
        "bytes": (HERE / "run_once.py").stat().st_size,
        "archive": "capture-state-diagnosis/source-final/run_once.py",
    }
    reference = load_prior()
    scene, config = reference.specification()
    write_new(HERE / "execution-source-hashes.json", sources)
    write_new(HERE / "execution-archive-index.json", index)
    write_new(
        HERE / "header.json",
        {
            "scope": "EXCLUDED_SAME_COMPONENT_PASSIVE_CAPTURE_STATE_DIAGNOSIS",
            "status": "PREPARED_NO_ACTUAL_CALLS",
            "attempt_limit": 1,
            "component": "t7b-continuous-visibility",
            "independent_calibration_group": False,
            "original_attempt": "t7b-continuous-visibility/attempt-1",
            "original_attempt_retried": False,
            "scene": scene.model_dump(mode="json"),
            "config": config.model_dump(mode="json"),
            "scene_hash": scene.scene_hash,
            "group_id": scene.group_id,
            "passive_physics_steps": PHYSICAL_STEPS,
            "teacher_actions": 0,
            "motion_commands": 0,
            "live_extra_capture_steps": list(range(PHYSICAL_STEPS + 1)),
            "detached_terminal_capture_limit": 1,
            "detached_copy_api": "copy.copy(MjData)",
            "source_count": len(sources),
            "source_bytes": sum(entry["bytes"] for entry in index.values()),
            "source_manifest_sha256": digest((HERE / "execution-source-hashes.json").read_bytes()),
            "source_archive_index_sha256": digest(
                (HERE / "execution-archive-index.json").read_bytes()
            ),
            "inherited_32_reference_manifest_sha256": digest(
                (PRIOR / "fix-round-1/execution-source-hashes.json").read_bytes()
            ),
            "environment": environment_pins(),
            "cpu_test_sha256": digest((HERE / "test_cpu.py").read_bytes()),
            "max_snapshot_bytes": MAX_SNAPSHOT_BYTES,
            "max_snapshot_storage_bytes": MAX_STORED_BYTES,
            "decoder_calls": 0,
            "formal_accepted": False,
            "native_admission": "NOT_PROMOTED",
            "continuous_motion": "NOT_CERTIFIED",
            "future_stability": "UNAVAILABLE",
        },
    )
    print(json.dumps({"status": "PREPARED_NO_ACTUAL_CALLS", "source_count": len(sources)}))


def verify_inputs(header):
    manifest, index = HERE / "execution-source-hashes.json", HERE / "execution-archive-index.json"
    if digest(manifest.read_bytes()) != header["source_manifest_sha256"]:
        raise RuntimeError("diagnostic source manifest changed")
    if digest(index.read_bytes()) != header["source_archive_index_sha256"]:
        raise RuntimeError("diagnostic source archive index changed")
    sources, archives = json.loads(manifest.read_text()), json.loads(index.read_text())
    for name, expected in sources.items():
        if (
            digest((ROOT / name).read_bytes()) != expected
            or digest((HERE.parent / archives[name]["archive"]).read_bytes()) != expected
        ):
            raise RuntimeError("frozen diagnostic source changed: " + name)
    if environment_pins() != header["environment"]:
        raise RuntimeError("diagnostic dependency bytes changed")


def terminal_copy_probe(backend, probe, store, journal, counts):
    """One copy gate; a rejected copy produces no clone capture or fallback."""
    live_before = store.save(backend, "COPY_LIVE_BEFORE")
    counts["terminal_copy_attempts"] += 1
    detached = contract = rejection = None
    try:
        detached = copy.copy(backend._data)
        contract = copy_contract(backend._data, detached)
    except Exception as error:
        rejection = {"error_type": type(error).__name__, "error": str(error)}
    live_after_copy = store.save(backend, "COPY_LIVE_AFTER")
    if live_before["state"] != live_after_copy["state"]:
        raise RuntimeError("copy.copy changed original live state")
    if rejection is not None:
        counts["terminal_copy_rejected"] += 1
        journal.emit(
            "DETACHED_COPY_REJECTED",
            **rejection,
            before=live_before,
            after=live_after_copy,
            clone_capture_calls=0,
            retry=False,
        )
        return
    journal.emit(
        "DETACHED_COPY_VALIDATED", contract=contract, before=live_before, after=live_after_copy
    )
    counts["terminal_clone_capture_calls"] += 1
    probe.capture(detached, detached=True)
    live_final = store.save(backend, "COPY_LIVE_AFTER_CAPTURE")
    if live_before["state"] != live_final["state"]:
        raise RuntimeError("detached capture changed original live state")
    journal.emit(
        "DETACHED_CAPTURE_END", original_live_unchanged=True, before=live_before, after=live_final
    )


def execute_once():
    header = json.loads((HERE / "header.json").read_text())
    verify_inputs(header)
    reference = load_prior()
    scene, config = reference.specification()
    if (
        scene.model_dump(mode="json") != header["scene"]
        or config.model_dump(mode="json") != header["config"]
    ):
        raise RuntimeError("frozen diagnostic scene/config differs")
    directory = HERE / "diagnostic-1"
    directory.mkdir()  # No overwrite/resume/retry of this diagnostic or the old attempt.
    journal = reference.NominalJournal(directory / "journal.jsonl.gz")
    store = SnapshotStore(directory / "snapshots", reference)
    probe = backend = None
    failure = None
    counts = {
        "setup_capture_calls": 0,
        "bootstrap_capture_calls": 0,
        "cached_updates_suppressed": 0,
        "terminal_copy_attempts": 0,
        "terminal_copy_rejected": 0,
        "terminal_clone_capture_calls": 0,
    }
    original_capture = reference.MuJoCoRGBDCamera.capture
    setup_frames = []
    started = time.monotonic_ns()

    def counted_setup(camera, *args, **kwargs):
        counts["setup_capture_calls"] += 1
        value = original_capture(camera, *args, **kwargs)
        setup_frames.append(value)
        return value

    reference.MuJoCoRGBDCamera.capture = counted_setup
    try:
        journal.emit("SETUP_BEGIN", original_attempt_retried=False)
        with reference.MuJoCoCaptureSession(config) as session:
            session.apply_scene(scene)
            backend = session._backend
            if backend._sensor_noise_std_m != 0.0:
                raise RuntimeError("same original scene must apply exact zero noise")
            if counts["setup_capture_calls"] != 1:
                raise RuntimeError("original single setup capture count differs")
            journal.emit(
                "SETUP_END",
                episode_id=backend._episode_id,
                physics_step=backend.total_physics_steps,
                sim_time_s=backend.get_sim_time(),
            )
            original_update = backend._update_sensor_frame

            def suppress_cached_render():
                counts["cached_updates_suppressed"] += 1

            backend._update_sensor_frame = suppress_cached_render
            try:
                with backend.observe_operation_boundaries(journal.operation):
                    counts["bootstrap_capture_calls"] += 1
                    frame, _, _, hashes = backend.capture_sensor_frame_with_instances()
                    if len(hashes) != 3 or len(set(hashes)) != 1:
                        raise RuntimeError("same original bootstrap state mismatch")
                    bootstrap = reference.observation_from_sensor_frame(
                        frame, source="mujoco_camera"
                    )
                    journal.emit(
                        "BOOTSTRAP_SAVED",
                        pass_state_hashes=hashes,
                        saved=reference.save_observation_gzip(
                            directory / "bootstrap.json.gz", bootstrap
                        ),
                    )
                    probe = CaptureProbe(backend, reference, store, journal, directory)

                    def physical(snapshot):
                        journal.emit(
                            "PHYSICAL_SOURCE",
                            source=snapshot,
                            control_operation_id=journal.last_control,
                            physics_operation_id=journal.last_physics,
                        )
                        probe.capture()

                    with backend.observe_actuator_steps(
                        lambda value: journal.emit("ACTUATOR", source=value)
                    ):
                        passive_horizon(backend, physical)
                    if probe.calls != PHYSICAL_STEPS + 1:
                        raise RuntimeError("eleven live extra captures not completed")
                    terminal_copy_probe(backend, probe, store, journal, counts)
                    journal.ensure(backend)
            finally:
                backend._update_sensor_frame = original_update
                write_new(
                    directory / "terminal.json",
                    {
                        "episode_id": backend._episode_id,
                        "physical_step": backend.total_physics_steps,
                        "sim_time_s": backend.get_sim_time(),
                        "commands": reference.plain(backend.command_records),
                        "operation_ledger": reference.plain(backend._operation_ledger),
                        "operation_observer_failures": reference.plain(
                            backend._operation_observer_failures
                        ),
                        "observer_overhead_ns": backend._operation_observer_overhead_ns,
                    },
                )
    except BaseException:
        failure = traceback.format_exc()
    finally:
        reference.MuJoCoRGBDCamera.capture = original_capture
        if failure:
            with (directory / "failure.txt").open("x") as stream:
                stream.write(failure)
        setup_members = []
        for ordinal, frame in enumerate(setup_frames):
            value = reference.observation_from_sensor_frame(frame, source="mujoco_camera")
            setup_members.append(
                reference.save_observation_gzip(directory / f"setup-{ordinal:02d}.json.gz", value)
            )
        write_new(directory / "setup-members.json", setup_members)
        summary = {
            "scope": header["scope"],
            "component": header["component"],
            "independent_calibration_group": False,
            "original_attempt_retried": False,
            "status": "DIAGNOSTIC_PARTIAL_OR_FAILED" if failure else "DIAGNOSTIC_CAPTURE_COMPLETED",
            "classification": "UNRESOLVED_NO_GUARD_RELAXATION",
            "counts": counts,
            "physical_steps": backend.total_physics_steps if backend else 0,
            "captures_started": probe.calls if probe else 0,
            "capture_attempts_allocated": probe.calls if probe else 0,
            "camera_calls_started": probe.camera_calls_started if probe else 0,
            "captures_completed": probe.completed if probe else 0,
            "captures_failed": probe.failed if probe else 0,
            "captures_with_state_differences": probe.state_differences if probe else 0,
            "failure_journal_errors": probe.failure_journal_errors if probe else [],
            "teacher_actions": 0,
            "motion_commands": len(backend.command_records) if backend else 0,
            "decoder_calls": 0,
            "snapshot_files": store.ordinal,
            "snapshot_stored_bytes": store.stored_bytes,
            "wall_elapsed_s": (time.monotonic_ns() - started) / 1e9,
            "formal_accepted": False,
            "native_admission": "NOT_PROMOTED",
            "continuous_motion": "NOT_CERTIFIED",
            "future_stability": "UNAVAILABLE",
        }
        write_new(directory / "summary.json", summary)
        journal.close()
        write_new(
            directory / "files.json",
            {
                str(path.relative_to(directory)): {
                    "sha256": digest(path.read_bytes()),
                    "bytes": path.stat().st_size,
                }
                for path in sorted(directory.rglob("*"))
                if path.is_file()
            },
        )
        print(json.dumps(summary, indent=2), flush=True)
    if failure:
        raise RuntimeError(
            "single passive diagnostic failed; no retry; all saved evidence retained"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--prepare", action="store_true")
    choice.add_argument("--execute-once", action="store_true")
    arguments = parser.parse_args()
    prepare() if arguments.prepare else execute_once()
