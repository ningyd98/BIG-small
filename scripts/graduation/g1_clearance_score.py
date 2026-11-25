"""Score a registered complete-CV development slot in fresh, source-pinned readers."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree

from scripts.graduation import g1_visibility_trials
from scripts.graduation.perception_io import ROOT, pinned, read, sha, write

STAGES = (
    "MOVE_ABOVE",
    "APPROACH",
    "GRASP",
    "LIFT",
    "MOVE_TO_REGION",
    "PLACE",
    "RELEASE",
    "RETREAT",
)
SERVO_STAGES = set(STAGES) - {"GRASP", "RELEASE"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def registered_hand_contacts(scene, samples):
    """Derive forbidden partners from the allocated physical assembly, including fixed children."""
    body = ElementTree.parse(scene).find(".//body[@name='object']")
    require(body is not None, "registered scene is missing the object body")
    structures = {
        g.attrib["name"]
        for g in body.iter("geom")
        if int(g.get("contype", 1)) or int(g.get("conaffinity", 1))
    }
    require("object_geom" in structures, "registered object has no physical block")
    structures.remove("object_geom")
    require(structures, "registered marked assembly contains no physical support")
    pairs = Counter()
    hands = {"hand", "left_finger_geom", "right_finger_geom"}
    fingers = hands - {"hand"}
    cube_steps, bilateral_steps, forbidden_steps = [], [], []
    for sample in samples:
        cube_hands = set()
        forbidden = False
        for pair in {tuple(sorted(p)) for p in sample["contact_pairs"]}:
            partners = set(pair)
            if not partners & hands:
                continue
            if "object_geom" in partners:
                cube_hands.update(partners & hands)
            elif partners & structures:
                forbidden = True
            else:
                continue
            pairs["/".join(pair)] += 1
        step = sample["physics_step"]
        if cube_hands:
            cube_steps.append(step)
        if fingers <= cube_hands:
            bilateral_steps.append(step)
        if forbidden:
            forbidden_steps.append(step)
    return {
        "support_geoms": sorted(structures),
        "block_hand_or_finger_steps": cube_steps,
        "block_both_fingers_steps": bilateral_steps,
        "board_or_support_hand_or_finger_steps": forbidden_steps,
        "hand_contact_pairs": dict(pairs),
    }


def valid_duration(value):
    return type(value) in (float, int) and math.isfinite(value) and value >= 0


def feedback_timing(run, audit):
    """Join acquisition, visual provider and outer controller samples at the native servo rate."""
    stages = run["actions"]
    require(tuple(s["skill"] for s in stages) == STAGES, "registered stage order differs")
    by_stage, durations, overruns = {}, [], []
    complete = True
    for stage in stages:
        name = stage["skill"]
        roles = [r for r in run["frame_roles"] if r["label"] == name + "/feedback"]
        traces = [r for r in audit if r.get("phase") == "servo" and r["skill"] == name]
        require(len(traces) <= 1, "duplicate native servo trace")
        trace = traces[0] if traces else {}
        visual, control = trace.get("visual_samples", []), trace.get("control_samples", [])
        measured, unmatched = [], []
        for i, role in enumerate(roles):
            frame_id = role["frame_id"]
            if i >= len(visual) or i >= len(control):
                unmatched.append(frame_id)
                continue
            accepted, native = visual[i], control[i]
            elapsed = native.get("sample_and_ik_s")
            if (
                accepted["observation_id"] != frame_id
                or accepted["checksum_sha256"] != role["checksum_sha256"]
                or native["physics_step"] != role["physics_step"]
                or accepted["sim_time_s"] != role["sim_time_s"]
                or native["sim_time_s"] != role["sim_time_s"]
                or not valid_duration(elapsed)
            ):
                unmatched.append(frame_id)
                continue
            ms = elapsed * 1000
            measured.append(ms)
            if elapsed > 0.100:
                overruns.append(
                    {
                        "skill": name,
                        "frame_id": frame_id,
                        "physics_step": role["physics_step"],
                        "elapsed_ms": ms,
                    }
                )
        counts_match = (
            len(roles) == len(visual) == len(control) == stage.get("feedback_accepted", 0)
        )
        if name in SERVO_STAGES:
            complete &= bool(roles) and counts_match and not unmatched
        else:
            complete &= not (roles or visual or control)
        durations.extend(measured)
        by_stage[name] = {
            "captured": len(roles),
            "visual_samples": len(visual),
            "controller_samples": len(control),
            "measured": len(measured),
            "max_ms": max(measured, default=None),
            "unmatched_frame_ids": unmatched,
        }
    return {
        "complete": bool(complete and not overruns),
        "by_stage": by_stage,
        "captured": sum(s["captured"] for s in by_stage.values()),
        "measured": len(durations),
        "max_sample_and_ik_ms": max(durations, default=None),
        "over_100ms": overruns,
    }


def qualified(result, complete_feedback_ok):
    return g1_visibility_trials.training_success(result) and complete_feedback_ok is True


def verify_generation(tree, generation):
    lock = pinned(tree / "runtime-build.json", generation)
    require(lock["runtime_files_sha256"], "empty runtime file catalogue")
    for name, expected in lock["runtime_files_sha256"].items():
        path = (tree / name).resolve()
        require(
            path.is_relative_to(tree.resolve()) and sha(path) == expected,
            "changed or external runtime source: " + name,
        )
    return lock


def check_issued_endpoint(issue, frame, destination):
    """Recompute the fixed-centre native recipe from blind pixels, the green reference and TCP."""
    from scripts.graduation.g1_mount_score import equal_point

    require(frame["usable"], "issued frame has no usable registered marker")
    inputs, params = issue["inputs"], issue["grounded_step"]["parameters"]
    center = frame["per_id"][str(frame["selected_id"])]["center_m"]
    grasp = frame["tcp_m"]
    equal_point(inputs["object_center_world_m"], center, "issued block centre differs from pixels")
    equal_point(inputs["grasp_tcp_world_m"], grasp, "issued grasp differs from fixed centre TCP")
    equal_point(
        inputs["destination_world_m"], destination, "issued destination differs from green region"
    )
    skill, policy = issue["grounded_step"]["skill"], issue["policy"]
    if skill in {"GRASP", "RELEASE"}:
        require("target_pose" not in params, "gripper-only skill was assigned a motion endpoint")
        return
    xyz = grasp.copy()
    if skill in {"LIFT", "RETREAT"}:
        xyz = [issue["online"]["robot_state"]["tcp_pose"][k] for k in "xyz"]
    if skill in {"MOVE_ABOVE", "MOVE_TO_REGION", "LIFT", "RETREAT"}:
        xyz[2] = max(policy["minimum_height_m"], xyz[2] + policy["clearance_m"])
    if skill in {"MOVE_TO_REGION", "PLACE"}:
        xyz[:2] = destination[:2]
    if skill == "PLACE":
        xyz[2] += destination[2] - inputs["nominal_support_height_m"]
    equal_point(
        [params["target_pose"][k] for k in "xyz"],
        xyz,
        "signed endpoint differs from original recipe",
    )


def local_gate_readback(rows, frames, run):
    """Compare the sealed live decision identity with the acquisition at each callback."""
    seen, clear = set(), set()
    refusals, durations = [], []
    counts = Counter()
    for row in rows:
        role, frame_id, phase = row["skill"], row["frame_id"], row["phase"]
        source = frames.get(frame_id)
        require(
            source is not None
            and row["physics_step"] == source["physics_step"]
            and row["checksum_sha256"] == source["checksum_sha256"],
            "local gate refers to a different frame, step or checksum",
        )
        key = (phase, role, frame_id)
        require(key not in seen, "duplicate local decision for the same frame and skill")
        seen.add(key)
        counts[phase] += 1
        require(valid_duration(row["gate_ms"]), "invalid local check duration")
        durations.append(row["gate_ms"])
        if row["status"] == "CLEAR":
            if phase == "FEEDBACK":
                clear.add((role, frame_id))
        else:
            refusals.append(
                {
                    k: row[k]
                    for k in (
                        "phase",
                        "skill",
                        "frame_id",
                        "physics_step",
                        "status",
                        "reason",
                        "gate_ms",
                    )
                }
            )
    actual = {
        (r["label"].split("/")[0], r["frame_id"])
        for r in run["frame_roles"]
        if r["label"].endswith("/feedback")
    }
    return {
        "by_phase": dict(counts),
        "gate_max_ms": max(durations, default=None),
        "refusals": refusals,
        "captured_feedback_without_clear": sorted(actual - clear),
        "all_captured_feedback_clear": bool(actual) and actual == clear,
    }


PLAN = "4f84f847bc86f68d474d4f81feb0083f6f9e2e9ee93d49e4d5c5509600cc824b"
PLAN_FILE = Path(
    "artifacts/research/process/20261004-ced-development/astra-rounds/"
    "round-g1-complete-cv-repair-20261125/plan.json"
)
PRIVATE = Path("experiments/results/g1-complete-cv-repair-20261125")
MODULE = "scripts.graduation.g1_clearance_score"


def batch_inputs(directory, requested):
    batch = read(directory / "allocation.json")
    require(batch["plan_sha256"] == PLAN, "foreign complete-CV development plan")
    repo = next((p for p in directory.parents if (p / ".git").exists()), None)
    require(
        repo is not None and directory.parent == repo / PRIVATE / "batches",
        "batch outside registered development storage",
    )
    plan = pinned(repo / PLAN_FILE, PLAN)
    specs = {r["id"]: r for r in plan["registration"]["slots"]}
    case_ids = [r["id"] for r in batch["cases"]]
    require(
        len(case_ids) == len(set(case_ids)) and set(case_ids) <= specs.keys(),
        "unexpected or duplicate allocated case",
    )
    require(
        requested and len(set(requested)) == len(requested) and set(requested) <= set(case_ids),
        "unknown, repeated or empty requested case",
    )
    for row in batch["cases"]:
        expected = specs[row["id"]]
        require(
            all(row[k] == expected[k] for k in ("seed", "reset_fixture_center_m", "yaw_rad")),
            "development placement differs from prospective plan",
        )
    generation = batch["runtime_build_sha256"]
    require(re.fullmatch(r"[0-9a-f]{64}", generation), "invalid runtime generation")
    tree = repo / PRIVATE / "builds" / generation / "runtime-source"
    return batch, tree


def checked_case(directory, batch, case_id, tree):
    (row,) = [r for r in batch["cases"] if r["id"] == case_id]
    require(
        row["arm"] == "dual" and row["allocation_file"] == case_id + "/allocation.json",
        "wrong family arm or private case path",
    )
    case_dir = directory / case_id
    allocation = pinned(case_dir / "allocation.json", row["allocation_sha256"])
    case = allocation["case"]
    require(
        allocation["plan_sha256"] == PLAN
        and allocation["runtime_build_sha256"] == batch["runtime_build_sha256"]
        and tuple(case["visual_stages_in_order"]) == STAGES
        and case["visual_seed"] == row["seed"]
        and all(
            case[k] == row[k]
            for k in (
                "id",
                "seed",
                "visual_id",
                "scene_id",
                "family",
                "asset_path",
                "asset_sha256",
                "reset_fixture_center_m",
                "yaw_rad",
            )
        )
        and allocation["asset_sha256"] == row["asset_sha256"] == sha(tree / row["asset_path"]),
        "foreign case, registration or generation",
    )
    raw = case_dir / "instance"
    started = read(raw / "started.json")
    require(
        started["case"] == case_id
        and started["attempt"] == 1
        and started["batch_sha256"] == sha(directory / "allocation.json")
        and started["allocation_sha256"] == row["allocation_sha256"]
        and started["claim_sha256"] == sha(case_dir / "attempt.json")
        and Path(started["source_root"]).resolve() == tree,
        "private worker generation, allocation or claim differs",
    )
    return row, allocation, raw, started


def issued_readback(raw, index, frames, geometry, run, audit, worker):
    from scripts.graduation import dynamic_vision_score as vision
    from scripts.graduation.qualify_archive import archived_color

    from cloud_edge_robot_arm.vision.owner_registration import RegisteredCollectionStepBindingV2

    issues = [r for r in audit if r.get("schema_version") == "native.registered.grounding.v2"]
    if not issues:
        return {"issued": 0, "skills": [], "color_reference": None}
    lease = worker["lease_id"]
    (ref,) = [r for r in run["frame_roles"] if r["label"] == "color_reference"]
    packet = vision.frame_from_row(
        raw, frames[ref["frame_id"]], index["episode"], index["scene"], geometry
    )
    tracker = archived_color(
        packet, geometry, run["color_init_event"], lease, issues[0]["lease_source"]["expires_at"]
    )
    destination = tracker.destination["center"]
    for n, issue in enumerate(issues):
        skill = issue["grounded_step"]["skill"]
        current = frames[issue["observation_id"]]
        bound = RegisteredCollectionStepBindingV2.from_payload(issue["binding"])
        prepared = issue["binding"]["prepared"]
        region = issue["registered_preview"]["region_evidence"]
        require(
            n == issue["index"]
            and skill == STAGES[n]
            and bound.digest() == issue["binding_sha256"]
            and prepared["current_identity"] == issue["identity"]
            and issue["identity"]["lease_id"] == issue["lease_source"]["lease_id"] == lease
            and issue["identity"]["job_id"] == worker["job_id"]
            and prepared["grounded_step"]
            == issue["grounded_step"]
            == issue["executed_contract"]["steps"][n]
            and prepared["observation_id"] == current["frame_id"]
            and prepared["observation_checksum_sha256"]
            == current["checksum_sha256"]
            == issue["checksum_sha256"]
            and prepared["calibration_version"] == geometry["camera"]["calibration_version"]
            and prepared["original_plan_hash"] == issue["original_plan_sha256"]
            and region["reference_observation_id"] == packet.observation_id
            and region["reference_observation_checksum_sha256"] == packet.checksum_sha256,
            "registered issue differs from original, owner, scene, region reference or raw frame",
        )
        check_issued_endpoint(issue, current, destination)
    return {
        "issued": len(issues),
        "skills": [r["grounded_step"]["skill"] for r in issues],
        "color_reference": packet.frame_id,
        "color_evaluated_at": run["color_init_event"]["evaluated_at"],
        "region_center_m": list(destination),
        "object_offset_m": [0.0, 0.0, 0.0],
    }


def window_pixels(windows, frames):
    from scripts.graduation.g1_dual_batch_score import coverage

    result = {}
    for name, window in windows.items():
        first, last = window.get("first_step"), window.get("last_step")
        packets = [] if first is None else [r for r in frames if first <= r["physics_step"] <= last]
        result[name] = {"first_step": first, "last_step": last, "pixels": coverage(packets)}
    return result


def read_slot(directory, batch, tree, case_id, area, lock):
    from scripts.graduation import g1_dual_asset as asset
    from scripts.graduation import g1_dual_batch_score as scorer
    from scripts.graduation import g1_dual_trials as dual
    from scripts.graduation import g1_mount_trials
    from scripts.graduation.g1_formal_runtime import bind_scene

    require(
        ROOT == tree and Path.cwd().resolve() == tree, "score must use the assigned private runtime"
    )
    row, allocation, raw, started = checked_case(directory, batch, case_id, tree)
    geometry = allocation["geometry"]
    require(
        row["family"] == geometry["marker_family"] == asset.FAMILY,
        "pixel reader imported a stale family",
    )
    asset.check_source_binding(geometry, allocation["sources_sha256"])
    calibration = batch["calibration_sha256"]
    require(
        re.fullmatch(r"[0-9a-f]{64}", calibration)
        and allocation.get("calibration_sha256", calibration) == calibration,
        "calibration differs from assigned batch",
    )
    common = {
        "id": case_id,
        "runtime_build_sha256": batch["runtime_build_sha256"],
        "calibration_sha256": calibration,
        "allocation_sha256": row["allocation_sha256"],
        "batch_sha256": sha(directory / "allocation.json"),
        "attempt_sha256": started["claim_sha256"],
        "plan_sha256": PLAN,
        "scope": batch["scope"],
    }
    if not (raw / "receipt.json").is_file():
        interruption = read(raw / "interrupted.json")
        return {
            **common,
            "receipt_sha256": None,
            "interruption_sha256": sha(raw / "interrupted.json"),
            "result": {
                "id": case_id,
                "acquired": False,
                "evidence_status": "INTERRUPTED",
                "interruption": interruption,
            },
            "complete_feedback_ok": False,
            "qualified": False,
        }
    receipt_sha = sha(raw / "receipt.json")
    with bind_scene(row["scene_id"]):
        # The original acquisition audit measures SQLite, reset, commands and dense physics.
        observed = json.loads(
            json.dumps(
                dual.audit_one(raw, row, allocation, common["batch_sha256"]), allow_nan=False
            )
        )
        require(observed["receipt_sha256"] == receipt_sha, "receipt bytes changed during audit")
        anon = scorer.package(
            [(row, allocation, observed, raw)], area / "pixels", registered_scene=True
        )
        blind = area / "blind"
        blind_seal = scorer.blind_reader(tree, anon, blind)
        require(blind_seal["index_sha256"] == sha(anon), "anonymous reader used another case")
        result, _, all_frames = scorer.score_case(
            row, allocation, observed, raw, tree, blind, blind_seal, expected_scene=row["scene_id"]
        )
        frames = {f["frame_id"]: f for f in all_frames}
        seal = pinned(raw / "acquisition-seal.json", observed["capture_sha256"])
        index = pinned(raw / "pixel-index.json", seal["index_sha256"])
        truth = pinned(raw / "offline-truth.json", seal["truth_sha256"])
        run = pinned(raw / "run.json", seal["run_sha256"])
        audit = pinned(raw / "online-audit.json", seal["audit_sha256"])
        native = issued_readback(raw, index, frames, geometry, run, audit, observed["worker"])
    hands = registered_hand_contacts(tree / row["asset_path"], truth["samples"])
    require(
        result["contacts"]["bilateral_cube_steps"] == len(hands["block_both_fingers_steps"]),
        "independent bilateral samples disagree with native scorer",
    )
    result.update(evidence_status="SCORED", hand_contacts=hands)
    live_seal = read(raw / "online-vision-seal.json")
    live = pinned(raw / "online-vision.json", live_seal["online_vision_sha256"])
    require(
        live_seal["acquisition_sha256"] == observed["capture_sha256"]
        and live_seal["attempt_sha256"] == live["attempt_sha256"] == started["claim_sha256"],
        "online measurements refer to another attempt or acquisition",
    )
    for key, trace in live["frames"].items():
        require(
            trace["callers"]
            and g1_visibility_trials.matches_online(frames[key], trace["measurement"]),
            "independent original pixels disagree with live marker record",
        )
    local_seal = read(raw / "local-clearance-seal.json")
    require(
        local_seal["acquisition_seal_sha256"] == observed["capture_sha256"]
        and local_seal["attempt_sha256"] == started["claim_sha256"],
        "unbound local clearance log",
    )
    local = pinned(raw / "local-clearance.json", local_seal["local_clearance_sha256"])
    rows = local if isinstance(local, list) else local["rows"]
    local_facts = local_gate_readback(rows, frames, run)
    timing = feedback_timing(run, audit)
    complete = timing["complete"] and local_facts["all_captured_feedback_clear"]
    imports = g1_mount_trials.project_imports(lock)
    return {
        **common,
        "result": result,
        "receipt_sha256": observed["receipt_sha256"],
        "native_issued": native,
        "registered_window_pixels": window_pixels(result["registered_windows"], all_frames),
        "feedback": timing,
        "local_clearance": local_facts,
        "complete_feedback_ok": complete,
        "qualified": qualified(result, complete),
        "worker": observed["worker"],
        "online_vision_sha256": live_seal["online_vision_sha256"],
        "local_clearance_sha256": local_seal["local_clearance_sha256"],
        "local_clearance_seal_sha256": sha(raw / "local-clearance-seal.json"),
        "cold_pixel_seal_sha256": sha(blind / "seal.json"),
        "cold_join_loaded_sources": imports,
    }


def run_independent(directory, ids):
    batch, tree = batch_inputs(directory, ids)
    verify_generation(tree, batch["runtime_build_sha256"])
    env = dict(
        os.environ,
        PYTHONPATH=os.pathsep.join((str(tree), str(tree / "src"))),
        PYTHONNOUSERSITE="1",
        PYTHONDONTWRITEBYTECODE="1",
    )
    for case_id in ids:
        case = directory / case_id
        root = Path(tempfile.mkdtemp(prefix="independent-readback-", dir=case))
        measurements = []
        proofs = []
        for number in (1, 2):
            area = root / ("reader-" + str(number))
            area.mkdir()
            cmd = [
                sys.executable,
                "-B",
                "-m",
                MODULE,
                str(directory),
                case_id,
                "--read-dir",
                str(area),
            ]
            with (area / "process.log").open("x") as log:
                worker = subprocess.Popen(
                    cmd, cwd=tree, env=env, stdout=log, stderr=subprocess.STDOUT
                )
                code = worker.wait()
            write(
                area / "process.json",
                {"pid": worker.pid, "status": code, "argv": cmd, "cwd": str(tree)},
            )
            if code:
                raise RuntimeError(
                    f"independent reader {number} exited {code}: {area / 'process.log'}"
                )
            measurements.append(read(area / "result.json"))
            proofs.append(
                {
                    "area": str(area.relative_to(case)),
                    "process_sha256": sha(area / "process.json"),
                    "result_sha256": sha(area / "result.json"),
                    "pid": worker.pid,
                }
            )
        require(
            proofs[0]["result_sha256"] == proofs[1]["result_sha256"]
            and proofs[0]["pid"] != proofs[1]["pid"],
            "independent cold processes disagree",
        )
        final = {**measurements[0], "independent_reads": proofs}
        out = root / "verified.json"
        write(out, final)
        destination = case / "independent-score.json"
        try:
            os.link(out, destination)
        except FileExistsError:
            previous = read(destination)
            require(
                {k: v for k, v in previous.items() if k != "independent_reads"} == measurements[0],
                "prior published score differs from fresh two-process readback",
            )
        print(
            f"{case_id} qualified={final['qualified']} "
            f"receipt={final['receipt_sha256']} score={destination}"
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch", type=Path)
    parser.add_argument("case_id", nargs="+")
    parser.add_argument("--read-dir", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    directory = args.batch.resolve()
    if args.read_dir is None:
        run_independent(directory, args.case_id)
    else:
        require(len(args.case_id) == 1, "a cold process reads one sealed case")
        batch, tree = batch_inputs(directory, args.case_id)
        lock = verify_generation(tree, batch["runtime_build_sha256"])
        result = read_slot(directory, batch, tree, args.case_id[0], args.read_dir, lock)
        write(args.read_dir / "result.json", result)


if __name__ == "__main__":
    main()
