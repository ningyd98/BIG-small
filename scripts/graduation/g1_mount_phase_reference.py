"""Bind zero-step G1 phase observations to an archived canonical fixed-TCP success."""

from __future__ import annotations

import math
from pathlib import Path

from scripts.graduation.dynamic_physics import lines, read_seal, stage_receipts
from scripts.graduation.g1_mount_phase_sources import (
    check_teacher_grid,
    selected_states,
    teacher_source,
)
from scripts.graduation.perception_io import ROOT, check_sources, pinned, read, sha
from scripts.graduation.proposal_camera import CHECK_LIMITS

REFERENCE_PLAN = "01d407f38cc68dfb1d0fecfcc027fb5c24ea618270248b7099867aeeb9f55d3e"
PARENT_PLAN = "62e4c93a03f37fcb1ebd20ac660c09837c225f2b9651960701725c742914bef7"


FK_LIMITS = {
    name: CHECK_LIMITS[name]
    for name in ("tcp_residual_m", "object_center_residual_m", "object_rotation_max_abs")
}


def valid_fk_registration(limits):
    return limits == FK_LIMITS and all(type(v) in (int, float) for v in limits.values())


def usable_reconstruction(scene_matches, residuals):
    return (
        scene_matches
        and residuals.keys() == FK_LIMITS.keys()
        and all(
            type(v) in (int, float) and math.isfinite(v) and 0 <= v <= FK_LIMITS[k]
            for k, v in residuals.items()
        )
    )


def samples_from_stages(spans, names, expected):
    samples = {}
    for skill, name in names.items():
        records = [s for s in spans if s["stage"] == name]
        if len(records) != 1 or records[0]["status"] != "RETURNED":
            raise ValueError("missing or failed canonical stage")
        start, end = records[0]["start_step"], records[0]["end_step"]
        samples[skill] = [start, (start + end) // 2, end]
    if samples != expected:
        raise ValueError("different canonical stage bounds")
    return samples


def check_snapshot(state, scene):
    for key in ("object_half_extent_m", "region_center_m", "region_half_extent_m", "table_top_m"):
        if state[key] != scene[key]:
            raise ValueError("source scene geometry differs from registered canonical reference")
    for key, size in (
        ("joint_positions_rad", 7),
        ("joint_velocities_rad_s", 7),
        ("finger_positions_m", 2),
        ("finger_velocities_m_s", 2),
        ("object_position_m", 3),
        ("object_geom_position_m", 3),
        ("object_geom_rotation_row_major", 9),
        ("tcp_position_m", 3),
    ):
        if len(state[key]) != size or not all(math.isfinite(v) for v in state[key]):
            raise ValueError(f"incomplete or nonfinite archived pose: {key}")


def canonical_record(plan, selected_mount):
    raw = ROOT / plan["canonical_raw_root"]
    case, name, episode = (
        plan["canonical_case"],
        plan["canonical_case_name"],
        plan["canonical_episode"],
    )
    allocation_path = ROOT / plan["canonical_allocation"]
    allocation_sha = plan["input_sha256"][plan["canonical_allocation"]]
    alloc = pinned(allocation_path, allocation_sha)
    seal = read_seal(raw, plan["canonical_seal_sha256"])
    published = read(ROOT / plan["canonical_public_result"])
    command, request, origin = (
        read(raw / p) for p in ("command.json", "request.json", "origin.json")
    )
    output = read(raw / "canonical.json")
    positive = output["cases"][name]
    history = [x for x in lines(raw / "cases.jsonl") if x["case_id"] == case]
    asset = plan["input_sha256"][plan["canonical_origin_asset"]]
    if (
        command["exit_code"] != 0
        or request["sha256"] != allocation_sha
        or Path(request["path"]).name != allocation_path.name
        or read(raw / "audit-start.json")["allocation"] != allocation_sha
        or seal["allocation_sha256"] != allocation_sha
        or published["allocation_sha256"] != allocation_sha
        or published["capture_seal_sha256"] != plan["canonical_seal_sha256"]
        or published["private_file_sha256"] != seal["files"]
        or (origin["episode"], origin["step"], origin["time"], origin["case_id"])
        != (episode, 0, 0, case)
        or not (
            asset
            == origin["asset_sha256"]
            == output["asset_sha256"]
            == alloc["sources_sha256"][alloc["asset"]]
        )
        or alloc["case_ids"][name] != case
        or published["episode"] != episode
        or [e["event"] for e in history] != ["BEGIN", "RETURN"]
        or any(e["case"] != name for e in history)
        or history[1]["result"] != positive
        or positive["passed"] is not True
        or published["original_positive_passed"] is not True
        or published["independent_outcome"]["success"] is not True
        or not all(
            published["windows"][k]["entire_registered_duration_met"] for k in ("lift", "release")
        )
    ):
        raise ValueError("reference is not the sealed successful fixed-TCP case")
    spans = stage_receipts(list(lines(raw / "stages.jsonl")), case)
    if spans != published["stage_receipts"] or [(s["stage"], s["end_step"]) for s in spans] != [
        (t["stage"], t["physics_steps_total"]) for t in positive["trace"][1:]
    ]:
        raise ValueError("public or original stage receipts differ from archived events")
    ticks = samples_from_stages(spans, plan["canonical_stage_names"], plan["canonical_stage_steps"])
    dt = plan["canonical_dt_s"]
    states = []
    for row in lines(raw / "steps.jsonl"):
        if row["case_id"] != case or row["asset_sha256"] != asset:
            raise ValueError("foreign case or asset in canonical source")
        check_snapshot(row["snapshot"], plan["canonical_expected_scene"])
        states.append(row["snapshot"])
    if not (
        len(states) == published["samples"] == plan["canonical_samples"]
        and dt == alloc["physics_dt_s"] == published["actual_dt_s"]
        and spans[-1]["end_step"] == published["actual_physics_steps"] == len(states) - 1
    ):
        raise ValueError("incomplete canonical clock")
    check_teacher_grid(states, episode, dt, len(states) - 1)
    return {
        "scope": "canonical_fixed_tcp_pose_reconstruction",
        "case": case,
        "episode": episode,
        "mounts": ["original", selected_mount],
        "ticks": ticks,
        "states": selected_states(states, ticks),
        "source_seal_sha256": plan["canonical_seal_sha256"],
        "source_allocation_sha256": allocation_sha,
        "source_file_sha256": seal["files"],
        "original_scene_asset_sha256": asset,
        "source_physics_dt_s": dt,
        "source_samples": len(states),
        "source_action": "Archived fixed-TCP trajectory without live marker feedback.",
    }


def reference_records(parent, path, selected_mount):
    plan = pinned(path, REFERENCE_PLAN)
    if (
        sha(path.with_name("plan.md")) != plan["plan_md_sha256"]
        or plan["parent_plan_sha256"] != PARENT_PLAN
        or plan["baseline"] != parent["baseline"]
        or not valid_fk_registration(plan["fk_limits"])
        or selected_mount
        not in {
            m["id"]
            for m in parent["mounts"]
            if m["id"] != "original" and m["expected_native_family_admissible"]
        }
    ):
        raise ValueError("wrong source plan, geometry tolerance or selected installation")
    check_sources({"sources_sha256": plan["input_sha256"]})
    attempt, t5_states = teacher_source(parent)
    t5 = ROOT / plan["t5_raw_root"]
    t5_return = read(t5 / "terminal.json")
    ticks = plan["t5_stage_steps"]
    t5_geometry = plan["t5_original_geometry"]
    if (
        attempt["episode_id"] != plan["t5_episode"]
        or t5_return["episode"] != attempt["episode_id"]
        or t5_return["case"]["id"] != plan["t5_case"]
        or not t5_return["teacher_independent_outcome"]["success"]
        or t5_return["errors"]
        or ticks != parent["phase_diagnostic"]["stage_steps"]
        or len(t5_states) != plan["unique_poses_per_reference"]
        or plan["t5_scene_matches"] is not False
        or any(
            s["object_half_extent_m"] != t5_geometry["target"]["half_size"]
            or s["region_half_extent_m"] != t5_geometry["destination"]["half_size"]
            for s in t5_states.values()
        )
    ):
        raise ValueError("T5 source or its observed scene mismatch has changed")
    status = {
        "supplemental_plan_sha256": REFERENCE_PLAN,
        "canonical_expected_scene": plan["canonical_expected_scene"],
        "source_clock_note": "Archived dt is 0.0041666667 s. Pose renders advance zero steps.",
        "t5": {
            "case": plan["t5_case"],
            "episode": attempt["episode_id"],
            "status": "SCENE_MISMATCH",
            "unique_original_poses": len(t5_states),
            "source_seal_sha256": sha(t5 / "seal.json"),
            "original_scene": t5_geometry,
            "original_phase_roles": [
                {"skill": k, "point": label, "step": s, "source_time_s": t5_states[s]["sim_time_s"]}
                for k, phase in ticks.items()
                for label, s in zip(("start", "middle", "end"), phase, strict=True)
            ],
            "nominal_images": 0,
            "contribution_to_success_denominator": 0,
        },
    }
    return [canonical_record(plan, selected_mount)], status
