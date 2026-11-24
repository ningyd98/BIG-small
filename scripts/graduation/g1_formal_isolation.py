"""Verify prospective G1 assignments against the historical scene and calibration inventories."""

from __future__ import annotations

import argparse
import hashlib
import subprocess
from collections import Counter
from pathlib import Path

from scripts.graduation.perception_io import ROOT, pinned, sha, write

from cloud_edge_robot_arm.research.sol_molmo_scenarios import sample_component_scene
from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig

PLAN_SHA = "8856a834e6191b74c323f89feb0e4a38c50b94e0a8850a4a88181bd53176e40a"
PROCESS = Path("artifacts/research/process/20261004-ced-development")
ROUNDS = PROCESS / "astra-rounds"


def compare_source(document, slots, release):
    """Include nested lineage and unlabelled XYZ/yaw tuples, as well as named scene fields."""
    centers = {tuple(slot["reset_fixture_center_m"]) for slot in slots}
    seeds = {slot["seed"] for slot in slots}
    identities = {release} | {slot[k] for slot in slots for k in ("id", "group", "visual_id")}
    seen_centers, seen_seeds, seen_ids = set(), set(), set()

    def visit(value):
        if isinstance(value, dict):
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            if len(value) in (3, 4) and all(type(x) in (float, int) for x in value):
                position = tuple(value[:3])
                if position in centers:
                    seen_centers.add(position)
            for child in value:
                visit(child)
        elif isinstance(value, str) and value in identities:
            seen_ids.add(value)
        elif type(value) in (int, float) and value in seeds:
            seen_seeds.add(value)

    visit(document)
    return {
        "center_overlap": [list(center) for center in sorted(seen_centers)],
        "seed_overlap": sorted(seen_seeds),
        "identity_overlap": sorted(seen_ids),
    }


def historical_paths(plan):
    paths = {Path(path) for path in plan["historical_allocation_pool_inputs"]}
    paths.update(
        {
            ROUNDS / "round-g1-dual-bootstrap-evidence-20261124/plan.json",
            ROUNDS / "round-g1-first-refusal-dual-marker-20261124/plan.json",
            ROUNDS / "round-g1-marker-mount-20261124/plan.json",
            ROUNDS / "round-harness-four-fresh-positions-20261118/preallocation.json",
            ROUNDS / "round-v10-phase5-20261122/registration/protocol.json",
            ROUNDS
            / "round-p1-development-readiness-20261119/development/preallocation/allocation.json",
            PROCESS / "t8b-module/fix-round-1-dry-selection/pools.json",
        }
    )
    for stage in ("pilot-v1", "pilot-v2"):
        paths.add(PROCESS.parent / "20261004-t8-foundation" / stage / "pools.json")
    for stage in ("integration", "dynamic-qualification", "guarded-clock"):
        paths.add(ROUNDS / f"round-graduation-{stage}-20261123" / "allocation.public.json")
    return sorted(paths)


def verify(plan_file, output):
    plan = pinned(plan_file, PLAN_SHA)
    pinned_md = sha(plan_file.with_suffix(".md"))
    if pinned_md != plan["plan_md_sha256"]:
        raise ValueError("Astra plan text changed")
    slots, release = plan["slots"], plan["release"]
    if len(slots) != 8 or Counter(slot["group"] for slot in slots) != dict.fromkeys(
        ("f01", "f02", "f03", "f04"), 2
    ):
        raise ValueError("invalid number of prospective paired assignments")
    rows, reconstructed, pool_groups = {}, {}, {}
    for path in historical_paths(plan):
        path_id = path.as_posix()
        git_blob = subprocess.check_output(
            ["git", "show", f"{plan['baseline']}:{path_id}"], cwd=ROOT
        )
        digest = hashlib.sha256(git_blob).hexdigest()
        if digest != plan["input_sha256"].get(path_id, digest):
            raise ValueError(f"baseline input differs from Astra plan: {path}")
        source = pinned(ROOT / path, digest)
        data = [source]
        if path.name == "pools.json" or path.name == "evidence-pools.json":
            pool_groups[path_id] = {
                name: len(rows) for name, rows in source.items() if isinstance(rows, list)
            }
        if path.name == "allocation.json" and "development" in source:
            sampler = ROOT / "src/cloud_edge_robot_arm/research/sol_molmo_scenarios.py"
            if sha(sampler) != source["source"]["pose_sampler_sha256"]:
                raise ValueError("historical component pose sampler changed")
            configs = source["development"] + source["repeats_1802"]
            for row in configs:
                config = pinned(ROOT / path.parent / row["config"], row["config_sha256"])
                generated = sample_component_scene(config["seed"], config["scene_split"])
                if generated != row["scene"]:
                    raise ValueError("regenerated historical placement differs")
                data.append(generated)
            reconstructed[path_id] = len(configs)
        if path == ROUNDS / "round-v10-phase5-20261122/registration/protocol.json":
            for assignment in source["assignments"]:
                scenario = PhysicalScenarioConfig.scenario(
                    "S01_NORMAL_STATIC", seed=assignment["seed"]
                )
                pose = scenario.object_pose
                data.append([pose.x, pose.y, pose.z, scenario.object_yaw_rad])
            reconstructed[path_id] = len(source["assignments"])
        rows[path_id] = {"sha256": digest, **compare_source(data, slots, release)}
    eligible = all(
        not row[key]
        for row in rows.values()
        for key in ("center_overlap", "seed_overlap", "identity_overlap")
    )
    protocol = ROOT / "artifacts/research/protocol-final/protocol.json"
    report = dict(
        schema="g1.formal-paired.placement-isolation.v1",
        plan_sha256=PLAN_SHA,
        eligible=eligible,
        release=release,
        distinct_placements=len({s["group"] for s in slots}),
        slot_count=len(slots),
        sources=rows,
        seeded_placements_reconstructed=reconstructed,
        registered_pool_rows=pool_groups,
        official_t16_final_present_at_canonical_path=protocol.is_file(),
        excluded_future_t16_lineages=[s["visual_id"] for s in slots],
        comparison="Exact XYZ in XYZ or XYZ/yaw records, assignment and ancestor IDs, and seeds.",
    )
    write(output, report)
    if not eligible:
        raise ValueError("prospective G1 sources overlap a historical assignment")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    verify(args.plan.resolve(), args.output.resolve())
