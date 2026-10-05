"""Custom V3 offline replay: complete guarded state and trace; no native authority."""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
from collections import Counter
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from cloud_edge_robot_arm.research import mujoco_state_guard as state_guard
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.pose_markers import PoseMarkerRegistration, detect_pose_marker

READER_VERSION = "research.custom-whole-step-guarded-reader.v3"
PROTOCOL = "research.custom-whole-step-guarded-rgbd.v3"
GUARD_PROTOCOL = "research.mujoco-support-aware-state.v1"
BASE_VERIFIER_SOURCE_SHA256 = "19225d13e058cb428b8cf3a99095bde6b46bfd985bcb3290e4824fdd4b0b4e6f"
ASSET_HASH = "ddc34b13d8df403f3fdeeab94be75ca988541f2eac0a3e534704f68200c39a23"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def same_json(left, right):
    """Preserve JSON types as well as values when joining saved raw records."""
    return json.dumps(left, sort_keys=True, separators=(",", ":")) == json.dumps(
        right, sort_keys=True, separators=(",", ":")
    )


def frame_identity(row):
    return {key: row.get(key) for key in ("episode_id", "physics_step", "sim_time_s")}


def verify_series(directory: Path, *, decode=False, output=None, expected_dimensions=None):
    """Read saved observations only; no backend, truth, command target or instance input."""
    summary = json.loads((directory / "summary.json").read_text())
    failures, ends, begins = [], {}, []
    for line in (directory / "index.jsonl").read_text().splitlines():
        row = json.loads(line)
        if row["event"] == "BEGIN":
            begins.append(row["physics_step"])
        elif row["event"] == "END":
            step = row["physics_step"]
            if step in ends:
                failures.append(f"duplicate END at {step}")
            ends[step] = row
        else:
            failures.append("retained recorder failure: " + row["event"])
    allocated = summary["allocated_steps"]
    if type(allocated) is not int or allocated < 1:
        failures.append("invalid allocated terminal horizon")
        allocated = 0
    expected = list(range(allocated))
    if begins != expected or sorted(ends) != expected or summary["status"] != "COMPLETE":
        failures.append("full declared horizon not collected")
    if summary["original_max_sample_gap_s"] > 0.005:
        failures.append("original sampling criterion enlarged")
    marker_registration = PoseMarkerRegistration(7, 0.045, ASSET_HASH) if decode else None
    stream = output.open("x") if output else None
    verified = 0
    ids = set()
    camera = None
    previous_time = previous_end_utc = previous_end_ns = None
    max_gap = 0.0
    statuses = Counter()
    compressed_total = original_total = 0
    try:
        for step, row in sorted(ends.items()):
            try:
                expected_path = f"frames/{step:07d}.json.gz"
                if row["file"] != expected_path:
                    raise ValueError("noncanonical payload path")
                compressed = (directory / expected_path).read_bytes()
                raw = gzip.decompress(compressed)
                if (
                    sha(compressed) != row["compressed_sha256"]
                    or sha(raw) != row["observation_json_sha256"]
                ):
                    raise ValueError("original/compressed payload hash mismatch")
                if len(compressed) != row["compressed_bytes"] or len(raw) != row["original_bytes"]:
                    raise ValueError("payload byte length mismatch")
                observation = RGBDObservation.model_validate_json(raw)
                if (
                    observation.episode_id != summary["episode_id"]
                    or observation.sim_time_s != row["sim_time_s"]
                    or observation.observation_id != row["observation_id"]
                    or observation.checksum_sha256 != row["observation_checksum_sha256"]
                    or observation.observation_id in ids
                ):
                    raise ValueError("frame step/identity/checksum mismatch")
                if (
                    expected_dimensions is not None
                    and (observation.width, observation.height) != expected_dimensions
                ):
                    raise ValueError("saved frame dimensions differ from pinned camera config")
                current_camera = (
                    observation.width,
                    observation.height,
                    observation.intrinsics,
                    observation.camera_to_world,
                    observation.calibration_version,
                    observation.scene_id,
                    observation.source,
                )
                if camera is not None and current_camera != camera:
                    raise ValueError("camera context changed")
                start, end = row["monotonic_begin_ns"], row["monotonic_end_ns"]
                begin_utc, end_utc = (
                    datetime.fromisoformat(row["utc_begin"]),
                    datetime.fromisoformat(row["utc_end"]),
                )
                if (
                    type(start) is not int
                    or type(end) is not int
                    or start > end
                    or not begin_utc <= observation.captured_at <= end_utc
                    or previous_end_utc is not None
                    and begin_utc < previous_end_utc
                    or previous_end_ns is not None
                    and start < previous_end_ns
                ):
                    raise ValueError("nominal capture interval invalid")
                hashes = row["pass_state_hashes"]
                if len(hashes) != 2 or hashes[0] != hashes[1]:
                    raise ValueError("registered two-pass source mismatch")
                if previous_time is not None:
                    gap = observation.sim_time_s - previous_time
                    if not 0 < gap <= summary["original_max_sample_gap_s"] + 1e-9:
                        raise ValueError("original maximum simulation sample gap exceeded")
                    max_gap = max(max_gap, gap)
                members = {
                    name: base64.b64decode(getattr(observation, field), validate=True)
                    for name, field in (
                        ("rgb.png", "rgb_png_base64"),
                        ("depth.f32", "depth_float32_base64"),
                        ("valid_mask.u8", "valid_mask_base64"),
                    )
                }
                measured = {
                    "physics_step": step,
                    "episode_id": observation.episode_id,
                    "sim_time_s": observation.sim_time_s,
                    "observation_id": observation.observation_id,
                    "checksum": observation.checksum_sha256,
                    "raw_member_sha256": {name: sha(data) for name, data in members.items()},
                    "raw_member_bytes": {name: len(data) for name, data in members.items()},
                    "decode_status": "NOT_REQUESTED",
                }
                if marker_registration is not None:
                    estimate = detect_pose_marker(observation, marker_registration)
                    measured["marker"] = asdict(estimate)
                    measured["marker"]["captured_at"] = estimate.captured_at.isoformat()
                    measured["decode_status"] = estimate.status
                    statuses[estimate.status] += 1
                if stream:
                    stream.write(json.dumps(measured, allow_nan=False) + "\n")
                    stream.flush()
                verified += 1
                ids.add(observation.observation_id)
                camera = current_camera
                previous_time, previous_end_utc, previous_end_ns = (
                    observation.sim_time_s,
                    end_utc,
                    end,
                )
                compressed_total += len(compressed)
                original_total += len(raw)
            except (OSError, ValueError, TypeError, KeyError) as error:
                failures.append(f"step {step}: {type(error).__name__}: {error}")
                if stream:
                    stream.write(
                        json.dumps(
                            {
                                "physics_step": step,
                                "decode_status": "UNAVAILABLE_INVALID_RAW",
                                "reason": str(error),
                            }
                        )
                        + "\n"
                    )
                    stream.flush()
    finally:
        if stream:
            stream.close()
    if verified != allocated or previous_time != summary["final_sim_time_s"]:
        failures.append("verified terminal horizon mismatch")
    return {
        "scope": "EXCLUDED_DEVELOPMENT_OFFLINE_RAW_RGBD_REPLAY",
        "integrity_status": "VERIFIED" if not failures else "INCOMPLETE_OR_INVALID",
        "allocated_steps": allocated,
        "allocated_step_denominator_retained": True,
        "verified_frames": verified,
        "failed_or_missing_frames": allocated - verified,
        "max_sim_sample_gap_s": max_gap,
        "original_max_sample_gap_s": summary["original_max_sample_gap_s"],
        "compressed_bytes": compressed_total,
        "original_json_bytes": original_total,
        "decoder_status_counts": dict(statuses),
        "decoder_requested": decode,
        "failures": failures,
        "clock_scope": "SAME_PROCESS_NOMINAL_BRACKETS_ONLY",
        "external_utc_uncertainty": "UNAVAILABLE",
        "formal_accepted": False,
        "native_admission": "NOT_PROMOTED",
        "continuous_motion": "NOT_CERTIFIED",
        "future_stability": "UNAVAILABLE",
        "calibrated_error_bound": "UNAVAILABLE",
    }


def read_jsonl_gzip(path: Path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            yield json.loads(line)


def guard_record(record, contract):
    """Reconstruct validated immutable records; recorded digests are never trusted."""
    if type(record) is not dict or set(record) != {"arrays", "protected_json", "digest"}:
        raise ValueError("guard record inventory invalid")
    arrays = record["arrays"]
    if type(arrays) is not dict or set(arrays) != {"contract_digest", "fields", "digest"}:
        raise ValueError("array record inventory invalid")
    fields = []
    for member in arrays["fields"]:
        if type(member) is not dict or type(member.get("shape")) is not list:
            raise ValueError("array field/shape representation invalid")
        fields.append(state_guard.ArrayField(**{**member, "shape": tuple(member["shape"])}))
    snapshot = state_guard.DataArraySnapshot(arrays["contract_digest"], tuple(fields))
    if snapshot.contract_digest != contract.digest or snapshot.digest != arrays["digest"]:
        raise ValueError("array contract/digest mismatch")
    dynamic = {getter.name: getter for getter in contract.getters}
    if not dynamic.keys() <= {field.name for field in snapshot.fields}:
        raise ValueError("dynamic getter inventory incomplete")
    dimensions = {}
    for field in snapshot.fields:
        getter = dynamic.get(field.name)
        if (
            field.status == "UNSUPPORTED_NULL_ALLOCATION"
            and getter is None
            or field.storage == "OWNING"
            and field.name not in contract.known_fields
        ):
            raise ValueError("unsupported owning getter outside frozen contract")
        if getter is not None:
            if (
                field.dtype != getter.dtype
                or len(field.shape) != (1 if getter.width == 1 else 2)
                or getter.width != 1
                and field.shape[-1] != getter.width
            ):
                raise ValueError("dynamic getter shape/dtype invalid")
            key = (getter.source, getter.dimension)
            if key in dimensions and dimensions[key] != field.shape[0]:
                raise ValueError("dynamic getter shared dimension mismatch")
            dimensions[key] = field.shape[0]
    if type(record["protected_json"]) is not str:
        raise ValueError("protected state representation invalid")
    protected = json.loads(record["protected_json"])
    result = state_guard.attach_protected_state(snapshot, protected)
    if result.protected_json != record["protected_json"] or result.digest != record["digest"]:
        raise ValueError("complete guarded state digest mismatch")
    return result


def verify_camera_guard(camera, contract):
    if camera.get("guard_protocol") != GUARD_PROTOCOL or not camera.get("camera_call_started"):
        raise ValueError("missing custom guarded camera acquisition")
    before = guard_record(camera["before_guard"], contract)
    after = guard_record(camera["after_guard"], contract)
    state_guard.assert_unchanged(before, after)
    for name, record in (("before_state", before), ("after_state", after)):
        expected = {**json.loads(record.protected_json), "data_arrays_sha256": record.arrays.digest}
        if not same_json(camera[name], expected):
            raise ValueError("guard/protected scalar bridge mismatch")
    if camera["pass_state_hashes"] != [camera["before_state"]["physics_state_sha256"]] * 2:
        raise ValueError("guard/two-pass physical state mismatch")


def verify_execution_header(directory, summary):
    """Check saved header, necessary source bytes and environment pins, without acquisition."""
    path = directory / "execution-header.json"
    raw = path.read_bytes()
    header = json.loads(raw)
    if sha(raw) != summary["execution_header_sha256"]:
        raise ValueError("saved execution header digest mismatch")
    if (
        header["protocol"] != PROTOCOL
        or summary["protocol"] != PROTOCOL
        or header["guard_protocol"] != GUARD_PROTOCOL
        or header["raw_v3_status"] != "CUSTOM_PROTOCOL_NOT_RAW_V3"
        or summary["raw_v3_status"] != "CUSTOM_PROTOCOL_NOT_RAW_V3"
        or header["source_authenticity"] != "UNKNOWN"
        or header["independent_calibration_group"] is not False
    ):
        raise ValueError("custom protocol/authority contract mismatch")
    root, archive_root = Path(header["source_root"]), Path(header["archive_root"])
    prepared = directory.parent
    manifest_raw = (prepared / "execution-source-hashes.json").read_bytes()
    index_raw = (prepared / "execution-archive-index.json").read_bytes()
    if (
        sha(manifest_raw) != header["source_manifest_sha256"]
        or sha(index_raw) != header["source_archive_index_sha256"]
    ):
        raise ValueError("execution source manifest/index pin mismatch")
    sources, archives = json.loads(manifest_raw), json.loads(index_raw)
    if (
        set(sources) != set(archives)
        or len(sources) != header["source_count"]
        or len(sources) != 32
    ):
        raise ValueError("execution source inventory mismatch")
    for name, expected in sources.items():
        live, archived = (
            (root / name).read_bytes(),
            (archive_root / archives[name]["archive"]).read_bytes(),
        )
        if (
            sha(live) != expected
            or sha(archived) != expected
            or archives[name]["sha256"] != expected
            or len(live) != archives[name]["bytes"]
        ):
            raise ValueError("execution source/archive bytes mismatch: " + name)
    guard_name = "src/cloud_edge_robot_arm/research/mujoco_state_guard.py"
    if (
        sources.get(guard_name) != header["guard_core_sha256"]
        or sha(Path(state_guard.__file__).read_bytes()) != header["guard_core_sha256"]
    ):
        raise ValueError("guard core source pin mismatch")
    for member in header["environment"]["files"].values():
        if sha(Path(member["path"]).read_bytes()) != member["sha256"]:
            raise ValueError("execution environment dependency mismatch")
    contract = state_guard.MujocoStateContract(
        Path(header["guard_headers"]["mjxmacro.h"]).read_bytes(),
        Path(header["guard_headers"]["mjdata.h"]).read_bytes(),
        header["guard_binding_sha256"],
        header["environment"]["mujoco_version"],
    )
    return contract, header


def reconcile_journal(records, episode, summary, terminal, series_allocated):
    """Derive complete event sets before trusting any declared success counters."""
    failures = []
    event_rows = {}
    for row in records:
        event_rows.setdefault(row["event"], []).append(row)

    def keyed(events, field):
        groups = {}
        for event in events:
            for row in event_rows.get(event, []):
                value = row.get(field)
                if type(value) is not int or value < (0 if field == "physics_step" else 1):
                    failures.append("invalid original event identity: " + event)
                    continue
                groups.setdefault(value, {}).setdefault(event, []).append(row)
        return groups

    acquisition = keyed(
        ("ACQUISITION_BEGIN", "ACQUISITION_END", "ACQUISITION_FAILED"), "physics_step"
    )
    action = keyed(
        ("ACTION_BEGIN", "ACTION_END", "ACTION_FAILED", "TEACHER_ACTION"), "action_ordinal"
    )
    acquisition_counts = {
        event: len(event_rows.get(event, []))
        for event in ("ACQUISITION_BEGIN", "ACQUISITION_END", "ACQUISITION_FAILED")
    }
    action_counts = {
        event: len(event_rows.get(event, []))
        for event in ("ACTION_BEGIN", "ACTION_END", "ACTION_FAILED", "TEACHER_ACTION")
    }
    hanging = []
    for step, events in acquisition.items():
        if step >= series_allocated:
            failures.append(f"step {step}: out-of-horizon acquisition retained")
        if any(len(rows) != 1 for rows in events.values()):
            failures.append(f"step {step}: duplicate original acquisition event retained")
        if "ACQUISITION_BEGIN" not in events or "ACQUISITION_END" not in events:
            hanging.append(step)
            failures.append(f"step {step}: unmatched original acquisition lifecycle retained")
        if "ACQUISITION_FAILED" in events:
            failures.append(f"step {step}: original ACQUISITION_FAILED retained")
        for rows in events.values():
            if any(row.get("episode_id") != episode for row in rows):
                failures.append(f"step {step}: acquisition lifecycle episode mismatch")
    observed_allocated = max(len(acquisition), acquisition_counts["ACQUISITION_BEGIN"])
    declared = summary.get("acquisition_allocated")
    if type(declared) is not int or declared < 0:
        failures.append("invalid declared acquisition allocation counter")
        declared = 0
    allocated = max(series_allocated, observed_allocated, declared)
    expected_steps = set(range(series_allocated))
    if set(acquisition) != expected_steps:
        failures.append("entire original acquisition set differs from declared physical horizon")
    if (
        declared != observed_allocated
        or summary.get("acquisition_completed") != acquisition_counts["ACQUISITION_END"]
        or summary.get("acquisition_failed") != acquisition_counts["ACQUISITION_FAILED"]
    ):
        failures.append("journal-derived acquisition counters differ from summary")
    camera_calls = sum(
        row.get("camera", {}).get("camera_call_started") is True
        for event in ("ACQUISITION_END", "ACQUISITION_FAILED")
        for row in event_rows.get(event, [])
        if type(row.get("camera")) is dict
    )
    if summary.get("whole_step_capture_calls") != camera_calls:
        failures.append("journal-derived camera delegate counter differs from summary")
    for ordinal, events in action.items():
        if set(events) != {"ACTION_BEGIN", "ACTION_END", "TEACHER_ACTION"} or any(
            len(rows) != 1 for rows in events.values()
        ):
            failures.append(f"action {ordinal}: complete original action lifecycle unavailable")
        if "ACTION_FAILED" in events:
            failures.append(f"action {ordinal}: original ACTION_FAILED retained")
        for event in ("ACTION_BEGIN", "ACTION_END", "ACTION_FAILED"):
            for row in events.get(event, []):
                if row.get("episode_id") != episode:
                    failures.append(f"action {ordinal}: original action episode mismatch")
        begin = events.get("ACTION_BEGIN", [{}])[0]
        end = events.get("ACTION_END", [{}])[0]
        teacher = events.get("TEACHER_ACTION", [{}])[0].get("source", {})
        if (
            begin.get("action_type") != end.get("action_type")
            or teacher.get("episode_id") != episode
        ):
            failures.append(f"action {ordinal}: complete original action identity mismatch")
    if (
        summary.get("action_begins") != action_counts["ACTION_BEGIN"]
        or summary.get("action_ends") != action_counts["ACTION_END"]
        or summary.get("action_failed") != action_counts["ACTION_FAILED"]
        or set(action) != set(range(1, len(action) + 1))
    ):
        failures.append("journal-derived action sets/counters differ from summary")
    operation = {}
    begin_ids = []
    ledger = []
    for row in event_rows.get("OPERATION", []):
        source = row.get("source", {})
        identifier, phase = source.get("operation_id"), source.get("phase")
        if type(identifier) is not int or identifier < 1 or phase not in {"BEGIN", "END"}:
            failures.append("invalid operation boundary identity")
            continue
        operation.setdefault(identifier, {}).setdefault(phase, []).append(row)
        if phase == "BEGIN":
            begin_ids.append(identifier)
        ledger.append(
            {
                key: source.get(key)
                for key in (
                    "operation_id",
                    "kind",
                    "phase",
                    "episode_id",
                    "physics_step",
                    "error_type",
                    "error",
                )
            }
        )
        if (
            source.get("episode_id") != episode
            or source.get("kind") not in {"RESET", "COMMAND", "CAPTURE", "CONTROL", "PHYSICS"}
            or type(source.get("physics_step")) is not int
            or source.get("error_type") is not None
            or source.get("error") is not None
        ):
            failures.append(
                f"operation {identifier}: invalid original kind/episode/step or retained failure"
            )
    if begin_ids and begin_ids != list(range(begin_ids[0], begin_ids[0] + len(begin_ids))):
        failures.append("original operation BEGIN sequence not unique and complete")
    if not same_json(ledger, terminal.get("operation_ledger")):
        failures.append("entire original operation source differs from terminal ledger")
    for identifier, phases in operation.items():
        if set(phases) != {"BEGIN", "END"} or any(len(rows) != 1 for rows in phases.values()):
            failures.append(f"operation {identifier}: unmatched or duplicate boundary retained")
            continue
        begin, end = phases["BEGIN"][0], phases["END"][0]
        left, right = begin["source"], end["source"]
        if (
            left["kind"] != right["kind"]
            or left["episode_id"] != right["episode_id"]
            or not same_json(left.get("parameters"), right.get("parameters"))
            or begin["record_seq"] >= end["record_seq"]
            or begin["clock"]["monotonic_after_ns"] > end["clock"]["monotonic_before_ns"]
        ):
            failures.append(
                f"operation {identifier}: complete BEGIN/END identity or bracket mismatch"
            )
    return {
        "allocated_steps": allocated,
        "journal_acquisition_allocated_steps": observed_allocated,
        "series_allocated_steps": series_allocated,
        "journal_acquisition_event_counts": acquisition_counts,
        "journal_action_event_counts": action_counts,
        "journal_action_allocated": len(action),
        "journal_camera_delegate_count": camera_calls,
        "unmatched_acquisition_steps": sorted(hanging),
        "retained_acquisition_steps": sorted(acquisition),
        "failures": failures,
    }


def verify_original_recipe(header, actions, teacher_actions, summary, terminal):
    """An incomplete original prefix remains incomplete; no remaining action is executed."""
    if header is None or "planned_teacher_actions" not in header:
        if (
            header is not None
            and header.get("scope") == "EXCLUDED_SAME_COMPONENT_CUSTOM_WHOLE_STEP_RGBD"
        ):
            return "INCOMPLETE_ORIGINAL_RECIPE", [
                "original recipe header missing required contract"
            ]
        return "NOT_DECLARED_SOFTWARE_CONTROL", []
    if summary["run_status"] != "COMPLETED_SINGLE_ATTEMPT":
        return "INCOMPLETE_ORIGINAL_PREFIX", []
    failures = []
    recipe = (
        "MOVE_ABOVE",
        "APPROACH",
        "GRASP",
        "LIFT",
        "OBSERVE",
        "MOVE_TO_REGION",
        "PLACE",
        "RELEASE",
        "OBSERVE",
    )
    if header.get("settle_steps") != 120 or header["planned_teacher_actions"] != len(recipe):
        failures.append("original recipe header differs from frozen 120/9 contract")
    if summary["action_begins"] != len(recipe) or summary["action_ends"] != len(recipe):
        return "INCOMPLETE_ORIGINAL_RECIPE", failures + [
            "original recipe nine action coverage incomplete"
        ]
    previous = 120
    for ordinal, kind in enumerate(recipe, 1):
        begin, end = actions.get((ordinal, "ACTION_BEGIN")), actions.get((ordinal, "ACTION_END"))
        source = teacher_actions.get(ordinal, {}).get("source", {})
        if begin is None or end is None:
            failures.append(f"recipe action {ordinal}: original span unavailable")
            continue
        if (
            begin.get("action_type") != kind
            or end.get("action_type") != kind
            or begin["start_step"] != previous
            or end["end_step"] <= previous
            or (end.get("result") or {}).get("action_type") != kind
            or (source.get("result") or {}).get("action_type") != kind
        ):
            failures.append(
                f"recipe action {ordinal}: original order/type/physical coverage mismatch"
            )
        if ordinal in {5, 9}:
            seconds, purpose = (
                (0.5, "post_lift_stability") if ordinal == 5 else (1.2, "post_release_stability")
            )
            arguments = begin.get("arguments", [])
            steps = max(1, round(seconds / header["config"]["physics_dt_s"]))
            if (
                len(arguments) != 3
                or arguments[1:] != [seconds, purpose]
                or end["end_step"] - begin["start_step"] != steps
                or (end.get("result") or {}).get("details", {}).get("purpose") != purpose
            ):
                failures.append(
                    f"recipe dwell {ordinal}: exact original duration/purpose/span mismatch"
                )
        previous = end["end_step"]
    if previous != terminal["final_step"]:
        failures.append("original recipe terminal physical horizon differs")
    return ("COMPLETE_ORIGINAL_120_9_2" if not failures else "INCOMPLETE_ORIGINAL_RECIPE"), failures


def verify_runtime_evidence(directory, records, header):
    if header is None or header.get("scope") != "EXCLUDED_SAME_COMPONENT_CUSTOM_WHOLE_STEP_RGBD":
        return "NOT_DECLARED_SOFTWARE_CONTROL", []
    try:
        record = json.loads((directory / "runtime-preflight.json").read_text())
        begins = [row for row in records if row["event"] == "SETUP_BEGIN"]
        if (
            len(begins) != 1
            or not same_json(begins[0].get("runtime_preflight"), record)
            or record["scope"] != "ACTUAL_MODULE_IMPORT_ONLY_BEFORE_FIRST_MODEL_RESET_CAMERA"
            or record["actual_mujoco_version"] != header["environment"]["mujoco_version"]
            or record["actual_numpy_version"] != header["environment"]["numpy_version"]
            or record["models_or_data_instantiated"] != 0
        ):
            raise ValueError("module preflight/setup association mismatch")
        expected_module = header["environment"]["files"]["mujoco/__init__.py"]
        if not same_json(record["public_module_origin"], expected_module):
            raise ValueError("module origin record differs from pin")
        for name in ("MjModel", "MjData"):
            if not same_json(
                record["classes"][name],
                {"module": "mujoco._structs", "name": name, "public_binding_identity": True},
            ):
                raise ValueError("public/binding class origin record differs")
        for name, member in record["binding_origins"].items():
            expected = header["environment"]["files"]["mujoco/" + Path(member["path"]).name]
            if name not in {"_structs", "_functions", "_enums"} or not same_json(member, expected):
                raise ValueError("binding origin record differs from pin")
        if set(record["binding_origins"]) != {"_structs", "_functions", "_enums"}:
            raise ValueError("binding origin record inventory incomplete")
    except (OSError, ValueError, KeyError, TypeError) as error:
        return "INCOMPLETE_MODULE_ORIGIN_RECORD", [
            "pre-model runtime provenance record invalid: " + str(error)
        ]
    return "CONSISTENT_PRE_MODEL_MODULE_RECORD_NOT_SOURCE_AUTHORITY", []


def verify_attempt(input_directory: Path, *, output_directory: Path, decode=False):
    """Replay existing bytes; write derived evidence only outside the input tree."""
    directory = input_directory.resolve(strict=True)
    output_directory = output_directory.resolve()
    if output_directory == directory or directory in output_directory.parents:
        raise ValueError("output directory must be outside input directory")
    output_directory.mkdir(parents=True, exist_ok=False)
    summary = json.loads((directory / "summary.json").read_text())
    terminal = json.loads((directory / "terminal.json").read_text())
    contract = None
    header = None
    preflight_failures = []
    try:
        contract, header = verify_execution_header(directory, summary)
    except (OSError, ValueError, TypeError, KeyError, state_guard.StateGuardError) as error:
        preflight_failures.append("execution header/source preflight: " + str(error))
    dimensions = (
        None
        if header is None
        else (header["config"]["camera_width"], header["config"]["camera_height"])
    )
    report = verify_series(
        directory / "whole-step",
        decode=False,
        output=output_directory / "offline-observations.jsonl",
        expected_dimensions=dimensions,
    )
    failures = report["failures"]
    failures.extend(preflight_failures)
    series_summary = json.loads((directory / "whole-step/summary.json").read_text())
    index_ends = {}
    for line in (directory / "whole-step/index.jsonl").read_text().splitlines():
        source_row = json.loads(line)
        if source_row["event"] == "END":
            index_ends[source_row["physics_step"]] = source_row
    final_identity = {
        "episode_id": series_summary["episode_id"],
        "physics_step": series_summary["final_step"],
        "sim_time_s": series_summary["final_sim_time_s"],
    }
    if not same_json(
        final_identity,
        {
            "episode_id": terminal.get("episode_id"),
            "physics_step": terminal.get("final_step"),
            "sim_time_s": terminal.get("final_sim_time_s"),
        },
    ):
        failures.append("terminal episode/step/time differs from continuous sequence")
    if not same_json(
        frame_identity(index_ends.get(series_summary["final_step"], {})), final_identity
    ):
        failures.append("terminal continuous sequence/index identity mismatch")
    actions, operations, acquisitions, acquisition_begins, teacher_actions, actuators = (
        {},
        {},
        {},
        {},
        {},
        {},
    )
    original_commands = []
    sequence = 0
    last_ns = None
    records = list(read_jsonl_gzip(directory / "nominal-journal.jsonl.gz"))
    for row in records:
        clock = row["clock"]
        before, after = clock["monotonic_before_ns"], clock["monotonic_after_ns"]
        if (
            type(row["record_seq"]) is not int
            or type(before) is not int
            or type(after) is not int
            or row["record_seq"] != sequence + 1
            or before > after
            or last_ns is not None
            and before < last_ns
        ):
            failures.append("nominal event sequence/clock bracket invalid")
        sequence, last_ns = row["record_seq"], after
        if row["event"] == "OPERATION":
            source = row["source"]
            key = (source["operation_id"], source["phase"])
            if key in operations:
                failures.append("duplicate operation boundary")
            operations.setdefault(key, row)
            if source["kind"] == "COMMAND" and source["phase"] == "END":
                original_commands.extend((source.get("result") or {}).get("command_records", []))
        elif row["event"] in {"ACTION_BEGIN", "ACTION_END"}:
            key = (row["action_ordinal"], row["event"])
            if key in actions:
                failures.append("duplicate original action boundary")
            actions.setdefault(key, row)
        elif row["event"] == "TEACHER_ACTION":
            teacher_actions.setdefault(row["action_ordinal"], row)
        elif row["event"] == "ACTUATOR":
            step = row["source"]["physics_step"]
            if step in actuators:
                failures.append("duplicate pre-physics actuator source")
            actuators.setdefault(step, row)
        elif row["event"] == "ACQUISITION_BEGIN":
            step = row["physics_step"]
            if step in acquisition_begins:
                failures.append("duplicate acquisition BEGIN")
            acquisition_begins.setdefault(step, row)
        elif row["event"] == "ACQUISITION_END":
            if row["physics_step"] in acquisitions:
                failures.append("duplicate acquisition END")
            acquisitions.setdefault(row["physics_step"], row)
    derived = reconcile_journal(
        records, series_summary["episode_id"], summary, terminal, report["allocated_steps"]
    )
    failures.extend(derived.pop("failures"))
    if set(actuators) != set(range(1, series_summary["allocated_steps"])):
        failures.append("entire upcoming actuator set differs from physical horizon")
    for kind, expected in (
        ("CONTROL", list(range(series_summary["allocated_steps"] - 1))),
        ("PHYSICS", list(range(1, series_summary["allocated_steps"]))),
    ):
        actual_steps = [
            row["source"]["physics_step"]
            for row in records
            if row["event"] == "OPERATION"
            and row["source"]["kind"] == kind
            and row["source"]["phase"] == "END"
        ]
        if actual_steps != expected:
            failures.append("entire original " + kind + " END set differs from physical horizon")
    if (
        summary["run_status"] != "COMPLETED_SINGLE_ATTEMPT"
        or terminal["operation_observer_failures"]
    ):
        failures.append("attempt or operation association remained partial")
    if summary["action_begins"] != summary["action_ends"]:
        failures.append("original action BEGIN/END count mismatch")
    if original_commands != terminal["commands"]:
        failures.append("original command source differs from terminal command journal")
    if report["allocated_steps"] != terminal["final_step"] + 1:
        failures.append("terminal and declared frame horizons differ")
    action_spans = {}
    for ordinal in range(1, summary["action_begins"] + 1):
        begin, end = actions.get((ordinal, "ACTION_BEGIN")), actions.get((ordinal, "ACTION_END"))
        teacher_action = teacher_actions.get(ordinal)
        if begin is None or end is None or teacher_action is None:
            failures.append(f"action {ordinal}: original/teacher span missing")
            continue
        start_step, end_step = begin["start_step"], end["end_step"]
        if (
            type(start_step) is not int
            or type(end_step) is not int
            or not 0 <= start_step <= end_step <= terminal["final_step"]
            or end["start_step"] != start_step
        ):
            failures.append(f"action {ordinal}: invalid original physical span")
        else:
            action_spans[ordinal] = (start_step, end_step)
        start, stop = begin["command_seq_start"], end["command_seq_end"]
        if (
            not 1 <= start <= stop <= len(terminal["commands"]) + 1
            or end["command_seq_start"] != start
        ):
            failures.append(f"action {ordinal}: half-open command span invalid")
        expected = {
            "start_step": begin["start_step"],
            "end_step": end["end_step"],
            "command_seq_start": start,
            "command_seq_end": stop,
        }
        if any(teacher_action["source"][key] != value for key, value in expected.items()):
            failures.append(f"action {ordinal}: teacher/original span mismatch")
        result = end.get("result")
        if result is None or end.get("error_type"):
            failures.append(f"action {ordinal}: original action did not return")
        else:
            start_utc, finish_utc = (
                datetime.fromisoformat(result["started_at"]),
                datetime.fromisoformat(result["finished_at"]),
            )
            if not (
                datetime.fromisoformat(begin["clock"]["utc"])
                <= start_utc
                <= finish_utc
                <= datetime.fromisoformat(end["clock"]["utc"])
            ):
                failures.append(f"action {ordinal}: original wall interval outside nominal wrapper")
    for step in range(report["allocated_steps"]):
        row = acquisitions.get(step)
        if row is None:
            failures.append(f"step {step}: missing saved acquisition association")
            continue
        begin = acquisition_begins.get(step)
        authoritative = index_ends.get(step, {})
        if not same_json(row["saved"], authoritative):
            failures.append(f"step {step}: saved acquisition differs from complete index END")
        identity = frame_identity(authoritative)
        if (
            not same_json(frame_identity(row), identity)
            or begin is None
            or not same_json(frame_identity(begin), identity)
            or not same_json(frame_identity(begin.get("physical_source", {})), identity)
        ):
            failures.append(f"step {step}: acquisition/raw physical identity mismatch")
        owners = [
            ordinal
            for ordinal, (start_step, end_step) in action_spans.items()
            if start_step < step <= end_step
        ]
        if len(owners) > 1 or row["action_ordinal"] != (owners[0] if owners else None):
            failures.append(f"step {step}: action ownership not unique or incorrectly bound")
        if (
            begin is None
            or begin["action_ordinal"] != row["action_ordinal"]
            or begin["control_operation_id"] != row["control_operation_id"]
            or begin["physics_operation_id"] != row["physics_operation_id"]
            or begin.get("command_seq_next") != row["camera"]["before_state"]["command_count"] + 1
            or begin["clock"]["monotonic_after_ns"] > row["saved"]["monotonic_begin_ns"]
            or row["saved"]["monotonic_end_ns"] > row["clock"]["monotonic_before_ns"]
        ):
            failures.append(f"step {step}: acquisition BEGIN/END bracket invalid")
        if (
            not row["camera"]["state_unchanged"]
            or row["camera"]["before_state"] != row["camera"]["after_state"]
        ):
            failures.append(f"step {step}: measured state preservation invalid")
        try:
            if contract is None:
                raise ValueError("verified execution contract unavailable")
            verify_camera_guard(row["camera"], contract)
        except (ValueError, TypeError, KeyError, state_guard.StateGuardError) as error:
            failures.append(f"step {step}: complete guarded acquisition invalid: {error}")
        for state in ("before_state", "after_state"):
            camera_identity = {
                "physics_step": row["camera"][state].get("physical_step"),
                "sim_time_s": row["camera"][state].get("sim_time_s"),
            }
            if not same_json(
                camera_identity, {key: identity[key] for key in ("physics_step", "sim_time_s")}
            ):
                failures.append(f"step {step}: camera measured step/time mismatch")
        if not (
            row["saved"]["monotonic_begin_ns"]
            <= row["camera"]["capture_monotonic_begin_ns"]
            <= row["camera"]["capture_monotonic_end_ns"]
            <= row["saved"]["monotonic_end_ns"]
        ):
            failures.append(f"step {step}: camera/raw capture clock interval mismatch")
        if not same_json(row["camera"]["pass_state_hashes"], row["saved"]["pass_state_hashes"]):
            failures.append(f"step {step}: camera/index two-pass digest bridge mismatch")
        if step == 0 and (
            row["control_operation_id"] is not None or row["physics_operation_id"] is not None
        ):
            failures.append("step zero cannot claim preceding CONTROL/PHYSICS operations")
        if step:
            physics = operations.get((row["physics_operation_id"], "END"))
            control = operations.get((row["control_operation_id"], "END"))
            physics_begin = operations.get((row["physics_operation_id"], "BEGIN"))
            control_begin = operations.get((row["control_operation_id"], "BEGIN"))
            # Source _build_actuator_observation identifies the upcoming step n.
            # CONTROL and PHYSICS BEGIN remain at n-1; PHYSICS END is n.
            actuator = actuators.get(step)
            prior = index_ends.get(step - 1, {})
            prior_identity = frame_identity(prior)
            for boundary, kind, phase, expected_identity in (
                (control_begin, "CONTROL", "BEGIN", prior_identity),
                (control, "CONTROL", "END", prior_identity),
                (physics_begin, "PHYSICS", "BEGIN", prior_identity),
                (physics, "PHYSICS", "END", identity),
            ):
                source = {} if boundary is None else boundary["source"]
                expected_id = (
                    row["control_operation_id"]
                    if kind == "CONTROL"
                    else row["physics_operation_id"]
                )
                if (
                    source.get("operation_id") != expected_id
                    or type(source.get("operation_id")) is not int
                    or source.get("kind") != kind
                    or source.get("phase") != phase
                    or not same_json(frame_identity(source), expected_identity)
                ):
                    failures.append(
                        f"step {step}: complete {kind} {phase} source identity mismatch"
                    )
            expected_actuator = {
                "episode_id": identity["episode_id"],
                "physics_step": step,
                "sim_time_s": prior.get("sim_time_s"),
            }
            if (
                actuator is None
                or not same_json(frame_identity(actuator.get("source", {})), expected_actuator)
                or actuator.get("control_operation_id") != row["control_operation_id"]
                or actuator.get("action_ordinal") != row["action_ordinal"]
            ):
                failures.append(f"step {step}: complete upcoming actuator source identity mismatch")
            elif control is not None and not same_json(
                (control["source"].get("result") or {}).get("control_state"), actuator["source"]
            ):
                failures.append(f"step {step}: original CONTROL result/actuator source differs")
            if physics is not None:
                physical_source = (physics["source"].get("result") or {}).get("physics_state", {})
                if not same_json(frame_identity(physics["source"]), identity) or not same_json(
                    frame_identity(physical_source), identity
                ):
                    failures.append(f"step {step}: declared PHYSICS source identity mismatch")
            if (
                physics is None
                or physics["source"]["kind"] != "PHYSICS"
                or physics["source"]["physics_step"] != step
                or control is None
                or control["source"]["kind"] != "CONTROL"
                or control["source"]["physics_step"] != step - 1
                or physics_begin is None
                or control_begin is None
                or begin is None
                or actuator is None
            ):
                failures.append(f"step {step}: CONTROL/PHYSICS association mismatch")
            elif not (
                control_begin["clock"]["monotonic_after_ns"]
                <= control["clock"]["monotonic_before_ns"]
                <= actuator["clock"]["monotonic_before_ns"]
                <= physics_begin["clock"]["monotonic_before_ns"]
                <= physics["clock"]["monotonic_before_ns"]
                <= begin["clock"]["monotonic_before_ns"]
                and actuator["control_operation_id"] == row["control_operation_id"]
            ):
                failures.append(
                    f"step {step}: CONTROL/actuator/PHYSICS/acquisition clocks mismatch"
                )
        ordinal = row["action_ordinal"]
        if ordinal is not None:
            begin, end = (
                actions.get((ordinal, "ACTION_BEGIN")),
                actions.get((ordinal, "ACTION_END")),
            )
            if (
                begin is None
                or end is None
                or not begin["start_step"] < step <= end["end_step"]
                or not begin["clock"]["monotonic_after_ns"]
                <= row["saved"]["monotonic_begin_ns"]
                <= row["clock"]["monotonic_after_ns"]
                <= end["clock"]["monotonic_before_ns"]
            ):
                failures.append(f"step {step}: original action span mismatch")
    if (
        summary.get("acquisition_allocated") != report["allocated_steps"]
        or summary.get("acquisition_completed") != len(acquisitions)
        or summary.get("acquisition_failed") != 0
        or summary.get("whole_step_capture_calls") != report["allocated_steps"]
        or summary.get("acquisition_failure_journal_errors")
        or summary.get("action_failed") != 0
        or summary.get("action_delegated") != summary["action_begins"]
        or summary.get("action_failure_journal_errors")
        or summary.get("nominal_journal_failure")
    ):
        failures.append("complete original acquisition/action denominators mismatch or failure")
    runtime_record_status, runtime_record_failures = verify_runtime_evidence(
        directory, records, header
    )
    failures.extend(runtime_record_failures)
    recipe_status, recipe_failures = verify_original_recipe(
        header, actions, teacher_actions, summary, terminal
    )
    failures.extend(recipe_failures)
    # The journal can retain a larger attempted denominator than a forged/partial series summary.
    report.update(derived)
    report["failed_or_missing_frames"] = report["allocated_steps"] - report["verified_frames"]
    if decode and not failures:
        decoded = verify_series(
            directory / "whole-step",
            decode=True,
            output=output_directory / "offline-markers.jsonl",
            expected_dimensions=dimensions,
        )
        report["decoder_status_counts"] = decoded["decoder_status_counts"]
        report["decoder_requested"] = True
        failures.extend(decoded["failures"])
    report["decoder_blocked_by_integrity_failure"] = bool(decode and failures)
    report.update(
        protocol=PROTOCOL,
        raw_v3_status="CUSTOM_PROTOCOL_NOT_RAW_V3",
        guard_protocol=GUARD_PROTOCOL,
        guard_contract_verified=contract is not None,
        reader_version=READER_VERSION,
        base_verifier_source_sha256=BASE_VERIFIER_SOURCE_SHA256,
        input_directory=str(directory),
        actuator_step_domain="UPCOMING_PHYSICS_STEP_N",
        integrity_status="VERIFIED" if not failures else "INCOMPLETE_OR_INVALID",
        association_scope="EXCLUDED_TEACHER_TRACE_NOT_NATIVE_RAW_V3",
        nominal_event_count=sequence,
        original_recipe_status=recipe_status,
        runtime_record_status=runtime_record_status,
        source_authenticity="UNKNOWN",
        original_action_begins=summary["action_begins"],
        original_action_ends=summary["action_ends"],
    )
    with (output_directory / "offline-verification.json").open("x") as stream:
        stream.write(json.dumps(report, indent=2, allow_nan=False) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--decode", action="store_true")
    arguments = parser.parse_args()
    result = verify_attempt(
        arguments.input, output_directory=arguments.output, decode=arguments.decode
    )
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["integrity_status"] == "VERIFIED" else 1)
