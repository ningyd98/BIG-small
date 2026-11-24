"""Build independently bound phase samples for the marker-mount development study."""

from __future__ import annotations

import math
from pathlib import Path

from scripts.graduation.dynamic_vision_score import checked_steps
from scripts.graduation.perception_io import ROOT, pinned, read, sha

SKILLS = ("APPROACH", "GRASP", "LIFT")


def phase_steps(actions, last_step):
    stages = {row["skill"]: row for row in actions if row["skill"] in SKILLS}
    if set(stages) != set(SKILLS) or sum(row["skill"] in SKILLS for row in actions) != len(SKILLS):
        raise ValueError("missing or duplicate registered phase")
    samples = {}
    for skill in SKILLS:
        row = stages[skill]
        if not row.get("executor_entered"):
            samples[skill] = []
            continue
        start, end = row.get("dispatch_step"), row.get("end_step")
        if type(start) is not int or type(end) is not int or not 0 <= start <= end <= last_step:
            raise ValueError("unbound executed phase interval")
        samples[skill] = [start, (start + end) // 2, end]
    return samples


def requires_teacher(samples, acquisitions):
    for skill, ticks in samples.items():
        if not ticks or not any(
            row["label"].startswith(skill + "/") and ticks[0] < row["physics_step"] < ticks[-1]
            for row in acquisitions
        ):
            return True
    return False


def check_teacher_grid(rows, episode, dt, end):
    if len(rows) != end + 1 or not math.isfinite(dt) or dt <= 0:
        raise ValueError("missing teacher states or declared clock")
    for step, row in enumerate(rows):
        if (
            row["episode_id"] != episode
            or row["physics_step"] != step
            or not math.isclose(row["sim_time_s"], step * dt, rel_tol=0, abs_tol=1e-8)
        ):
            raise ValueError("foreign teacher state or inconsistent physics clock")


def selected_states(trajectory, ticks):
    return {s: trajectory[s] for seq in ticks.values() for s in seq}


def fresh_sources(plan, batch, selection, trial_root):
    if len(batch["cases"]) != len(plan["slots"]):
        raise ValueError("incomplete preallocated development batch")
    mounts = {m["id"]: m for m in plan["mounts"]}
    records = []
    for planned, issued in zip(plan["slots"], batch["cases"], strict=True):
        if any(issued.get(k) != v for k, v in planned.items()):
            raise ValueError("fresh case differs from preregistered slot")
        case_id = planned["id"]
        if issued["allocation_file"] != f"{case_id}/allocation.json":
            raise ValueError("foreign allocation path")
        family = mounts["original" if planned["arm"] == "original" else selection["selected_mount"]]
        directory = trial_root / case_id / "instance"
        allocated = pinned(trial_root / issued["allocation_file"], issued["allocation_sha256"])
        seal = read(directory / "acquisition-seal.json")
        truth = pinned(directory / "offline-truth.json", seal["truth_sha256"])
        index = pinned(directory / "pixel-index.json", seal["index_sha256"])
        run = pinned(directory / "run.json", seal["run_sha256"])
        if (
            allocated["geometry"]["marker_family"] != family["family"]
            or allocated["geometry"]["asset_path"] != family["asset_path"]
            or allocated["asset_sha256"] != family["asset_sha256"]
            or index["allocation_sha256"] != issued["allocation_sha256"]
            or truth["allocation_sha256"] != index["allocation_sha256"]
            or truth["episode"] != index["episode"]
        ):
            raise ValueError("foreign trajectory, mount or run allocation")
        trajectory = checked_steps(
            truth["samples"], truth["episode"], family["asset_sha256"], truth["asset_sha256"]
        )
        ticks = phase_steps(run["actions"], max(trajectory))
        records.append(
            {
                "scope": "fresh_development_pose_reconstruction",
                "case": case_id,
                "arm": planned["arm"],
                "episode": truth["episode"],
                "mounts": [family["id"]],
                "ticks": ticks,
                "requires_separate_reference": requires_teacher(ticks, index["frames"]),
                "case_allocation_sha256": issued["allocation_sha256"],
                "source_seal_sha256": sha(directory / "acquisition-seal.json"),
                "source_truth_sha256": seal["truth_sha256"],
                "source_run_sha256": seal["run_sha256"],
                "source_pixel_index_sha256": seal["index_sha256"],
                "states": selected_states(trajectory, ticks),
            }
        )
    if len({r["episode"] for r in records}) != len(records):
        raise ValueError("reused development episode")
    return records


def teacher_source(plan):
    desc = plan["phase_diagnostic"]
    base = Path(desc["root"])

    def source(name):
        path = base / "source" / name
        return pinned(ROOT / path, plan["input_sha256"][str(path)])

    attempt = source("attempt.json")
    states = source("physical-observations.json")
    stages = source("teacher-actions.json")
    episode = attempt["episode_id"]
    check_teacher_grid(states, episode, attempt["physics_dt_s"], attempt["terminal_step"])
    ticks = desc["stage_steps"]
    for skill, points in ticks.items():
        relevant = [a for a in stages if a["action_type"] == skill]
        if len(relevant) != 1 or relevant[0]["episode_id"] != episode:
            raise ValueError("ambiguous teacher action")
        start, end = relevant[0]["start_step"], relevant[0]["end_step"]
        if points != [start, (start + end) // 2, end]:
            raise ValueError("teacher phase differs from registered steps")
    return attempt, selected_states(states, ticks)
