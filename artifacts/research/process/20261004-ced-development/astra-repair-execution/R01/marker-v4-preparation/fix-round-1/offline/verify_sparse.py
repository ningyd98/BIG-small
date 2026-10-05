"""Post-terminal custom sparse RGBD replay only; no simulator entry point.

Truth is used for association and comparison, never supplied to the detector.
This reader grants no source authority, native or continuous/future certificate.
"""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import importlib.util
import json
import math
import struct
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from cloud_edge_robot_arm.research import mujoco_state_guard as state_guard
from cloud_edge_robot_arm.simulation.mujoco.backend import PhysicsStepObservation
from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
    CompletionCriteria,
    sample_physical_observation,
)
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.pose_markers import PoseMarkerRegistration, detect_pose_marker

HERE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[9]
BASE = HERE.parents[1]
DEVELOPMENT = ROOT / "artifacts/research/process/20261004-ced-development"
OLD = DEVELOPMENT / "t7b-continuous-visibility-v3/fix-round-1/attempt-1"
PROTOCOL = "research.custom-sparse-guarded-marker-v4.v1"
HEADER_SHA = "d856dd0e1093278709239cb6e5cd312872b1f41dfd79d5d87a3b36b8de8e4213"
HELPER_SHA = "35ae741fa995715749133485eab4ef6ec70e28a9854de440e8489bd68f65314e"
ASSET_SHA = "045ce032032426ec6130348ee75e5f53b7db02699fc1f39558727edd63f67e0d"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def same(left, right):
    return json.dumps(left, sort_keys=True, separators=(",", ":"), allow_nan=False) == json.dumps(
        right, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def require(value, reason):
    if not value:
        raise ValueError(reason)


def identity(row):
    return {name: row[name] for name in ("episode_id", "physics_step", "sim_time_s")}


def unique(rows, key):
    result = {}
    for row in rows:
        k = key(row)
        require(k not in result, f"duplicate event key {k}")
        result[k] = row
    return result


def validate_index(rows, summary, selected, final, episode):
    require(type(final) is int and final >= 0, "invalid final range")
    require(
        selected == sorted(set(selected))
        and all(type(s) is int and 0 <= s <= final for s in selected),
        "invalid selected step inventory",
    )
    callbacks = [r for r in rows if r["event"] == "PHYSICAL_CALLBACK"]
    begins = unique([r for r in rows if r["event"] == "BEGIN"], lambda r: r["physics_step"])
    ends = unique([r for r in rows if r["event"] == "END"], lambda r: r["physics_step"])
    finishes = [r for r in rows if r["event"] == "FINISH"]
    require(
        all(r["event"] in {"PHYSICAL_CALLBACK", "BEGIN", "END", "FINISH"} for r in rows),
        "retained failure or unknown index event",
    )
    require(
        [r["physics_step"] for r in callbacks] == list(range(final + 1)),
        "full physical callback range mismatch",
    )
    require(
        sorted(begins) == selected == sorted(ends), "selected allocated/saved denominator mismatch"
    )
    require(
        len(finishes) == 1 and same(finishes[0].get("summary"), summary),
        "index FINISH/summary mismatch",
    )
    require(
        summary["status"] == "COMPLETE"
        and summary["recipe_range_status"] == "MATCH"
        and summary["expected_physics_steps"] == final
        and summary["final_step"] == final,
        "exact recipe range incomplete",
    )
    require(
        summary["physical_callback_attempts"] == final + 1 == summary["physical_callbacks"],
        "physical callback counter mismatch",
    )
    require(
        summary["allocated_steps"] == selected == summary["saved_steps"]
        and not summary["failed_steps"]
        and not summary["missing_selected_steps"]
        and not summary["publication_errors"],
        "retained acquisition denominator incomplete",
    )
    previous = -math.inf
    for callback in callbacks:
        step = callback["physics_step"]
        require(
            callback["episode_id"] == episode
            and type(callback["selected"]) is bool
            and callback["selected"] == (step in begins),
            "callback identity/selection mismatch",
        )
        require(
            math.isfinite(callback["sim_time_s"]) and callback["sim_time_s"] > previous,
            "callback simulation clock invalid",
        )
        previous = callback["sim_time_s"]
        if step in begins:
            require(
                same(identity(callback), identity(begins[step]))
                and same(identity(callback), identity(ends[step])),
                "selected frame/callback identity mismatch",
            )
            require(
                type(begins[step]["capture_monotonic_begin_ns"]) is int
                and type(ends[step]["capture_monotonic_end_ns"]) is int
                and begins[step]["capture_monotonic_begin_ns"]
                <= ends[step]["capture_monotonic_end_ns"],
                "index capture bracket invalid",
            )
    require(
        summary["episode_id"] == episode and summary["final_sim_time_s"] == previous,
        "index terminal episode/time mismatch",
    )
    return ends


def validate_operation_pair(begin, end, episode):
    b, e = begin["source"], end["source"]
    require(b["phase"] == "BEGIN" and e["phase"] == "END", "operation lifecycle incomplete")
    require(
        type(b["operation_id"]) is int
        and b["operation_id"] == e["operation_id"]
        and b["kind"] == e["kind"]
        and b["kind"] in {"PHYSICS", "CONTROL", "COMMAND", "CAPTURE"},
        "operation id/kind mismatch",
    )
    require(
        b["episode_id"] == e["episode_id"] == episode and same(b["parameters"], e["parameters"]),
        "operation episode/parameters mismatch",
    )
    require(
        begin["record_seq"] < end["record_seq"]
        and b["result"] is None
        and b["error"] is None
        and e["error"] is None
        and b["error_type"] is None
        and e["error_type"] is None,
        "operation publication/failure mismatch",
    )
    advance = 1 if b["kind"] == "PHYSICS" else 0
    require(
        type(b["physics_step"]) is int
        and type(e["physics_step"]) is int
        and b["physics_step"] + advance == e["physics_step"],
        "operation step bracket mismatch",
    )
    require(
        (e["sim_time_s"] > b["sim_time_s"]) if advance else (e["sim_time_s"] == b["sim_time_s"]),
        "operation simulation-time bracket mismatch",
    )


def validate_full_state(full, before, array_fields, expected_identity):
    require(same(identity(full), expected_identity), "full capture identity mismatch")
    require(
        before["physical_step"] == full["physics_step"]
        and before["sim_time_s"] == full["sim_time_s"]
        and before.get("episode_id", full["episode_id"]) == full["episode_id"],
        "protected scalar/full capture identity mismatch",
    )
    camera = full["camera_state"]
    require(
        set(camera) == {"sim_time_s", "qpos", "qvel", "act", "ctrl"}
        and camera["sim_time_s"] == full["sim_time_s"],
        "full camera inventory/time mismatch",
    )
    fields = unique(array_fields, lambda f: f["name"])
    digest = hashlib.sha256(struct.pack("<d", camera["sim_time_s"]))
    for name, count in (("qpos", 37), ("qvel", 33), ("act", 0), ("ctrl", 9)):
        values = camera[name]
        require(
            type(values) is list
            and len(values) == count
            and all(type(v) in {int, float} and math.isfinite(v) for v in values),
            "full camera numeric length/values invalid: " + name,
        )
        raw = struct.pack("<" + "d" * count, *values)
        digest.update(struct.pack("<I", count))
        digest.update(raw)
        f = fields[name]
        require(
            f["shape"] == [count]
            and f["dtype"] == "<f8"
            and f["status"] == ("DATA_BACKED" if count else "EMPTY")
            and f["byte_sha256"] == (sha(raw) if count else None),
            "full camera/guard byte domain mismatch: " + name,
        )
    require(
        digest.hexdigest() == before["physics_state_sha256"],
        "full camera physical-state hash mismatch",
    )


def compare_recorded(old, new):
    def normalize(row):
        return {k: v for k, v in row.items() if k != "episode_id"}

    differences = [
        i
        for i, (a, b) in enumerate(zip(old, new, strict=False))
        if not same(normalize(a), normalize(b))
    ]
    return dict(
        old_rows=len(old),
        new_rows=len(new),
        different_rows=len(differences) + abs(len(old) - len(new)),
        different_row_indices=differences,
        excluded_fields=["episode_id"],
        scope="ALL_RECORDED_FIELDS_ONLY_NOT_ALL_INTERNAL_RUNTIME_STATE",
    )


def compare_markers(selected, old, new):
    require(
        set(selected) <= old.keys() and set(selected) == new.keys(),
        "fixed marker denominator incomplete",
    )
    return dict(
        selected_denominator=len(selected),
        old_status_counts=dict(Counter(old[s] for s in selected)),
        new_status_counts=dict(Counter(new[s] for s in selected)),
        transitions=dict(Counter(old[s] + "->" + new[s] for s in selected)),
    )


def load_helper():
    path = DEVELOPMENT / "t7b-continuous-visibility-v3/verify_offline.py"
    require(sha(path.read_bytes()) == HELPER_SHA, "immutable helper source differs")
    spec = importlib.util.spec_from_file_location("v3_pure_reader_helpers", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_journal(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


def source_contract(attempt, header, summary):
    require(
        sha((attempt / "execution-header.json").read_bytes())
        == HEADER_SHA
        == summary["execution_header_sha256"]
        == sha((attempt.parent / "header.json").read_bytes()),
        "execution header pin mismatch",
    )
    require(
        header["protocol"] == summary["protocol"] == PROTOCOL
        and header["scope"] == "EXCLUDED_SAME_COMPONENT_SPARSE_MARKER_V4_PILOT"
        and header["raw_v3_status"] == "CUSTOM_PROTOCOL_NOT_RAW_V3",
        "custom sparse protocol mismatch",
    )
    require(
        header["source_authenticity"] == "UNKNOWN"
        and header["independent_calibration_group"] is False
        and header["native_admission"] == "NOT_PROMOTED"
        and header["formal_accepted"] is False,
        "authority boundary mismatch",
    )
    require(
        header["expected_physics_steps"] == 4806
        and header["expected_physics_steps_is_admission_gate"] is True
        and header["range_policy"] == "RETAIN_ALL_ACTUAL_CALLBACKS_REQUIRE_EXACT_ORIGINAL_HORIZON",
        "frozen horizon policy mismatch",
    )
    sources = json.loads((attempt.parent / "execution-source-hashes.json").read_text())
    archives = json.loads((attempt.parent / "execution-archive-index.json").read_text())
    require(
        sha((attempt.parent / "execution-source-hashes.json").read_bytes())
        == header["source_manifest_sha256"]
        and sha((attempt.parent / "execution-archive-index.json").read_bytes())
        == header["source_archive_index_sha256"],
        "source metadata pins mismatch",
    )
    require(
        sources.keys() == archives.keys() and len(sources) == header["source_count"] == 34,
        "necessary source inventory mismatch",
    )
    total = 0
    for name, pin in sources.items():
        live = (ROOT / name).read_bytes()
        arc = (ROOT / archives[name]["archive"]).read_bytes()
        require(
            sha(live) == sha(arc) == pin == archives[name]["sha256"]
            and len(live) == archives[name]["bytes"],
            "source/archive mismatch: " + name,
        )
        total += len(live)
    require(total == header["source_bytes"], "source byte inventory mismatch")
    for member in header["environment"]["files"].values():
        require(
            sha(Path(member["path"]).read_bytes()) == member["sha256"],
            "environment byte pin mismatch",
        )
    selection_path = BASE / "selection-manifest.json"
    require(
        sha(selection_path.read_bytes()) == header["selection_manifest_sha256"],
        "selection manifest pin mismatch",
    )
    selection = json.loads(selection_path.read_text())
    require(
        selection["selected_steps"] == header["selected_steps"]
        and len(selection["selected_steps"]) == header["selected_frame_budget"] == 201,
        "fixed201 selection mismatch",
    )
    for member in selection["input_pins"]:
        require(
            sha((ROOT / member["path"]).read_bytes()) == member["sha256"]
            and (ROOT / member["path"]).stat().st_size == member["bytes"],
            "old input lineage pin mismatch: " + member["path"],
        )
    for member in selection["original_frames"]:
        original = (ROOT / member["path"]).read_bytes()
        require(
            sha(original) == member["sha256"] and len(original) == member["bytes"],
            "old selected frame lineage mismatch",
        )
    require(
        sha((BASE / "scene_pose_marker_outboard_v4.xml").read_bytes())
        == ASSET_SHA
        == header["asset_sha256"],
        "asset lineage differs",
    )
    require(
        header["marker_registration"]
        == dict(marker_id=7, marker_size_m=0.075, marked_asset_sha256=ASSET_SHA),
        "registered decoder geometry differs",
    )
    require(
        sha(Path(state_guard.__file__).read_bytes()) == header["guard_core_sha256"],
        "loaded guard source differs",
    )
    contract = state_guard.MujocoStateContract(
        Path(header["guard_headers"]["mjxmacro.h"]).read_bytes(),
        Path(header["guard_headers"]["mjdata.h"]).read_bytes(),
        header["guard_binding_sha256"],
        header["environment"]["mujoco_version"],
    )
    return contract, selection


def validate_runtime(attempt, records, header, contract):
    r = json.loads((attempt / "runtime-preflight.json").read_text())
    setup = [row for row in records if row["event"] == "SETUP_BEGIN"]
    require(
        len(setup) == 1 and setup[0] == records[0] and same(setup[0]["runtime_preflight"], r),
        "setup/runtime preflight join differs",
    )
    require(
        r["scope"] == "ACTUAL_MODULE_IMPORT_ONLY_BEFORE_FIRST_MODEL_RESET_CAMERA"
        and r["models_or_data_instantiated"] == 0
        and r["actual_mujoco_version"] == header["environment"]["mujoco_version"] == "3.3.7"
        and r["actual_numpy_version"] == header["environment"]["numpy_version"]
        and r["contract_digest"] == contract.digest,
        "runtime version/scope/contract differs",
    )
    require(
        same(r["public_module_origin"], header["environment"]["files"]["mujoco/__init__.py"]),
        "public module origin mismatch",
    )
    require(
        set(r["binding_origins"]) == {"_structs", "_functions", "_enums"},
        "binding inventory mismatch",
    )
    for name, member in r["binding_origins"].items():
        require(
            same(member, header["environment"]["files"]["mujoco/" + Path(member["path"]).name]),
            "binding origin mismatch: " + name,
        )
    for name in ("MjModel", "MjData"):
        require(
            r["classes"][name]
            == dict(module="mujoco._structs", name=name, public_binding_identity=True),
            "runtime class record mismatch",
        )


def owner(step, actions):
    matches = [
        o
        for (o, event), r in actions.items()
        if event == "ACTION_END" and r["start_step"] < step <= r["end_step"]
    ]
    require(len(matches) <= 1, "overlapping action physical spans")
    return matches[0] if matches else None


def validate_trace(records, summary, terminal, teacher, index_rows, ends, header, helper, contract):
    episode = terminal["episode_id"]
    final = terminal["final_step"]
    selected = header["selected_steps"]
    require(
        [r["record_seq"] for r in records] == list(range(1, len(records) + 1)),
        "full journal sequence mismatch",
    )
    previous = -1
    for r in records:
        c = r["clock"]
        b, e = c["monotonic_before_ns"], c["monotonic_after_ns"]
        require(
            type(b) is int and type(e) is int and previous <= b <= e,
            "journal monotonic brackets invalid",
        )
        previous = e
        require(
            not r["event"].endswith("FAILED") and not r["event"].endswith("FAILURE"),
            "retained journal failure",
        )
    operations = [r for r in records if r["event"] == "OPERATION"]
    ledger_keys = (
        "operation_id",
        "kind",
        "phase",
        "episode_id",
        "physics_step",
        "error_type",
        "error",
    )
    require(
        same(
            [{k: r["source"][k] for k in ledger_keys} for r in operations],
            terminal["operation_ledger"],
        )
        and not terminal["operation_observer_failures"],
        "journal/terminal operation ledger mismatch",
    )
    pairs = unique(operations, lambda r: (r["source"]["operation_id"], r["source"]["phase"]))
    ids = sorted(set(k[0] for k in pairs))
    require(
        ids == list(range(1, len(ids) + 1)) and len(pairs) == 2 * len(ids),
        "full operation allocated/terminal denominator mismatch",
    )
    for operation_id in ids:
        validate_operation_pair(
            pairs[(operation_id, "BEGIN")], pairs[(operation_id, "END")], episode
        )
    physics = unique(
        [
            r
            for r in operations
            if r["source"]["kind"] == "PHYSICS" and r["source"]["phase"] == "END"
        ],
        lambda r: r["source"]["physics_step"],
    )
    controls = unique(
        [
            r
            for r in operations
            if r["source"]["kind"] == "CONTROL" and r["source"]["phase"] == "END"
        ],
        lambda r: r["source"]["physics_step"] + 1,
    )
    actuators = unique(
        [r for r in records if r["event"] == "ACTUATOR"], lambda r: r["source"]["physics_step"]
    )
    require(
        sorted(physics) == sorted(controls) == sorted(actuators) == list(range(1, final + 1)),
        "all physical/control/actuator steps incomplete",
    )
    begins = unique(
        [r for r in records if r["event"] == "ACQUISITION_BEGIN"], lambda r: r["physics_step"]
    )
    acquisitions = unique(
        [r for r in records if r["event"] == "ACQUISITION_END"], lambda r: r["physics_step"]
    )
    require(
        sorted(begins) == sorted(acquisitions) == selected
        and summary["acquisition_allocated"] == summary["acquisition_completed"] == len(selected)
        and summary["acquisition_failed"] == 0,
        "journal acquisition allocated/terminal denominator mismatch",
    )
    actions = unique(
        [r for r in records if r["event"] in {"ACTION_BEGIN", "ACTION_END"}],
        lambda r: (r["action_ordinal"], r["event"]),
    )
    teacher_actions = unique(
        [r for r in records if r["event"] == "TEACHER_ACTION"], lambda r: r["action_ordinal"]
    )
    recipe, failures = helper.verify_original_recipe(
        header, actions, teacher_actions, summary, terminal
    )
    require(
        not failures and recipe == "COMPLETE_ORIGINAL_120_9_2",
        "original recipe invalid: " + str(failures),
    )
    require(
        sorted(teacher_actions) == list(range(1, 10))
        and len(actions) == 18
        and summary["action_failed"] == 0,
        "full action denominator mismatch",
    )
    for o in range(1, 10):
        b, e = actions[(o, "ACTION_BEGIN")], actions[(o, "ACTION_END")]
        require(
            b["episode_id"] == e["episode_id"] == episode
            and b["start_step"] == e["start_step"]
            and b["action_type"] == e["action_type"]
            and b["record_seq"] < e["record_seq"],
            "action span identity mismatch",
        )
        require(
            teacher_actions[o]["source"]["episode_id"] == episode
            and teacher_actions[o]["source"]["start_step"] == b["start_step"]
            and teacher_actions[o]["source"]["end_step"] == e["end_step"],
            "teacher action span mismatch",
        )
        require(
            same(teacher_actions[o]["source"]["result"], teacher["actions"][o - 1]),
            "teacher action evidence mismatch",
        )
    physical = {0: begins[0]["physical_source"]}
    callbacks = {r["physics_step"]: r for r in index_rows if r["event"] == "PHYSICAL_CALLBACK"}
    for step in range(1, final + 1):
        p, c, a = physics[step], controls[step], actuators[step]
        pb, cb = (
            pairs[(p["source"]["operation_id"], "BEGIN")],
            pairs[(c["source"]["operation_id"], "BEGIN")],
        )
        physical[step] = p["source"]["result"]["physics_state"]
        ident = identity(callbacks[step])
        prior = identity(callbacks[step - 1])
        require(
            same(identity(p["source"]), ident)
            and same(identity(physical[step]), ident)
            and same(identity(pb["source"]), prior)
            and same(identity(c["source"]), prior)
            and same(identity(cb["source"]), prior),
            "full physical/control begin/end identity mismatch",
        )
        require(
            same(
                identity(a["source"]),
                dict(episode_id=episode, physics_step=step, sim_time_s=prior["sim_time_s"]),
            )
            and a["control_operation_id"] == c["source"]["operation_id"]
            and same(a["source"], c["source"]["result"]["control_state"]),
            "upcoming-n actuator/control mismatch",
        )
        require(
            a["action_ordinal"] == owner(step, actions)
            and cb["record_seq"]
            < c["record_seq"]
            < a["record_seq"]
            < pb["record_seq"]
            < p["record_seq"],
            "full control/actuator/physics owner or sequence mismatch",
        )
    command_rows = [
        command
        for r in operations
        if r["source"]["kind"] == "COMMAND" and r["source"]["phase"] == "END"
        for command in r["source"]["result"]["command_records"]
    ]
    require(
        same(command_rows, terminal["commands"])
        and [c["command_seq"] for c in command_rows] == list(range(1, len(command_rows) + 1))
        and len(command_rows) == 743,
        "command inventory/source mismatch",
    )
    require(
        terminal["final_sim_time_s"] == physical[final]["sim_time_s"]
        and len(teacher["physical_samples"]) == final + 1
        and summary["whole_step_capture_calls"] == len(selected),
        "terminal/evidence horizon mismatch",
    )
    criteria = CompletionCriteria("object", "target_region")
    for step in range(final + 1):
        sample = asdict(
            sample_physical_observation(PhysicsStepObservation(**physical[step]), criteria)
        )
        require(
            same(sample, teacher["physical_samples"][step]),
            "physical scorer evidence differs at step " + str(step),
        )
    full_states = []
    for step in selected:
        b, e = begins[step], acquisitions[step]
        camera = e["camera"]
        saved = {k: v for k, v in ends[step].items() if k != "event"}
        require(
            same(identity(b), identity(e))
            and same(identity(b), identity(callbacks[step]))
            and same(b["physical_source"], physical[step]),
            "capture physical identity/source mismatch",
        )
        require(
            b["action_ordinal"] == e["action_ordinal"] == owner(step, actions)
            and b["control_operation_id"] == e["control_operation_id"]
            and b["physics_operation_id"] == e["physics_operation_id"],
            "capture unique action/operation ownership mismatch",
        )
        if step:
            require(
                b["control_operation_id"] == controls[step]["source"]["operation_id"]
                and b["physics_operation_id"] == physics[step]["source"]["operation_id"]
                and physics[step]["record_seq"] < b["record_seq"],
                "capture operation join mismatch",
            )
        else:
            require(
                b["control_operation_id"] is None and b["physics_operation_id"] is None,
                "initial capture operation identity differs",
            )
        require(
            same(e["saved"], saved) and e["record_seq"] > b["record_seq"],
            "acquisition/index END saved identity mismatch",
        )
        helper.verify_camera_guard(camera, contract)
        require(
            camera["state_unchanged"] is True
            and camera["before_state"]["sensor_noise_std_m"] == 0.0,
            "capture non-mutating/noise contract mismatch",
        )
        full = camera["full_capture_state"]
        validate_full_state(
            full, camera["before_state"], camera["before_guard"]["arrays"]["fields"], identity(e)
        )
        full_states.append(full)
        lo, hi = (
            ends[step]["capture_monotonic_end_ns"],
            next(
                r["capture_monotonic_begin_ns"]
                for r in index_rows
                if r["event"] == "BEGIN" and r["physics_step"] == step
            ),
        )
        require(
            b["clock"]["monotonic_after_ns"]
            <= hi
            <= camera["capture_monotonic_begin_ns"]
            <= camera["capture_monotonic_end_ns"]
            <= lo
            <= e["clock"]["monotonic_before_ns"],
            "capture complete nested clocks mismatch",
        )
    return (
        physical,
        actuators,
        dict(
            journal_records=len(records),
            operations=len(ids),
            physical_callbacks=final + 1,
            selected_frames=len(selected),
            actions=9,
            commands=len(command_rows),
            recipe=recipe,
            all_full_capture_states_verified=len(full_states),
            all_teacher_physical_samples_verified=final + 1,
            guard_scope="ALL_RECORDED_DATA_BACKED_ARRAY_DOMAINS_AND_ALL_PROTECTED_COMPONENTS",
        ),
    )


def inventory(paths):
    return {
        str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p): dict(
            bytes=p.stat().st_size, sha256=sha(p.read_bytes())
        )
        for p in sorted(set(paths))
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--decode-once", action="store_true", required=True)
    parser.parse_args()
    output = HERE / "offline-verification.json"
    markers = HERE / "offline-markers.jsonl"
    require(
        not output.exists() and not markers.exists(),
        "single reader output already exists; no decode retry",
    )
    attempt = HERE.parent / "pilot-protocol/attempt-1"
    summary = json.loads((attempt / "summary.json").read_text())
    terminal = json.loads((attempt / "terminal.json").read_text())
    header = json.loads((attempt / "execution-header.json").read_text())
    helper = load_helper()
    contract, selection = source_contract(attempt, header, summary)
    source_files = [
        ROOT / name
        for name in json.loads((attempt.parent / "execution-source-hashes.json").read_text())
    ]
    input_paths = list(attempt.rglob("*"))
    input_paths = (
        [p for p in input_paths if p.is_file()]
        + source_files
        + [
            attempt.parent / "header.json",
            attempt.parent / "execution-source-hashes.json",
            attempt.parent / "execution-archive-index.json",
            BASE / "selection-manifest.json",
            OLD / "nominal-journal.jsonl.gz",
            OLD / "terminal.json",
            OLD / "teacher-evidence.json",
            DEVELOPMENT / "astra-repair-execution/R01/offline/offline-markers.jsonl",
            Path(__file__),
        ]
    )
    before = inventory(input_paths)
    (HERE / "input-inventory-before.json").write_text(json.dumps(before, indent=2) + "\n")
    records = read_journal(attempt / "nominal-journal.jsonl.gz")
    validate_runtime(attempt, records, header, contract)
    index_rows = [
        json.loads(line) for line in (attempt / "whole-step/index.jsonl").read_text().splitlines()
    ]
    series = json.loads((attempt / "whole-step/summary.json").read_text())
    selected = header["selected_steps"]
    ends = validate_index(
        index_rows, series, selected, terminal["final_step"], terminal["episode_id"]
    )
    teacher = json.loads((attempt / "teacher-evidence.json").read_text())
    physical, actuators, trace = validate_trace(
        records, summary, terminal, teacher, index_rows, ends, header, helper, contract
    )
    old_records = read_journal(OLD / "nominal-journal.jsonl.gz")
    old_terminal = json.loads((OLD / "terminal.json").read_text())
    old_teacher = json.loads((OLD / "teacher-evidence.json").read_text())
    old_physical = [
        r["physical_source"]
        for r in old_records
        if r["event"] == "ACQUISITION_BEGIN" and r["physics_step"] == 0
    ] + [
        r["source"]["result"]["physics_state"]
        for r in old_records
        if r["event"] == "OPERATION"
        and r["source"]["kind"] == "PHYSICS"
        and r["source"]["phase"] == "END"
    ]
    comparison = dict(
        physical_states=compare_recorded(
            old_physical, [physical[s] for s in range(terminal["final_step"] + 1)]
        ),
        actuator_states=compare_recorded(
            [r["source"] for r in old_records if r["event"] == "ACTUATOR"],
            [actuators[s]["source"] for s in range(1, terminal["final_step"] + 1)],
        ),
        commands=compare_recorded(old_terminal["commands"], terminal["commands"]),
        scorer_samples=compare_recorded(
            old_teacher["physical_samples"], teacher["physical_samples"]
        ),
    )
    old_markers = {
        r["physics_step"]: r["decode_status"]
        for r in map(
            json.loads,
            (DEVELOPMENT / "astra-repair-execution/R01/offline/offline-markers.jsonl")
            .read_text()
            .splitlines(),
        )
    }
    registration = PoseMarkerRegistration(**header["marker_registration"])
    statuses = {}
    reasons = Counter()
    ids = set()
    camera_context = None
    valid = 0
    compressed_bytes = original_bytes = 0
    decoder_calls = 0
    with markers.open("x") as stream:
        for step in selected:
            measured = dict(
                physics_step=step,
                old_decode_status=old_markers[step],
                decode_status="UNAVAILABLE_INVALID_RAW",
            )
            try:
                row = ends[step]
                require(row["file"] == f"frames/{step:07d}.json.gz", "noncanonical raw path")
                compressed = (attempt / "whole-step" / row["file"]).read_bytes()
                raw = gzip.decompress(compressed)
                require(
                    sha(compressed) == row["compressed_sha256"]
                    and sha(raw) == row["original_sha256"]
                    and len(raw) == row["original_bytes"]
                    and len(compressed) == row["compressed_bytes"],
                    "original raw bytes/hash mismatch",
                )
                observation = RGBDObservation.model_validate_json(raw)
                require(
                    observation.episode_id == terminal["episode_id"]
                    and observation.sim_time_s == row["sim_time_s"]
                    and observation.observation_id == row["observation_id"]
                    and observation.checksum_sha256 == row["checksum"]
                    and observation.observation_id not in ids,
                    "original observation identity/checksum mismatch",
                )
                require(
                    (observation.width, observation.height) == (640, 480),
                    "original camera dimensions differ",
                )
                context = (
                    observation.width,
                    observation.height,
                    observation.intrinsics,
                    observation.camera_to_world,
                    observation.calibration_version,
                    observation.scene_id,
                    observation.source,
                )
                require(
                    camera_context is None or camera_context == context,
                    "original camera context changed",
                )
                camera_context = context
                ids.add(observation.observation_id)
                require(
                    row["pass_state_hashes"]
                    == [
                        next(
                            r["camera"]["before_state"]["physics_state_sha256"]
                            for r in records
                            if r["event"] == "ACQUISITION_END" and r["physics_step"] == step
                        )
                    ]
                    * 2,
                    "original camera passes differ",
                )
                measured.update(
                    episode_id=observation.episode_id,
                    sim_time_s=observation.sim_time_s,
                    observation_id=observation.observation_id,
                    checksum=observation.checksum_sha256,
                    compressed_sha256=sha(compressed),
                    original_sha256=sha(raw),
                    raw_member_sha256={
                        name: sha(base64.b64decode(getattr(observation, field), validate=True))
                        for name, field in [
                            ("rgb.png", "rgb_png_base64"),
                            ("depth.f32", "depth_float32_base64"),
                            ("valid_mask.u8", "valid_mask_base64"),
                        ]
                    },
                )
                valid += 1
                compressed_bytes += len(compressed)
                original_bytes += len(raw)
                measured["decode_status"] = "DECODE_ERROR"
                decoder_calls += 1
                estimate = detect_pose_marker(observation, registration)
                marker = asdict(estimate)
                marker["captured_at"] = estimate.captured_at.isoformat()
                measured.update(marker=marker, decode_status=estimate.status)
                reasons[estimate.reason] += 1
            except Exception as error:
                measured["failure"] = dict(type=type(error).__name__, message=str(error))
                reasons[measured["decode_status"]] += 1
            statuses[step] = measured["decode_status"]
            stream.write(json.dumps(measured, allow_nan=False) + "\n")
            stream.flush()
    after = inventory(input_paths)
    require(same(before, after), "immutable input changed during offline analysis")
    (HERE / "input-inventory-after.json").write_text(json.dumps(after, indent=2) + "\n")
    comparison["marker_status"] = compare_markers(selected, old_markers, statuses)
    result = dict(
        reader_version="research.custom-sparse-marker-v4-offline.v1",
        integrity_status="VERIFIED_SPARSE_RAW_AND_RECORDED_TRACE"
        if valid == 201
        else "INCOMPLETE_INVALID_RAW",
        scope="EXCLUDED_SAME_COMPONENT_SPARSE_VISIBILITY_DIAGNOSIS",
        source_authenticity="UNKNOWN",
        independent_calibration_group=False,
        formal_accepted=False,
        native_admission="NOT_PROMOTED",
        continuous_visibility="NOT_ESTABLISHED",
        future_stability="UNAVAILABLE",
        external_utc_uncertainty="UNAVAILABLE",
        original_max_sample_gap_s=0.005,
        sparse_max_gap_s=series["sparse_max_gap_s"],
        selected_denominator=201,
        raw_verified_frames=valid,
        decoder_calls=decoder_calls,
        decoder_status_counts=dict(Counter(statuses.values())),
        decoder_reason_counts=dict(reasons),
        trace=trace,
        comparison=comparison,
        source_count=34,
        environment_pins=len(header["environment"]["files"]),
        execution_header_sha256=HEADER_SHA,
        detector_source_sha256=sha(
            Path(
                __import__("cloud_edge_robot_arm.vision.pose_markers", fromlist=[""]).__file__
            ).read_bytes()
        ),
        reader_source_sha256=sha(Path(__file__).read_bytes()),
        helper_source_sha256=HELPER_SHA,
        asset_sha256=ASSET_SHA,
        marker_registration=header["marker_registration"],
        registration_digest=registration.digest(),
        original_json_bytes=original_bytes,
        compressed_frame_bytes=compressed_bytes,
        immutable_input_files=len(before),
        immutable_input_bytes=sum(p["bytes"] for p in before.values()),
        immutable_inputs_unchanged=True,
        actual_simulator_calls=0,
        acquisition_script_wall_s=summary["wall_s"]
        if "wall_s" in summary
        else summary.get("wall_elapsed_s", summary.get("wall_seconds")),
        camera_counts_scope="RECORDED_COUNTS_ONLY_NO_MEASURED_RENDER_TOTAL",
        no_old_pose_substitution=True,
    )
    output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(
        json.dumps(
            {
                k: result[k]
                for k in (
                    "integrity_status",
                    "selected_denominator",
                    "raw_verified_frames",
                    "decoder_calls",
                    "decoder_status_counts",
                    "comparison",
                )
            },
            allow_nan=False,
        )
    )


if __name__ == "__main__":
    main()
