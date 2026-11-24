"""Independently score the preregistered four-pair G1 simulation from its frozen originals."""

from __future__ import annotations

import argparse
import os
import sqlite3
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from itertools import combinations
from pathlib import Path

from scripts.graduation import dynamic_vision_score as vision
from scripts.graduation import g1_dual_batch_score as dual
from scripts.graduation import g1_formal_runtime as build
from scripts.graduation import g1_formal_trials as trials
from scripts.graduation import g1_mount_trials as mounts
from scripts.graduation.perception_io import pinned, read, sha, write

from cloud_edge_robot_arm.research.native_collection_grounding import validate_camera

PLAN_SHA = build.PLAN_SHA
SCOPE = build.SCOPE
REPORTS = ("paired-results.public.json", "live-visibility.public.json")
SCORE_FILES = {
    "scripts/graduation/g1_formal_score.py",
    "scripts/graduation/g1_dual_batch_score.py",
    "scripts/graduation/g1_dual_pixel_readback.py",
}


@dataclass
class Slot:
    row: dict
    observed: dict
    raw: Path
    allocation: dict | None = None
    status: str = "SCORED"
    reason: str | None = None
    claim_sha: str | None = None

    def package_input(self):
        return self.row, self.allocation, self.observed, self.raw


def check_scene(release, row, receipt, index, truth):
    dual.require(
        f"{release}/{row['id']}"
        == row["visual_id"]
        == row["scene_id"]
        == receipt["physical_reset"]["scenario"]
        == index["scene"]
        == truth["scene"]
        and receipt["physical_reset"]["episode_id"] == index["episode"] == truth["episode"],
        "formal scene or episode differs between assignment, actual reset, image index and truth",
    )


def check_claim(private, plan, row, observed, plan_sha, batch_sha):
    authority = private / "claims" / (row["id"] + ".json")
    digest = observed["claim_sha256"]
    claim = pinned(authority, digest)
    pinned(private / "trials" / row["id"] / "claim.json", digest)
    fields = {
        "schema": "g1.formal-paired.claim.v1",
        "release": plan["release"],
        "id": row["id"],
        "assignment": row["visual_id"],
        "slot": row["slot"],
        "attempt": 1,
        "protocol_sha256": plan_sha,
        "allocation_sha256": row["allocation_sha256"],
        "batch_sha256": batch_sha,
        "output_root": str(private),
    }
    dual.require(all(claim[k] == v for k, v in fields.items()), "foreign formal claim")
    dual.require(
        datetime.fromisoformat(claim["claimed_at"]).utcoffset() is not None,
        "formal claim lacks a timezone",
    )
    return claim


def check_frame_files(raw, index):
    frames = index["frames"]
    dual.require(
        frames
        and [r["file"] for r in frames] == [f"frames/{i:04d}.json" for i in range(len(frames))]
        and {r["file"] for r in frames}
        == {p.relative_to(raw).as_posix() for p in (raw / "frames").iterdir()}
        and len({r["frame_id"] for r in frames}) == len(frames),
        "incomplete, duplicated or reordered original frame inventory",
    )
    for item in frames:
        dual.require(sha(raw / item["file"]) == item["file_sha256"], "changed original frame")


def allocated_outcomes(rows):
    return {
        "metrics": dual.rate_summary(rows),
        "evidence_status_by_arm": {
            arm: dict(Counter(r["evidence_status"] for r in rows if r["arm"] == arm))
            for arm in dual.ARMS
        },
    }


def source_table(private, public):
    _, plan = build.layout(public / "plan.json", private)
    raw = private / "trials"
    batch_sha = sha(public / "trial-allocation.public.json")
    batch = pinned(raw / "allocation.json", batch_sha)
    acquisition_sha = sha(public / "trial-acquisition.public.json")
    acquired = pinned(raw / "acquisition.json", acquisition_sha)
    stages = plan["stage_order"]
    dual.require(
        batch["schema"] == "g1.formal-paired.allocation.v1"
        and acquired["schema"] == "g1.formal-paired.acquisition.v1"
        and batch["plan_sha256"] == acquired["plan_sha256"] == PLAN_SHA
        and batch["release"] == acquired["release"] == plan["release"]
        and batch["scope"] == acquired["scope"] == SCOPE
        and batch["baseline"] == plan["baseline"]
        and batch["placement_overlap_sha256"] == sha(public / "placement-overlap.public.json")
        and acquired["assigned_slots"] == 8
        and batch["attempts_per_slot"] == 1
        and acquired["allocation_sha256"] == batch_sha
        and len(stages) == len(set(stages)) == 8
        and len(batch["cases"]) == len(acquired["cases"]) == len(plan["slots"]) == 8,
        "wrong formal allocation, acquisition, scope or denominator",
    )
    tree = private / "runtime-source"
    dual.require(
        batch["runtime_build_sha256"]
        == acquired["runtime_build_sha256"]
        == sha(public / "runtime-build.public.json"),
        "foreign registered runtime build",
    )
    lock = build.verify_lock(private, batch["runtime_build_sha256"])
    files = lock["runtime_files_sha256"]
    scoring = batch["scoring_sources_sha256"]
    dual.require(
        SCORE_FILES <= scoring.keys()
        and scoring == lock["scoring_sources_sha256"]
        and batch["scene_binding_plan_sha256"]
        == lock["scene_binding_plan_sha256"]
        == build.SCENE_PLAN_SHA
        and all(files[k] == h for k, h in scoring.items()),
        "unregistered scoring program or decoder",
    )
    dual.require(
        Path(__file__).resolve() == tree / "scripts/graduation/g1_formal_score.py"
        and Path(dual.__file__).resolve() == tree / "scripts/graduation/g1_dual_batch_score.py"
        and Path(mounts.__file__).resolve() == tree / "scripts/graduation/g1_mount_trials.py",
        "scorer must load its registered runtime",
    )
    slots = []
    for spec, row, observed in zip(plan["slots"], batch["cases"], acquired["cases"], strict=True):
        owner = spec["visual_id"].replace("/", ":")
        dual.require(
            all(row[k] == v for k, v in spec.items())
            and row["scene_id"] == spec["visual_id"] == f"{plan['release']}/{spec['id']}"
            and row["task_id"] == owner + ":task"
            and row["plan_id"] == owner + ":plan"
            and row["allocation_file"] == spec["id"] + "/allocation.json"
            and observed["id"] == row["id"],
            "crossed preregistered slot or native ownership",
        )
        slot = Slot(row, observed, raw / spec["id"] / "instance")
        slots.append(slot)
        inspect_slot(slot, private, plan, batch, batch_sha, files)
    mark_shared_identities(slots)
    known_ids = {row["id"] for row in batch["cases"]}
    authority = private / "claims"
    claim_ids = sorted(p.stem for p in authority.glob("*.json"))
    dual.require(
        set(claim_ids) <= known_ids and len(claim_ids) == acquired["formal_claims"],
        "formal claim ledger differs from acquisition",
    )
    common = {
        "release": plan["release"],
        "scope": SCOPE,
        "plan_sha256": PLAN_SHA,
        "scene_binding_plan_sha256": build.SCENE_PLAN_SHA,
        "allocation_sha256": batch_sha,
        "acquisition_sha256": acquisition_sha,
        "runtime_build_sha256": batch["runtime_build_sha256"],
        "scoring_sources_sha256": {k: scoring[k] for k in sorted(SCORE_FILES)},
        "independent_placements": 4,
        "allocated_slots": 8,
        "allocated_per_arm": 4,
        "maximum_attempts_per_slot": 1,
        "claim_files_present": len(claim_ids),
    }
    return slots, stages, common


def inspect_slot(slot, private, plan, batch, batch_sha, files):
    row, observed, raw = slot.row, slot.observed, slot.raw
    try:
        alloc, recorded = trials.load_case(private / "trials", batch, row)
        slot.allocation = alloc
        dual.require(
            alloc["case"]["visual_stages_in_order"] == plan["stage_order"]
            and alloc["scene_binding_plan_sha256"] == batch["scene_binding_plan_sha256"]
            and alloc["geometry"]["camera"] == plan["camera"]
            and all(files[k] == h for k, h in recorded.items()),
            "foreign formal case, geometry, asset, source generation or intent",
        )
        authority = private / "claims" / (row["id"] + ".json")
        if not authority.exists():
            if raw.exists() or (raw.parent / "claim.json").exists() or observed["acquired"]:
                raise ValueError("slot has execution evidence without its authoritative claim")
            slot.status, slot.reason = "NOT_RUN", "No claim and no instance"
            return
        claim = check_claim(private, plan, row, observed, PLAN_SHA, batch_sha)
        slot.claim_sha = observed["claim_sha256"]
        if observed["acquired"] is not True:
            status = observed["evidence_status"]
            dual.require(status in {"MISSING", "INTERRUPTED", "CORRUPT"}, "unknown claim status")
            if status == "INTERRUPTED" and "interruption_sha256" in observed:
                pinned(raw / "interrupted.json", observed["interruption_sha256"])
            for name, digest in observed.get("present_file_sha256", {}).items():
                dual.require(
                    Path(name).name == name and sha(raw / name) == digest,
                    "recorded partial evidence differs from original",
                )
            slot.status, slot.reason = status, observed.get("reason", status)
            return
        receipt = pinned(raw / "receipt.json", observed["receipt_sha256"])
        original = mounts.captured_evidence(raw, row, alloc)
        dual.require(
            all(v == receipt[k] == observed[k] for k, v in original.items())
            and receipt["batch_sha256"] == batch_sha
            and original["worker"]["run_id"] == row["visual_id"].replace("/", ":")
            and receipt["allocation_sha256"] == row["allocation_sha256"],
            "formal job, reset, SQLite, commands or original receipt differs from acquisition",
        )
        trials.formal_evidence(raw, row, receipt, batch_sha, claim)
        imports = pinned(raw / "imports.json", receipt["imports_sha256"])
        dual.require(
            all(
                files[m["file"]] == m["sha256"]
                for key in ("project_before", "project_after")
                for m in imports[key].values()
            ),
            "actual loaded project source differs from the frozen runtime",
        )
        mass = pinned(raw / "assembly-reset.json", observed["mass_receipt_sha256"])
        dual.require(
            mass == observed["mass"]
            and mass["requested_object_mass_kg"] == row["physical_object_mass_kg"],
            "unregistered assembly reset",
        )
        seal = pinned(raw / "acquisition-seal.json", receipt["capture_sha256"])
        index = pinned(raw / "pixel-index.json", seal["index_sha256"])
        truth = pinned(raw / "offline-truth.json", seal["truth_sha256"])
        check_scene(plan["release"], row, receipt, index, truth)
        states = vision.checked_steps(
            truth["samples"], index["episode"], row["asset_sha256"], truth["asset_sha256"]
        )
        dual.require(
            index["allocation_sha256"] == truth["allocation_sha256"] == row["allocation_sha256"]
            and max(states) == receipt["actual_physics_steps"],
            "foreign or incomplete original trajectory",
        )
        check_frame_files(raw, index)
        for r in index["frames"]:
            frame = vision.frame_from_row(
                raw, r, index["episode"], row["scene_id"], alloc["geometry"]
            )
            dual.require(r["physics_step"] in states, "frame outside the registered trajectory")
            validate_camera(frame, alloc["geometry"])
    except FileNotFoundError as exc:
        slot.status, slot.reason = "MISSING", str(exc)
    except (KeyError, TypeError, ValueError, IndexError, sqlite3.DatabaseError) as exc:
        slot.status, slot.reason = "CORRUPT", f"{type(exc).__name__}: {exc}"


def mark_shared_identities(slots):
    occurrences = defaultdict(list)
    assessed = [s for s in slots if s.status == "SCORED"]
    for slot in assessed:
        raw = slot.observed
        for key, value in (
            ("episode", raw["physical_reset"]["episode_id"]),
            ("job", raw["worker"]["job_id"]),
            ("lease", raw["worker"]["lease_id"]),
            ("receipt", raw["receipt_sha256"]),
        ):
            occurrences[(key, value)].append(slot)
    for left, right in combinations(assessed, 2):
        if datetime.fromisoformat(left.observed["worker"]["released_at"]) >= datetime.fromisoformat(
            right.observed["worker"]["acquired_at"]
        ):
            for slot in (left, right):
                slot.status, slot.reason = "CORRUPT", "overlapping or reversed registered leases"
    for (key, _), shared in occurrences.items():
        if len(shared) > 1:
            for slot in shared:
                slot.status, slot.reason = "CORRUPT", "reused original " + key


def score_slot(slot, tree, blind, seal):
    row, alloc, observed, raw = slot.package_input()
    header = {
        k: row[k]
        for k in (
            "id",
            "group",
            "arm",
            "slot",
            "seed",
            "reset_fixture_center_m",
            "yaw_rad",
            "asset_sha256",
            "allocation_sha256",
            "scene_id",
        )
    }
    if slot.status == "SCORED":
        try:
            with build.bind_scene(row["scene_id"]):
                result, by_stage, frames = dual.score_case(
                    row, alloc, observed, raw, tree, blind, seal, expected_scene=row["scene_id"]
                )
            receipt = pinned(raw / "receipt.json", observed["receipt_sha256"])
            truth = pinned(raw / "offline-truth.json", result["truth_sha256"])
            supports = set(result["contacts"]["support_geoms"])
            for phase in result["phases"].values():
                first, last = phase["entered_step"], phase["end_step"]
                sample_set = []
                if first is not None and last is not None:
                    dual.require(
                        0 <= first <= last < len(truth["samples"]),
                        "phase outside actual trajectory",
                    )
                    sample_set = truth["samples"][first : last + 1]
                phase["contacts"] = dual.contact_counts(sample_set, supports)
            result.update(
                scene_id=row["scene_id"],
                evidence_status="SCORED",
                claim_sha256=slot.claim_sha,
                full_commands_sha256=receipt["full_commands_sha256"],
                backend_command_count=receipt["backend_command_count"],
                worker_db_sha256=receipt["worker"]["sqlite_sha256"],
                original_runtime_imports_sha256=receipt["imports_sha256"],
            )
            return result, by_stage, frames
        except (
            ValueError,
            KeyError,
            IndexError,
            TypeError,
            StopIteration,
            FileNotFoundError,
        ) as exc:
            slot.status, slot.reason = "UNSCORABLE", f"{type(exc).__name__}: {exc}"
    reason = str(slot.reason).replace(str(tree.parent), "<formal-output>")
    return (
        {
            **header,
            "acquired": False,
            "evidence_status": slot.status,
            "acquisition_reported_acquired": observed["acquired"],
            "reason": reason,
            "claim_sha256": slot.claim_sha,
            **{k: None for k in dual.mount.METRICS},
        },
        {},
        [],
    )


def stage_totals(rows, stages):
    summary = {}
    for arm in dual.ARMS:
        allocated = [r for r in rows if r["arm"] == arm]
        scored = [r for r in allocated if r["evidence_status"] == "SCORED"]
        summary[arm] = {}
        for skill in stages:
            phases = [r["phases"][skill] for r in scored]
            summary[arm][skill] = {
                "allocated": len(allocated),
                "assessed": len(phases),
                "unknown": len(allocated) - len(phases),
                "entered": sum(p["entered_step"] is not None for p in phases),
                "dispatched": sum(p["dispatched"] for p in phases),
                "passed": sum(p["status"] == "PASS" for p in phases),
                "statuses": dict(Counter(p["status"] for p in phases)),
                "controller_sampling": dict(Counter(p["sampling"]["sampling"] for p in phases)),
            }
    return summary


def score_readback(private, public, blind, seal_sha, destination):
    slots, stages, common = source_table(private, public)
    index = blind.parent / "packets" / "index.json"
    seal = pinned(blind / "seal.json", seal_sha)
    expected = {
        read(s.raw / "acquisition-seal.json")["index_sha256"]: s
        for s in slots
        if s.status == "SCORED"
    }
    bundles = pinned(index, seal["index_sha256"])
    dual.require(
        set(expected) == set(bundles) == set(seal["packets"])
        and all(
            b["registered_scene"] == b["scene"] == expected[token].row["scene_id"]
            and b["episode"] == expected[token].observed["physical_reset"]["episode_id"]
            and b["mode"] == expected[token].row["arm"]
            and b["geometry"] == expected[token].allocation["geometry"]
            for token, b in bundles.items()
        )
        and seal["n_frames"] == sum(len(b["frames"]) for b in bundles.values()),
        "sealed blind packets do not cover exactly the verified registered originals",
    )
    rows = []
    pixel_groups = {arm: {key: [] for key in ("all_frames", *stages)} for arm in dual.ARMS}
    for slot in slots:
        result, by_stage, frames = score_slot(slot, private / "runtime-source", blind, seal)
        rows.append(result)
        group = pixel_groups[slot.row["arm"]]
        group["all_frames"].extend(frames)
        for skill, items in by_stage.items():
            group[skill].extend(items)
    assessed = [r for r in rows if r["evidence_status"] == "SCORED"]
    totals = {
        "verified_scored_episodes": len(assessed),
        "verified_action_dispatches": sum(r["dispatched"] for r in assessed),
        "verified_backend_commands": sum(r["backend_command_count"] for r in assessed),
        "verified_dense_samples": sum(r["dense_samples"] for r in assessed),
        "verified_physics_steps": sum(r["physics_steps"] for r in assessed),
        "scored_unique_frames": sum(r["frames"] for r in assessed),
        "blind_decoded_unique_frames": seal["n_frames"],
    }
    results = {
        **common,
        **totals,
        "schema": "g1.formal-paired.outcomes.v1",
        "cases": rows,
        **allocated_outcomes(rows),
        "stage_totals": stage_totals(rows, stages),
        "unit": "One independently reset placement per arm in each of four fixed pairs.",
        "joint_criterion": (
            "All eight online admissions with successful returns, independent physical success, "
            "qualified 121-sample lift and 241-sample release windows, and SCOPED_NO_VIOLATION."
        ),
        "verified_count_scope": "Counts cover slots with complete, verified scoring originals.",
        "joint_success_target": 0.9,
    }
    visibility = {
        **common,
        **totals,
        "schema": "g1.formal-paired.visibility.v1",
        "error_target_mm": 10,
        "definition": (
            "Euclidean 3D object-top-centre error conditional on accepted registered identity, "
            "metric depth and the frozen marker selection rule. Each acquired frame counts once "
            "per arm in all_frames. A reused frame can contribute to multiple stage rows. "
            "No observed frame gives null coverage and null P90."
        ),
        "by_arm": {
            arm: {key: dual.coverage(items) for key, items in group.items()}
            for arm, group in pixel_groups.items()
        },
    }
    destination.mkdir()
    for name, content in zip(REPORTS, (results, visibility), strict=True):
        write(destination / name, content)


def runtime_env(tree):
    return {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": os.pathsep.join((str(tree), str(tree / "src"))),
    }


def run_worker(private, public, blind, seal_sha, destination):
    tree = private / "runtime-source"
    argv = [
        sys.executable,
        "-m",
        "scripts.graduation.g1_formal_score",
        str(private),
        str(public),
        "--readback",
        str(blind),
        seal_sha,
        str(destination),
    ]
    with subprocess.Popen(
        argv,
        cwd=tree,
        env=runtime_env(tree),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ) as process:
        stdout, stderr = process.communicate()
        record = {
            "argv": argv,
            "cwd": str(tree),
            "pid": process.pid,
            "returncode": process.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "blind_seal_sha256": sha(blind / "seal.json"),
        }
    write(destination.with_suffix(".process.json"), record)
    dual.require(
        record["returncode"] == 0, "independent formal score worker failed: " + stderr[-1000:]
    )


def main(private, public):
    slots, _, common = source_table(private, public)
    verified = [s.package_input() for s in slots if s.status == "SCORED"]
    tree = private / "runtime-source"
    folder = Path(tempfile.mkdtemp(prefix="scoring-", dir=private))
    index = dual.package(verified, folder / "packets", registered_scene=True)
    outputs = [folder / name for name in ("blind-one", "blind-two")]
    seals = [dual.blind_reader(tree, index, output) for output in outputs]
    hashes = [sha(output / "seal.json") for output in outputs]
    dual.require(
        seals[0] == seals[1] and hashes[0] == hashes[1], "independent blind decoder mismatch"
    )
    dual.require(
        seals[0]["index_sha256"] == sha(index), "blind decoder used a different packet set"
    )
    for token, digest in seals[0]["packets"].items():
        dual.require(
            all(sha(p / (token + ".json")) == digest for p in outputs),
            "two blind packet hashes differ",
        )
    joined = [folder / name for name in ("score-one", "score-two")]
    for blind, result in zip(outputs, joined, strict=True):
        run_worker(private, public, blind, hashes[0], result)
    results = {}
    for name in REPORTS:
        first, second = (p / name for p in joined)
        results[name] = sha(first)
        dual.require(results[name] == sha(second), "independent final score mismatch: " + name)
        report = read(first)
        dual.require(
            all(report[k] == v for k, v in common.items()),
            "registration changed during score readback",
        )
    verification = {
        **common,
        "schema": "g1.formal-paired.scoring-verification.v1",
        "blind_input_sha256": sha(index),
        "blind_seal_sha256": hashes[0],
        "blind_input_scope": (
            "Original RGB-D, frame and scene identity, installation mode and registered geometry. "
            "Both pixel readers are blinded to decisions, contacts, trajectory and outcomes."
        ),
        "blind_frames": seals[0]["n_frames"],
        "fresh_pixel_processes": 2,
        "fresh_score_processes": 2,
        "blind_seals_identical": True,
        "final_scores_byte_identical": True,
        "blind_process_receipts_sha256": [sha(p.with_suffix(".process.json")) for p in outputs],
        "score_process_receipts_sha256": [sha(p.with_suffix(".process.json")) for p in joined],
        "result_sha256": results,
    }
    for name in REPORTS:
        target = public / name
        if target.exists():
            dual.require(
                sha(target) == results[name], "existing public score differs from verified readback"
            )
        else:
            write(target, read(joined[0] / name))
    verification_path = public / "scoring-verification.public.json"
    if verification_path.exists():
        previous = read(verification_path)
        dual.require(
            previous["result_sha256"] == results and previous["blind_seal_sha256"] == hashes[0],
            "existing verification belongs to a different readback",
        )
    else:
        write(verification_path, verification)
    print(folder)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private", type=Path, help="Registered formal output root")
    parser.add_argument("public", type=Path, help="Formal round directory containing plan.json")
    parser.add_argument(
        "--readback", nargs=3, metavar=("BLIND", "SEAL_SHA", "DEST"), help=argparse.SUPPRESS
    )
    args = parser.parse_args()
    private, public = args.private.resolve(), args.public.resolve()
    if args.readback:
        blind, seal_sha, destination = args.readback
        score_readback(private, public, Path(blind), seal_sha, Path(destination))
    else:
        main(private, public)
