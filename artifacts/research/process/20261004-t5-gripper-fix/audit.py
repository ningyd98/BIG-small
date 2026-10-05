"""Audit paired teacher scenes, fixed denominators and preserved failure evidence."""

from __future__ import annotations

import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUTPUT = Path(__file__).resolve().parent
OLD_MANIFEST_SHA = "5d02ae37083a6772df4bbaca925baab10257a896ab5d89218331b936ee11dd34"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_dataset(name: str) -> tuple[dict, dict]:
    directory = ROOT / "datasets" / name
    manifest = json.loads((directory / "manifest.json").read_text())
    assignments = manifest["assignments"]
    assert manifest["status"] == "COMPLETE"
    assert len(assignments) == manifest["requested_episodes"]
    assert [a["index"] for a in assignments] == list(range(len(assignments)))
    outcomes, failures = [], []
    sample_count = frame_count = 0
    for assignment in assignments:
        path = directory / assignment["episode_path"]
        assert sha(path) == assignment["sha256"]
        episode = json.loads(gzip.decompress(path.read_bytes()))
        outcome = episode["outcome"]
        assert assignment["status"] == episode["status"] == outcome["status"]
        assert assignment["physical_success"] == episode["physical_success"] == outcome["success"]
        assert assignment["execution_verified"] == episode["execution_verified"]
        assert episode["source"] == "GROUND_TRUTH_TEACHER"
        sample_count += len(episode["physical_samples"])
        frame_count += len(episode["frames"])
        outcomes.append(outcome)
        if not outcome["success"]:
            contacts = Counter(
                tuple(pair) for sample in episode["physical_samples"]
                for pair in sample["contact_pairs"]
                if "object_geom" in pair and any("distractor" in name for name in pair)
            )
            failures.append({
                "index": assignment["index"], "case": assignment["case"],
                "seed": assignment["seed"], "status": outcome["status"],
                "reason": outcome["failure_reason"], "safety_events": outcome["safety_events"],
                "target_distractor_contact_pair_samples": [
                    {"pair": list(pair), "count": count} for pair, count in contacts.items()
                ],
            })
    normal = [a for a in assignments if a["case"] == "NORMAL"]
    random = [a for a in assignments if a["scene_source"] == "SAMPLED_CURRENT_ASSET"]
    successes = [outcome for outcome in outcomes if outcome["success"]]
    report = {
        "dataset": str(directory.relative_to(ROOT)),
        "manifest_sha256": sha(directory / "manifest.json"),
        "asset_sha256": manifest["asset_sha256"], "protocol_hash": manifest["protocol_hash"],
        "assigned": len(assignments), "published": len(outcomes),
        "normal_success": sum(a["physical_success"] for a in normal),
        "normal_assigned": len(normal),
        "random_success": sum(a["physical_success"] for a in random),
        "random_assigned": len(random),
        "negative_control_success": assignments[1]["physical_success"],
        "status_counts": dict(Counter(outcome["status"] for outcome in outcomes)),
        "safety_event_counts": dict(Counter(
            event for outcome in outcomes for event in outcome["safety_events"]
        )),
        "physical_sample_count": sample_count, "action_frame_count": frame_count,
        "successful_outcome_minima": {
            key: min(outcome[key] for outcome in successes)
            for key in ("measured_lift_m", "hold_s", "placed_stable_s")
        },
        "failures": failures,
    }
    return manifest, report


def main() -> None:
    old, old_report = read_dataset("rgbd-teacher-smoke-v2")
    current, current_report = read_dataset("rgbd-teacher-smoke-v3")
    fresh, fresh_report = read_dataset("rgbd-teacher-fresh-gripper-v3")
    assert old_report["manifest_sha256"] == OLD_MANIFEST_SHA
    assert len(old["assignments"]) == len(current["assignments"]) == 20
    for before, after in zip(old["assignments"], current["assignments"], strict=True):
        assert (before["index"], before["case"], before["seed"], before["scene_source"]) == (
            after["index"], after["case"], after["seed"], after["scene_source"],
        )
        assert before["scene"]["scene_parameters"] == after["scene"]["scene_parameters"]
    assert [a["seed"] for a in fresh["assignments"][2:]] == list(range(20261103, 20261143))
    assert not {a["seed"] for a in current["assignments"]} & {
        a["seed"] for a in fresh["assignments"]
    }
    for manifest in (current, fresh):
        assert manifest["asset_sha256"] == sha(ROOT / "assets/robots/franka_panda/scene.xml")
        assert all(sha(ROOT / path) == digest for path, digest in
                   manifest["protocol"]["source_sha256"].items())
    report = {
        "schema_version": "rgbd.teacher-gripper-fix.audit.v1", "valid": True,
        "original_scene_parameters_equal": True, "fresh_seeds_disjoint": True,
        "historical_manifest_unchanged": True, "current_teacher_sources_match": True,
        "historical": old_report, "paired_repaired": current_report, "fresh": fresh_report,
        "formal_g1": False, "online_model_success_measured": False,
    }
    (OUTPUT / "audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in (
        "valid", "original_scene_parameters_equal", "fresh_seeds_disjoint",
        "historical_manifest_unchanged", "current_teacher_sources_match",
    )}))


if __name__ == "__main__":
    main()
