"""Preallocate and project the eight archived first MOVE_ABOVE admissions into a blind store."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from scripts.graduation.perception_io import ROOT, check_sources, pinned, read, sha, write

ROUND = (
    ROOT
    / "artifacts/research/process/20261004-ced-development/astra-rounds"
    / "round-proposal-development-gate-binding-20261124"
)
RAW = Path("../../local-verification/round-proposal-exp-20261124.OYKmbQnV/translated/episodes")
PLAN = "f41bef9db302c950fedbbc7395906563b58ccc617de6a65d33da99d02c6bb2e7"
BASE = "4bd4deb0716b82e6036b617bb78436390a0e8c12"
FILES = (
    "online-audit.json",
    "run.json",
    "pixel-index.json",
    "acquisition-seal.json",
    "frames/0002.json",
)
ROLE_NAMES = (
    "registration-handoff",
    "color_reference",
    "registered_reference",
    "MOVE_ABOVE/PRE",
    "MOVE_ABOVE/PRE_conditions",
    "MOVE_ABOVE/PRE_Shield",
    "MOVE_ABOVE/dispatch_source_recheck",
)
FACTS_SOURCE = "FIRST_PRE_COLOR_TRACKER_SAME_HANDOFF_OBJECT"
PRE_COLUMNS = {
    "case",
    "geometry",
    "original",
    "identity",
    "original_sha256",
    "inventory_digest",
    "registered_binding",
    "binding_sha256",
    "executed_contract",
    "grounded_step",
    "clock",
    "roles",
    "dispatch_reference",
    "candidate",
    "grounding_reference",
    "dispatch",
    "first_command",
    "shield",
    "registered_requirements",
    "registered_verdicts",
    "pre_state",
    "pre_preview_time",
    "source_frame",
    "source_row_sha256",
    "provenance",
}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def utc(value):
    time = datetime.fromisoformat(value)
    require(time.utcoffset() == timedelta(0), "original aware UTC required")
    return time


def clock_window(roles):
    names = [r["label"] for r in roles]
    require(
        names[: len(ROLE_NAMES)] == list(ROLE_NAMES)
        and all(r == ROLE_NAMES[-1] for r in names[len(ROLE_NAMES) :]),
        "misordered PRE roles",
    )
    identity = (
        "frame_id",
        "episode_id",
        "checksum_sha256",
        "captured_at",
        "physics_step",
        "sim_time_s",
    )
    first = roles[0]
    previous = utc(first["captured_at"])
    for index, row in enumerate(roles):
        require(all(first[k] == row[k] for k in identity), "mixed source frame or simulation clock")
        require(row["acquired_for_this_role"] is (index == 0), "same retained reference required")
        now = utc(row["checked_at"])
        require(previous <= now, "nonmonotonic original role clock")
        previous = now
    return dict(
        bootstrap_begin=first["checked_at"],
        bootstrap_end=roles[1]["checked_at"],
        conditions_begin=roles[4]["checked_at"],
        pre_shield=roles[5]["checked_at"],
        dispatch_recheck=roles[-1]["checked_at"],
    )


def fresh_track_interval(captured, first, last):
    require(
        captured - timedelta(seconds=0.05) <= first <= last <= captured + timedelta(seconds=5),
        "cannot identify a single fresh tracker branch on the complete recorded interval",
    )


def validate_facts_envelope(value):
    require(
        set(value) == {"source", "facts"}
        and value["source"] == FACTS_SOURCE
        and bool(value["facts"])
        and "target_visible" in value["facts"],
        "unbound PRE color facts or external label",
    )


def require_event_identity(original, replay):
    require(original == replay, "opportunity identity differs or includes an external label")


def allocation(raw, public):
    plan = pinned(ROUND / "plan.json", PLAN)
    require(
        plan["planner"] == "gpt-6.2-astra"
        and plan["baseline"] == BASE
        and sha(ROUND / "plan.md") == plan["plan_md_sha256"]
        and len(plan["input_sha256"]) == 77,
        "incorrect scope or plan",
    )
    check_sources({"sources_sha256": plan["input_sha256"]})
    subprocess.run(["git", "merge-base", "--is-ancestor", BASE, "HEAD"], cwd=ROOT, check=True)
    extra = {}
    for path in (
        "research/native_archived_tracker.py",
        "research/raw_episode_v3.py",
        "vision/owner_registration.py",
        "vision/observations.py",
        "edge/evidence/models.py",
        "edge/evidence/conditions.py",
    ):
        rel = "src/cloud_edge_robot_arm/" + path
        stored = subprocess.check_output(["git", "show", f"{BASE}:{rel}"], cwd=ROOT)
        require(
            hashlib.sha256(stored).hexdigest() == sha(ROOT / rel),
            "archive replay dependency changed",
        )
        extra[rel] = sha(ROOT / rel)
    master = pinned(
        ROOT / RAW / "allocation.json", plan["input_sha256"][str(RAW / "allocation.json")]
    )
    ids = [case["id"] for case in master["cases"]]
    require(
        len(ids) == len(set(ids)) == 8
        and {c["id"] for c in master["cases"]}
        == {f"t{i:02d}-{view}" for i in range(1, 5) for view in ("nominal", "translated")},
        "expected four prespecified placements in two views",
    )
    rows = []
    for row in master["cases"]:
        directory = RAW / row["id"] / "instance"
        hashes = {name: plan["input_sha256"][str(directory / name)] for name in FILES}
        run = pinned(ROOT / directory / "run.json", hashes["run.json"])
        candidate = run["candidate"]
        rows.append(
            dict(
                id=row["id"],
                group=row["group"],
                view=row["view"],
                allocation_file=row["allocation_file"],
                allocation_sha256=row["allocation_sha256"],
                camera_configuration_sha256=row["camera_configuration_sha256"],
                files=hashes,
                candidate={
                    k: candidate[k]
                    for k in (
                        "skill",
                        "frame_id",
                        "checksum_sha256",
                        "binding_sha256",
                        "target_pose_m",
                    )
                },
            )
        )
    inv = "r593-v4-source-inventory.json"
    value = dict(
        plan_sha256=PLAN,
        baseline=BASE,
        input_count=77,
        archive_dependencies=extra,
        master_sha256=sha(ROOT / RAW / "allocation.json"),
        inventory_sha256=plan["input_sha256"][str(RAW / inv)],
        event_definition=(
            "first actually dispatched MOVE_ABOVE PRE per frozen E allocation; keep all cases"
        ),
        cases=rows,
        new_dispatches=0,
    )
    write(raw / "allocation.json", value)
    write(public / "allocation.public.json", value)


def project(case, inventory):
    source = ROOT / RAW / case["id"] / "instance"
    files = case["files"]
    raw = {name: pinned(source / name, files[name]) for name in FILES[:-1]}
    require(sha(source / FILES[-1]) == files[FILES[-1]], "mixed RGB-D file")
    seal, index, run, audit = (
        raw[name]
        for name in ("acquisition-seal.json", "pixel-index.json", "run.json", "online-audit.json")
    )
    require(
        all(
            seal[key] == files[name]
            for key, name in (
                ("audit_sha256", FILES[0]),
                ("run_sha256", FILES[1]),
                ("index_sha256", FILES[2]),
            )
        ),
        "mixed run/audit/index acquisition seal",
    )
    configuration = pinned(ROOT / RAW / case["allocation_file"], case["allocation_sha256"])
    geometry = configuration["geometry"]
    require(
        configuration["case"]["id"] == case["id"]
        and digest(geometry["camera"]) == case["camera_configuration_sha256"]
        and index["allocation_sha256"] == case["allocation_sha256"],
        "wrong placement or camera",
    )
    original, grounding, shield, pre = audit[:4]
    require(
        original["phase"] == "r2_original_contract"
        and grounding["index"] == 0
        and grounding["schema_version"] == "native.registered.grounding.v2"
        and pre["phase"] == shield["phase"] == "PRE",
        "missing original first PRE audit",
    )
    frame_row = index["frames"][2]
    require(
        frame_row["file"] == FILES[-1]
        and frame_row["label"] == ROLE_NAMES[0]
        and frame_row["file_sha256"] == files[FILES[-1]],
        "wrong handoff file",
    )
    roles = [x for x in run["frame_roles"] if x["label"] in ROLE_NAMES]
    clock_window(roles)
    require(index["episode"] == roles[0]["episode_id"], "pixel index belongs to another episode")
    action = run["actions"][0]
    summary = action["pre"]
    actual_cmd = next(a for a in audit if a.get("phase") == "actual_command_records")
    require(
        action["skill"] == actual_cmd["skill"] == case["candidate"]["skill"] == "MOVE_ABOVE"
        and case["candidate"] == run["candidate"]
        and actual_cmd["first_seq"] == actual_cmd["rows"][0]["command_seq"],
        "first archived executor action does not match the allocated MOVE_ABOVE",
    )
    require(
        summary["shield"]["result"] == shield["shield"]
        and shield["target_pose"] == case["candidate"]["target_pose_m"]
        and summary["frame_id"] == shield["frame_id"] == frame_row["frame_id"]
        and summary["checksum_sha256"] == frame_row["checksum_sha256"]
        and shield["step_id"] == grounding["step_id"],
        "mismatched PRE SafetyShield receipt",
    )
    require(
        summary["conditions"]
        == [
            dict(name=v["condition_name"], status=v["status"], reasons=v["reasons"])
            for v in pre["verdicts"]
        ],
        "PRE condition receipt differs from the run",
    )
    require(
        grounding["online"]["visual_facts"] == {}
        and grounding["online"]["context_hash"] == grounding["checkpoint_sha256"],
        "unidentified preparation-phase source",
    )
    track = pre["preview"]["track"]
    require(
        track["observation_id"] == grounding["observation_id"] == frame_row["frame_id"]
        and track["observation_checksum_sha256"]
        == grounding["checksum_sha256"]
        == frame_row["checksum_sha256"]
        and track["episode_id"] == index["episode"],
        "PRE state or grounding came from another frame",
    )
    require(
        original["original"]["source_hashes"]
        == inventory
        == grounding["binding"]["prepared"]["grounding_source_hashes"],
        "wrong r593 source registration",
    )
    return {
        "case": {k: case[k] for k in ("id", "group", "view", "camera_configuration_sha256")},
        "geometry": geometry,
        "original": original["original"],
        "identity": grounding["identity"],
        "original_sha256": grounding["original_plan_sha256"],
        "inventory_digest": digest(inventory),
        "registered_binding": grounding["binding"],
        "binding_sha256": grounding["binding_sha256"],
        "executed_contract": grounding["executed_contract"],
        "grounded_step": grounding["grounded_step"],
        "clock": run["action_clock_contexts"][0],
        "roles": roles,
        "dispatch_reference": run["dispatch_reference"],
        "candidate": case["candidate"],
        "grounding_reference": run["grounding_contracts"][0],
        "dispatch": {
            k: action[k]
            for k in ("skill", "entered_step", "dispatch_step", "executor_entered", "dispatched")
        },
        "first_command": actual_cmd["rows"][0],
        "shield": summary["shield"],
        "registered_requirements": pre["requirements"],
        "registered_verdicts": pre["verdicts"],
        "pre_state": pre["state"],
        "pre_preview_time": pre["preview"]["evaluated_at"],
        "source_frame": frame_row,
        "source_row_sha256": files,
        "provenance": {
            "state": "online-audit:first PRE with state",
            "facts": FACTS_SOURCE,
            "comparison_now": "last MOVE_ABOVE/dispatch_source_recheck.checked_at",
            "historical_shield": "original first pre_check receipt",
        },
    }


def extract(raw, public):
    alloc = pinned(raw / "allocation.json", sha(public / "allocation.public.json"))
    inventory = pinned(ROOT / RAW / "r593-v4-source-inventory.json", alloc["inventory_sha256"])
    blind = raw / "blind"
    blind.mkdir(exist_ok=True)
    require(not (blind / "seal.json").exists(), "extraction already sealed")
    items = []
    for case in alloc["cases"]:
        selection = project(case, inventory)
        require(set(selection) == PRE_COLUMNS, "unregistered extraction columns")
        target = blind / case["id"]
        target.mkdir(exist_ok=True)
        if (target / "pre.json").exists():
            require(read(target / "pre.json") == selection, "partial projection differs")
        else:
            write(target / "pre.json", selection)
        source = ROOT / RAW / case["id"] / "instance" / FILES[-1]
        if not (target / "frame.json").exists():
            with source.open("rb") as src, (target / "frame.json").open("xb") as dst:
                shutil.copyfileobj(src, dst)
        require(sha(target / "frame.json") == case["files"][FILES[-1]], "RGB-D copy differs")
        items.append(
            dict(
                id=case["id"],
                pre_sha256=sha(target / "pre.json"),
                frame_sha256=sha(target / "frame.json"),
            )
        )
    seal = {
        "allocation_sha256": sha(raw / "allocation.json"),
        "cases": items,
        "stage": "PRE_WHITELIST_ONLY",
    }
    write(blind / "seal.json", seal)
    write(public / "blind-inputs.public.json", seal)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["allocate", "extract"])
    parser.add_argument("raw", type=Path)
    a = parser.parse_args()
    {"allocate": allocation, "extract": extract}[a.stage](a.raw, ROUND)


if __name__ == "__main__":
    main()
