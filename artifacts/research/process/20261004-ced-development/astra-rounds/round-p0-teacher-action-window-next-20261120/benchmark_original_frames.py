"""Compare PNG 6/1 on the original 242 frames, without running an experiment."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import resource
import shutil
import statistics
import struct
import sys
import time
from collections import Counter, defaultdict
from contextlib import ExitStack, contextmanager
from copy import deepcopy
from dataclasses import dataclass, fields
from functools import partial, wraps
from hashlib import file_digest
from importlib.metadata import version
from pathlib import Path
from types import SimpleNamespace

import numpy  # noqa: F401 - load the production vectorized RGB-D validation path
from PIL import Image

from cloud_edge_robot_arm.harness.config import strict_json
from cloud_edge_robot_arm.research import native_full_horizon_recorder as native
from cloud_edge_robot_arm.research.native_full_horizon_originals import _Audit, _restore_frame
from cloud_edge_robot_arm.simulation.models import SensorFrame
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
from cloud_edge_robot_arm.simulation.mujoco.camera import MuJoCoRGBDCamera
from cloud_edge_robot_arm.vision import observations
from cloud_edge_robot_arm.vision import raw_recorder_v3 as raw_recorder

ROUND = Path(__file__).resolve().parent
PLAN_SHA = "3c10462457e761865c22c2bec2be231c5513961da8b90cbc535754ceed855eca"
INPUT_STATIC_PLAN_SHA = "519795330d08b9be668a808da25c2e5ae6782b118bee98f973acb4e9f5355aaa"
FROZEN_CHECKPOINT_KEY = "src/cloud_edge_robot_arm/research/native_checkpoint_diagnostic.py"
FROZEN_CHECKPOINT_SHA = "a1c22853004ddddcbc12bdd3c4726d2dc54f7925fe6537d37c6887b5e965073d"
SOURCE_SUFFIX = Path(
    "experiments/results/phase9/p0-first-teacher-20261119/checkpoint-egl-development-20261120"
)
N = 242
MIN_FREE = 6 * 1024**3
MAX_OUTPUT = 4 * 1024**3
MAX_RSS = 2 * 1024**3
PAIRS = ("AB", "BA", "BA", "AB")
LEVEL = {"A": 6, "B": 1}
FRAME_ARTIFACTS = ("rgb.png", "depth.f32", "mask.u8", "instances.i32", "source-frame.json")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha_file(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def verified_file(path, expected):
    require(path.is_file() and path.resolve() == path.absolute(), f"missing original: {path}")
    require(sha_file(path) == expected, f"original hash differs: {path}")
    return path


def require_identity(expected, found):
    require(expected == found, "original frame identity or role differs")


def verify_baseline_bytes(expected, actual):
    require(expected == actual, "baseline level 6 differs from original bytes or payload")


def phase_residual(total, exclusive):
    remainder = total - sum(exclusive.values())
    require(all(value >= 0 for value in exclusive.values()) and remainder >= 0, "phase overlap")
    return remainder


def fresh_output(path):
    path.mkdir(mode=0o700)
    return path


def save(path, value):
    with path.open("x", encoding="utf8") as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
        stream.write("\n")


def read(path):
    return strict_json(path.read_bytes())


def clocks():
    return time.perf_counter_ns(), time.process_time_ns()


def elapsed(start):
    return tuple(stop - begin for stop, begin in zip(clocks(), start, strict=True))


def raw_bytes(frame, name):
    return (frame.folder / name).read_bytes()


@dataclass(slots=True)
class Input:
    aid: str
    folder: Path
    event: SimpleNamespace
    sensor: SensorFrame
    metadata: dict
    layer: str

    @property
    def role(self):
        return self.metadata["capture_source"]["role"]


def prohibit_external_activity():
    attempted = []

    def rejected(*_args, **_kwargs):
        name = "SIMULATION_OR_RENDER_ATTEMPT"
        attempted.append(name)
        raise RuntimeError(name)

    def audit(event, _args):
        if event in {"socket.getaddrinfo", "socket.connect", "socket.sendto", "socket.sendmsg"}:
            attempted.append(event)
            raise RuntimeError("network forbidden in this benchmark")

    sys.addaudithook(audit)
    for name in ("initialize", "reset", "step", "capture_sensor_frame_with_instances"):
        setattr(MuJoCoPhysicsBackend, name, rejected)
    MuJoCoRGBDCamera.__init__ = rejected
    return attempted


def planned_input(work, group, name, expected):
    if group == "inputs_sha256" and name == FROZEN_CHECKPOINT_KEY:
        require(expected == FROZEN_CHECKPOINT_SHA, "unrecognized registered original source hash")
        return verified_file(work / SOURCE_SUFFIX / "source" / name, expected)
    return verified_file(work / name, expected)


def preflight(work):
    plan_file = verified_file(ROUND / "plan.json", PLAN_SHA)
    plan = read(plan_file)
    for group in ("inputs_sha256", "frame_inputs_sha256"):
        for name, value in plan[group].items():
            planned_input(work, group, name, value)
    expect = plan["inputs_sha256"][FROZEN_CHECKPOINT_KEY]
    resolved = planned_input(work, "inputs_sha256", FROZEN_CHECKPOINT_KEY, expect)
    observed = work / FROZEN_CHECKPOINT_KEY
    provenance = {
        "verified_parent_input_counts": {
            group: len(plan[group])
            for group in (
                "inputs_sha256",
                "frame_inputs_sha256",
            )
        },
        "supplement_plan_sha256": INPUT_STATIC_PLAN_SHA,
        "original_key": FROZEN_CHECKPOINT_KEY,
        "parent_expected_sha256": expect,
        "observed_worktree_path": str(observed),
        "observed_worktree_sha256": (
            sha_file(observed) if observed.is_file() and observed.resolve() == observed else None
        ),
        "resolved_frozen_path": str(resolved),
        "resolved_frozen_sha256": sha_file(resolved),
        "git_witnesses": ["1c50c2d712f2eb16b5fb27edf76e7d78b5dabdd3", "902c2702"],
    }
    frozen = work / SOURCE_SUFFIX
    state = read(frozen / "source-freeze.json")
    require(Path(state["source_path"]) == frozen / "source", "source freeze location differs")
    for path, digest in state["source_files_sha256"].items():
        verified_file(frozen / "source" / path, digest)
    for path, digest in state["protected_inputs_sha256"].items():
        verified_file(work / path, digest)
    checks = {}
    actual = read(frozen / "release/run/imported-source-manifest.json")["after"]
    for module in (observations, native, raw_recorder):
        path = Path(module.__file__).resolve()
        require(path == Path(actual[module.__name__]["path"]), "wrong frozen module loaded")
        checks[module.__name__] = {
            "source_path": str(path),
            "sha256": sha_file(path),
        }
        require(
            checks[module.__name__]["sha256"] == actual[module.__name__]["sha256"],
            "current module differs from original import bytes",
        )

    run = frozen / "release/run"
    originals = run / "originals"
    inventory = read(originals / "inventory.json")
    files = inventory["files"]
    require(len(files) == inventory["file_count"] == 1228, "unexpected original inventory")
    require(native.digest(files) == inventory["inventory_sha256"], "inventory fingerprint mismatch")
    for name, receipt in files.items():
        path = verified_file(originals / name, receipt["sha256"])
        require(path.stat().st_size == receipt["bytes"], f"original size differs: {name}")
    require(
        sum(item["bytes"] for item in files.values()) == inventory["original_bytes"],
        "bad original inventory byte total",
    )
    return run, checks, provenance


def load_inputs(run):
    start = clocks()
    originals = run / "originals"
    protocol = read(run.parent / "protocol.json")["recipe"]
    raw = read(originals / "partial-originals.json")
    timing = read(originals / "checkpoint-diagnostic.json")
    audit = _Audit(protocol, {"assignment_id": "native-dev-checkpoint-20261120-0001"}, run)
    audit.raw = raw
    audit.intervals = {row["interval_id"]: row for row in raw["intervals"]}
    audit.states = {row["physics_step"]: row["post_state_payload"] for row in raw["physics"]}
    audit.states[0] = raw["reset"]["physics_state"]
    ids = [f"acquisition-{index}" for index in range(1, N + 1)]
    require(ids == raw["allocated_frames"], "original acquisition order differs")
    require(
        all(join["relation"] == "BEFORE_SUBMIT" for join in raw["joins"]),
        "original acquisition path contains live action-triggered joins",
    )
    operation_map = {row["operation_id"]: row["bracket"] for row in raw["operational_events"]}
    data = []
    for aid in ids:
        observation, metadata, state = audit.frame(aid)
        folder = originals / "frames" / aid
        capture = metadata["capture_source"]
        operation = capture["operation_id"]
        if operation == timing["rejected_checkpoint"]["operation_id"]:
            layer = "IN_FLIGHT_AT_CUTOFF"
        elif operation_map[operation]["upper_ns"] < timing["first_action_started_monotonic_ns"]:
            layer = "SETUP_THROUGH_PRE"
        else:
            bracket = operation_map[operation]
            require(
                timing["first_action_started_monotonic_ns"]
                <= bracket["lower_ns"]
                <= bracket["upper_ns"]
                <= timing["cutoff_monotonic_ns"],
                "unclassified acquisition wall bracket",
            )
            layer = "WITHIN_ACTION_WINDOW"
        with Image.open(folder / "rgb.png") as image:
            require(image.mode == "RGB", "incorrect source image mode")
            pixels = image.tobytes()
        sensor = SensorFrame(
            frame_id=observation.frame_id,
            sim_time_s=observation.sim_time_s,
            width=observation.width,
            height=observation.height,
            rgb=pixels,
            depth=observation.depth_values(),
            intrinsics=tuple(observation.intrinsics),
            camera_to_world=observation.camera_to_world,
            captured_at=observation.captured_at,
            scene_id=observation.scene_id,
            episode_id=observation.episode_id,
            calibration_version=observation.calibration_version,
            valid_mask=observation.valid_mask_bytes(),
        )
        inst = (folder / "instances.i32").read_bytes()
        result = {
            "sensor_frame": {f.name: getattr(sensor, f.name) for f in fields(sensor)},
            "pass_state_hashes": metadata["frame"]["pass_state_hashes"],
        }
        if metadata["instance_ids_present"] is True:
            result["instance_ids"] = struct.unpack(f"<{len(inst) // 4}i", inst)
        if metadata["instance_labels_present"] is True:
            result["instance_labels"] = metadata["instance_labels"]
        event = SimpleNamespace(
            operation_id=operation,
            parameters={
                "camera_state": metadata["frame"]["camera_state_payload"],
                "physics_state": state,
            },
            result=result,
        )
        baseline = observations.observation_from_sensor_frame(
            sensor,
            source="mujoco_camera",
            png_compress_level=6,
        ).model_dump(mode="json")
        verify_baseline_bytes(observation.model_dump(mode="json"), baseline)
        require(
            native.digest(baseline) == metadata["observation_payload_sha256"],
            f"baseline reconstructed payload digest differs: {aid}",
        )
        sample = Input(aid, folder, event, sensor, metadata, layer)
        validate_operation(sample, operation_context(sample))
        data.append(sample)
    require(
        Counter(frame.layer for frame in data)
        == {
            "SETUP_THROUGH_PRE": 124,
            "WITHIN_ACTION_WINDOW": 117,
            "IN_FLIGHT_AT_CUTOFF": 1,
        },
        "original window strata differ",
    )
    return data, elapsed(start)


def recorder_for(path):
    recorder = object.__new__(native.NativeFullHorizonRecorder)
    recorder.directory = fresh_output(path)
    recorder.application = SimpleNamespace(policy={"raw_bytes": MAX_OUTPUT})
    recorder._published = False
    recorder.inventory = {}
    recorder.bytes_written = 0
    recorder._frames = []
    recorder._frame_aux = {}
    recorder._capture_roles = {}
    recorder._last_returned_span = None
    recorder.frame_sources = {}
    return recorder


def operation_context(frame):
    metadata = frame.metadata["frame"]
    return {
        "acquisition_id": frame.aid,
        "row": {"interval_id": metadata["interval_id"]},
        "input_role": metadata["input_role"],
        "action": None,
        "parameters": frame.event.parameters,
    }


def validate_operation(frame, operation):
    metadata = frame.metadata
    source = metadata["frame"]
    capture = metadata["capture_source"]
    require(
        "parameters" in operation and operation["parameters"] is frame.event.parameters,
        "missing original capture parameters",
    )
    parameters = operation["parameters"]
    require_identity(source["camera_state_payload"], parameters["camera_state"])
    physics = parameters["physics_state"]
    require_identity(source["joined_physics_observation_hash"], raw_recorder._digest(physics))
    require_identity(
        (
            source["acquisition_id"],
            source["interval_id"],
            capture["operation_id"],
            capture["physics_step"],
            source["input_role"],
        ),
        (
            operation["acquisition_id"],
            f"operation-{frame.event.operation_id}",
            frame.event.operation_id,
            physics["physics_step"],
            operation["input_role"],
        ),
    )
    require_identity(source["interval_id"], operation["row"]["interval_id"])
    require_identity(
        "ONLINE" if frame.role == "REGISTERED_ACTION_BOUNDARY" else "SOURCE",
        operation["input_role"],
    )
    values = frame.event.result
    require_identity(source["pass_state_hashes"], values["pass_state_hashes"])
    for key in ("instance_ids", "instance_labels"):
        require(type(metadata[f"{key}_present"]) is bool, f"invalid source flag: {key}")
        require_identity(metadata[f"{key}_present"], key in values)
    ids = values.get("instance_ids", ())
    require_identity(
        (metadata["instance_count"], metadata["instances_available"]), (len(ids), bool(ids))
    )
    require_identity(metadata["instance_labels"], values.get("instance_labels", {}))


def record_frame(recorder, frame, encoder):
    # Only reconstruct inputs to the real recorder. Source ownership and event clocks
    # were verified outside the measured path and are never executed in the adapter.
    metadata = frame.metadata["frame"]
    recorder._record_seq = metadata["record_seq"] - 1
    recorder._capture_roles[frame.event.operation_id] = frame.metadata["capture_source"]
    operation = operation_context(frame)
    original = raw_recorder.observation_from_sensor_frame
    raw_recorder.observation_from_sensor_frame = encoder
    try:
        recorder._record_frame(frame.event, operation)
    finally:
        raw_recorder.observation_from_sensor_frame = original
    require("error" not in operation["row"], f"recorder rejected {frame.aid}: {operation['row']}")


def payload_equivalence(before, after):
    permitted = {"rgb_png_base64", "checksum_sha256"}
    require_identity(
        {k: v for k, v in before.items() if k not in permitted},
        {k: v for k, v in after.items() if k not in permitted},
    )


def verified_derived(root, frame, variant):
    output = root / "frames" / frame.aid
    meta = read(output / "source-frame.json")
    if variant == "A":
        for name in FRAME_ARTIFACTS:
            verify_baseline_bytes(raw_bytes(frame, name), (output / name).read_bytes())
    else:
        for name in ("depth.f32", "mask.u8", "instances.i32"):
            require(
                (output / name).read_bytes() == raw_bytes(frame, name), f"candidate changed {name}"
            )
        with Image.open(output / "rgb.png") as png:
            require(
                png.mode == "RGB" and png.tobytes() == frame.sensor.rgb,
                "candidate changed RGB pixels",
            )

    original = _restore_frame(frame.folder.parent.parent, frame.metadata)
    restored = _restore_frame(root, meta)
    payload_equivalence(original["observation_payload"], restored["observation_payload"])
    # Reconcile only fields that derive from the PNG representation and observation checksum.
    expected = deepcopy(frame.metadata)
    expected["frame"]["observation_payload"]["checksum_sha256"] = restored["observation_payload"][
        "checksum_sha256"
    ]
    expected["frame"]["file_hashes"][f"frames/{frame.aid}/rgb.png"] = sha_file(output / "rgb.png")
    expected["encoded_string_sha256"]["rgb_png_base64"] = hashlib.sha256(
        restored["observation_payload"]["rgb_png_base64"].encode(),
    ).hexdigest()
    expected["observation_payload_sha256"] = native.digest(restored["observation_payload"])
    require_identity(expected, meta)
    return {
        "rgb_digest_changed": sha_file(output / "rgb.png") != sha_file(frame.folder / "rgb.png"),
        "observation_checksum_changed": (
            restored["observation_payload"]["checksum_sha256"]
            != original["observation_payload"]["checksum_sha256"]
        ),
        "metadata_sha256": sha_file(output / "source-frame.json"),
    }


class Profile:
    """Nested exclusive timing for wrappers around existing functions."""

    def __init__(self):
        self.stack = []
        self.total = defaultdict(lambda: [0, 0, 0])

    def invoke(self, label, function, *args, **kwargs):
        children = [0, 0]
        self.stack.append(children)
        start = clocks()
        try:
            return function(*args, **kwargs)
        finally:
            durations = elapsed(start)
            self.stack.pop()
            if self.stack:
                for index, value in enumerate(durations):
                    self.stack[-1][index] += value
            counters = self.total[label]
            for index, value in enumerate(durations):
                counters[index] += value - children[index]
            counters[2] += 1

    def wrap(self, label, function):
        @wraps(function)
        def measured(*args, **kwargs):
            return self.invoke(label, function, *args, **kwargs)

        return measured


@contextmanager
def instrument(profile):
    with ExitStack() as stack:

        def replace(owner, name, wrapper):
            original = vars(owner).get(name)
            if name in vars(owner):
                stack.callback(setattr, owner, name, original)
            else:
                stack.callback(delattr, owner, name)
            setattr(owner, name, wrapper)

        for owner, name, label in (
            (Image.Image, "save", "png_save"),
            (struct, "pack", "pack"),
            (base64, "b64decode", "base64"),
            (base64, "b64encode", "base64"),
            (hashlib, "sha256", "sha256_constructor"),
            (native, "canonical", "metadata_canonicalization"),
            (observations.RGBDObservation, "model_validate", "model_validate"),
        ):
            replace(owner, name, profile.wrap(label, getattr(owner, name)))

        open_file = Path.open

        @contextmanager
        def output_file(stream):
            try:
                yield SimpleNamespace(
                    write=profile.wrap("file_write", stream.write),
                    flush=profile.wrap("file_flush", stream.flush),
                )
            finally:
                profile.invoke("file_close", stream.close)

        def open_output(path, mode="r", *args, **kwargs):
            if mode != "xb":
                return open_file(path, mode, *args, **kwargs)
            return output_file(profile.invoke("file_open", open_file, path, mode, *args, **kwargs))

        replace(Path, "open", open_output)
        yield


def enforce_resources(output, amount, deadline):
    require(amount <= MAX_OUTPUT, "private output hard limit reached")
    require(shutil.disk_usage(output).free >= MIN_FREE, "six GiB free-space floor reached")
    require(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024 <= MAX_RSS, "RSS exceeded")
    require(time.monotonic() <= deadline, "ten-minute wall limit exceeded")


def run_block(output, block, order, inputs, operation_rows, amount, deadline, profiles=False):
    recorders = {variant: recorder_for(output / f"{block}-{variant}") for variant in order}
    encoders = {
        variant: partial(
            observations.observation_from_sensor_frame, png_compress_level=LEVEL[variant]
        )
        for variant in order
    }
    begin = clocks()
    for number, frame in enumerate(inputs, 1):
        for variant in order:
            encoder, recorder = encoders[variant], recorders[variant]
            start = clocks()
            encoder(frame.sensor, source="mujoco_camera")
            encode_wall, encode_cpu = elapsed(start)
            previous = recorder.bytes_written
            profile = Profile() if profiles else None
            if profile is not None:
                with instrument(profile):
                    start = clocks()
                    record_frame(recorder, frame, encoder)
                    wall, cpu = elapsed(start)
            else:
                start = clocks()
                record_frame(recorder, frame, encoder)
                wall, cpu = elapsed(start)
            size = recorder.bytes_written - previous
            amount += size
            row = dict(
                block=block,
                order=order,
                level=variant,
                acquisition=frame.aid,
                role=frame.role,
                layer=frame.layer,
                encode_wall_ns=encode_wall,
                encode_cpu_ns=encode_cpu,
                recorder_wall_ns=wall,
                recorder_cpu_ns=cpu,
                bytes_written=size,
                png_bytes=(recorder.directory / "frames" / frame.aid / "rgb.png").stat().st_size,
            )
            if profile is not None:
                row["profile_exclusive"] = dict(profile.total)
                row["profile_residual_wall_ns"] = phase_residual(
                    wall,
                    {key: stage[0] for key, stage in profile.total.items()},
                )
                row["profile_residual_cpu_ns"] = phase_residual(
                    cpu,
                    {key: stage[1] for key, stage in profile.total.items()},
                )
            operation_rows.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
        if number % 30 == 0:
            operation_rows.flush()
            enforce_resources(output, amount, deadline)
    enforce_resources(output, amount, deadline)
    wall, cpu = elapsed(begin)
    book = {
        "block": block,
        "order": order,
        "start_monotonic_ns": begin[0],
        "wall_ns": wall,
        "process_cpu_ns": cpu,
        "frames_per_variant": len(inputs),
        "variant_total_bytes": {
            name: recorder.bytes_written for name, recorder in recorders.items()
        },
        "linux_loadavg": os.getloadavg(),
    }
    save(output / f"{block}-runtime.json", book)
    print(json.dumps(book, sort_keys=True), flush=True)
    return amount


def nearest_rank(values, fraction):
    ordered = sorted(values)
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]


def summarize(output):
    rows = [
        strict_json(line)
        for line in (output / "frame-measurements.jsonl").read_bytes().splitlines()
    ]
    grouped = defaultdict(dict)
    for row in rows:
        pair = grouped[(row["block"], row["acquisition"])]
        require(row["level"] not in pair, "repeated row")
        pair[row["level"]] = row
    rates = (
        "encode_wall_ns",
        "encode_cpu_ns",
        "recorder_wall_ns",
        "recorder_cpu_ns",
        "bytes_written",
        "png_bytes",
    )
    differences = defaultdict(list)
    block_values = defaultdict(lambda: defaultdict(Counter))
    for (block, _aid), pair in grouped.items():
        if not block.startswith("pair-"):
            continue
        a, b = pair["A"], pair["B"]
        require_identity((a["role"], a["layer"], a["order"]), (b["role"], b["layer"], b["order"]))
        for row in (a, b):
            block_values[block][row["level"]].update({k: row[k] for k in rates})
        for key in rates:
            for stratum in ("ALL", a["role"], a["layer"]):
                differences[(stratum, key)].append(b[key] - a[key])
    require(
        sum(1 for block, _ in grouped if block.startswith("pair-")) == N * len(PAIRS),
        "paired denominator differs",
    )
    stage_totals = defaultdict(lambda: [0, 0, 0])
    overhead = {}
    for row in rows:
        if row["block"] == "profile":
            for key, stage in row["profile_exclusive"].items():
                for index, value in enumerate(stage):
                    stage_totals[key][index] += value
        if row["block"] in {"profile", "profile-reference"}:
            name = row["block"]
            overhead.setdefault(name, Counter())
            overhead[name].update(
                {
                    "frames": 1,
                    "recorder_wall_ns": row["recorder_wall_ns"],
                    "recorder_cpu_ns": row["recorder_cpu_ns"],
                    "profile_residual_wall_ns": row.get("profile_residual_wall_ns", 0),
                    "profile_residual_cpu_ns": row.get("profile_residual_cpu_ns", 0),
                }
            )
    return dict(
        paired_blocks=dict(block_values),
        paired_deltas_B_minus_A={
            stratum: {
                key: {
                    "samples": len(differences[(stratum, key)]),
                    "median": statistics.median(differences[(stratum, key)]),
                    "p95": nearest_rank(differences[(stratum, key)], 0.95),
                }
                for key in rates
            }
            for stratum, _ in differences
        },
        instrumented_stage_totals=dict(stage_totals),
        profile_same_content=overhead,
        phase_fields=["exclusive_wall_ns", "exclusive_process_cpu_ns", "calls"],
    )


def verify_outputs(output, inputs):
    variants = {
        **{f"pair-{number}-{variant}": variant for number in range(1, 5) for variant in "AB"},
        "warmup-A": "A",
        "warmup-B": "B",
        "profile-A": "A",
        "profile-reference-A": "A",
    }
    report = {}
    for block, variant in variants.items():
        path = output / block
        require(
            sorted(p.name for p in (path / "frames").iterdir()) == sorted(f.aid for f in inputs),
            f"output frame inventory differs: {block}",
        )
        digests, png_changes, checksum_changes = {}, 0, 0
        for frame in inputs:
            item = verified_derived(path, frame, variant)
            digests[frame.aid] = item["metadata_sha256"]
            png_changes += item["rgb_digest_changed"]
            checksum_changes += item["observation_checksum_changed"]
        report[block] = dict(
            frames=len(inputs),
            png_digest_changes=png_changes,
            checksum_changes=checksum_changes,
            frame_metadata_inventory_sha256=native.digest(digests),
            frame_metadata_sha256=digests,
        )
    return report


def run_negative(output, inputs):
    frame = inputs[0]
    parent = fresh_output(output / "tamper-control")
    target = parent / "frames" / frame.aid
    shutil.copytree(output / "pair-1-B" / "frames" / frame.aid, target)
    depth = target / "depth.f32"
    data = depth.read_bytes()
    depth.write_bytes(bytes((data[0] ^ 1,)) + data[1:])
    try:
        verified_derived(parent, frame, "B")
    except ValueError as error:
        require(
            "candidate changed depth.f32" in str(error), "wrong rejection stage for tamper control"
        )
        return {"status": "EXPECTED_REJECTION", "artifact": "depth.f32", "message": str(error)}
    raise ValueError("tamper control accepted")


def environment(source):
    with Path("/proc/self/mountinfo").open(encoding="utf8") as stream:
        mounts = [line.strip() for line in stream]
    meminfo = Path("/proc/meminfo").read_text()
    return {
        "interpreter": sys.executable,
        "python_version": sys.version,
        "packages": {k: version(k) for k in ("numpy", "pillow", "pydantic")},
        "cpu_affinity": sorted(os.sched_getaffinity(0)),
        "cpu_model": next(
            line.split(":", 1)[1].strip()
            for line in Path("/proc/cpuinfo").read_text().splitlines()
            if line.startswith("model name")
        ),
        "linux_loadavg": os.getloadavg(),
        "memory": meminfo.splitlines()[:3],
        "free_bytes": shutil.disk_usage(source).free,
        "mountinfo": mounts,
        "clock_resolution_s": {
            name: time.get_clock_info(name).resolution for name in ("perf_counter", "process_time")
        },
        "source": str(source),
        "pillow_zlib_version": Image.core.zlib_version,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("measure", "readback"))
    parser.add_argument("--worktree", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    work, output = args.worktree.absolute(), args.output.absolute()
    deadline = time.monotonic() + 600
    attempted = prohibit_external_activity()
    require(os.sched_getaffinity(0) == {15}, "benchmark requires exclusive CPU 15 allocation")
    require(output.is_relative_to(work / "experiments/results"), "private output location differs")
    run, sources, provenance = preflight(work)
    inputs, rebuild = load_inputs(run)
    if args.command == "readback":
        enforce_resources(output, 0, deadline)
        readback = verify_outputs(output, inputs)
        require(not attempted, "external activity refused")
        save(output / "independent-readback.json", readback)
        save(output / "independent-readback-inputs.json", provenance)
        print(f"Read and independently verified {len(readback)} blocks, {N} frames each")
        return

    fresh_output(output)
    enforce_resources(output, 0, deadline)
    save(output / "preflight-before.json", provenance)
    save(
        output / "preregistration.json",
        {
            "paired_orders": PAIRS,
            "numeric_acquisition_order": [frame.aid for frame in inputs],
            "single_warmup_order": "AB",
            "profile_overhead_order": ["profile-reference", "profile"],
            "source_plan_sha256": PLAN_SHA,
            "bytes_limit": MAX_OUTPUT,
        },
    )
    save(
        output / "environment.json",
        {
            **environment(output),
            "baseline_module_hashes": sources,
            "rebuild_and_baseline_check_wall_cpu_ns": rebuild,
        },
    )
    amount = 0
    with (output / "frame-measurements.jsonl").open("x", encoding="utf8") as rows:
        for block, order, profiled in [
            ("warmup", "AB", False),
            *((f"pair-{number}", order, False) for number, order in enumerate(PAIRS, 1)),
            ("profile-reference", "A", False),
            ("profile", "A", True),
        ]:
            amount = run_block(output, block, order, inputs, rows, amount, deadline, profiled)
    final_input, final_sources, final_provenance = preflight(work)
    save(output / "preflight-after.json", final_provenance)
    require(run == final_input and sources == final_sources, "input source changed")
    result = summarize(output)
    save(
        output / "summary.json",
        {
            **result,
            "total_written_frame_bytes": amount,
            "receipts": {"inputs_pre_post_verified": True},
            "negative_control": run_negative(output, inputs),
            "network_or_simulation_attempts": attempted,
            "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
            "qualification_credit": 0,
            "materialized_frames_per_variant": len(inputs),
        },
    )
    enforce_resources(output, amount, deadline)
    require(not attempted, "external activity refused")


if __name__ == "__main__":
    main()
