"""Read sealed pixel decisions and physical samples after the development episode."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
from scripts.graduation.perception_io import pinned, sha, write
from scripts.graduation.perception_pixels import measure

from cloud_edge_robot_arm.vision.observations import RGBDObservation


def checked_steps(rows, episode, expected_asset, recorded_asset):
    if expected_asset != recorded_asset or not rows:
        raise ValueError("missing trajectory or foreign asset")
    for i, row in enumerate(rows):
        if (
            row["episode_id"] != episode
            or row["physics_step"] != i
            or not math.isclose(row["sim_time_s"], i / 240, abs_tol=1e-8, rel_tol=0)
        ):
            raise ValueError("trajectory must exactly cover every step of this episode")
    return {r["physics_step"]: r for r in rows}


def fixed_window(steps, start, span):
    if start is None:
        return {"status": "NOT_RUN", "actual_samples": 0, "expected_samples": span + 1}
    present = [i for i in range(start, start + span + 1) if i in steps]
    return {
        "status": "COMPLETE_SAMPLING" if len(present) == span + 1 else "INCOMPLETE",
        "start": start,
        "planned_end": start + span,
        "actual_samples": len(present),
        "expected_samples": span + 1,
    }


def summarize_errors(values):
    observed = [v for v in values if v is not None]
    return {
        "frames": len(values),
        "estimated": len(observed),
        "rejected": len(values) - len(observed),
        "p50_m": float(np.quantile(observed, 0.5)) if observed else None,
        "p90_m": float(np.quantile(observed, 0.9)) if observed else None,
        "max_m": max(observed, default=None),
    }


def frame_from_row(directory, row, episode, scene, geometry):
    frame = RGBDObservation.model_validate(pinned(directory / row["file"], row["file_sha256"]))
    if (
        frame.checksum_sha256 != row["checksum_sha256"]
        or frame.frame_id != row["frame_id"]
        or frame.episode_id != episode
        or frame.scene_id != scene
        or frame.calibration_version != geometry["camera"]["calibration_version"]
        or not math.isclose(frame.sim_time_s, row["physics_step"] / 240, abs_tol=1e-8, rel_tol=0)
    ):
        raise ValueError("frame/source/step/calibration mismatch")
    return frame


def pixels(raw, alloc_file, alloc_sha):
    alloc = pinned(alloc_file, alloc_sha)
    seal = pinned(raw / "acquisition-seal.json", sha(raw / "acquisition-seal.json"))
    trace = pinned(raw / "pixel-index.json", seal["index_sha256"])
    if trace["allocation_sha256"] != alloc_sha:
        raise ValueError("foreign pixel allocation")
    decisions = []
    ids = set()
    for row in trace["frames"]:
        frame = frame_from_row(raw, row, trace["episode"], trace["scene"], alloc["geometry"])
        if frame.frame_id in ids:
            raise ValueError("duplicate captured frame")
        ids.add(frame.frame_id)
        decisions.append({**row, "estimate": measure(frame, alloc["geometry"], "SUBPIX")})
    write(raw / "decisions.json", {"index_sha256": seal["index_sha256"], "decisions": decisions})
    write(
        raw / "decision-seal.json",
        {
            "sha256": sha(raw / "decisions.json"),
            "acquisition_sha256": sha(raw / "acquisition-seal.json"),
        },
    )


def motion(steps, first, last):
    return {
        key: np.subtract(steps[last][field], steps[first][field]).tolist()
        for key, field in (
            ("object_delta_xyz_m", "object_geom_position_m"),
            ("tcp_delta_xyz_m", "tcp_position_m"),
        )
    }


def subset(rows, steps):
    errors = []
    speeds = []
    accepted = []
    for row in rows:
        center = row["estimate"]["object_top_center_world_m"]
        i = row["physics_step"]
        actual = steps[i]
        if center is None:
            errors.append(None)
            continue
        r = np.array(actual["object_geom_rotation_row_major"]).reshape(3, 3)
        top = (
            np.array(actual["object_geom_position_m"]) + r[:, 2] * actual["object_half_extent_m"][2]
        )
        errors.append(float(np.linalg.norm(np.subtract(center, top))))
        accepted.append((i, np.array(center)))
    for (i, a), (j, b) in zip(accepted, accepted[1:], strict=False):
        if j > i:
            speeds.append(float(np.linalg.norm(b - a) * 240 / (j - i)))
    ticks = sorted({r["physics_step"] for r in rows})
    gaps = np.diff(ticks) / 240
    return {
        "top_center": summarize_errors(errors),
        "distinct_sample_steps": len(ticks),
        "observed_sim_s": (ticks[-1] - ticks[0]) / 240 if ticks else 0.0,
        "distinct_step_mean_frequency_hz": (len(ticks) - 1) * 240 / (ticks[-1] - ticks[0])
        if len(ticks) > 1
        else None,
        "max_gap_sim_s": float(max(gaps)) if len(gaps) else None,
        "max_adjacent_accepted_apparent_speed_m_s": max(speeds, default=None),
        "positive_dt_accepted_pairs": len(speeds),
        "continuous_motion_bound_m_s": None,
    }


def score(raw, alloc_file, alloc_sha, out):
    alloc = pinned(alloc_file, alloc_sha)
    pixel_seal = pinned(raw / "decision-seal.json", sha(raw / "decision-seal.json"))
    seal = pinned(raw / "acquisition-seal.json", pixel_seal["acquisition_sha256"])
    obs = pinned(raw / "pixel-index.json", seal["index_sha256"])
    decision = pinned(raw / "decisions.json", pixel_seal["sha256"])
    truth = pinned(raw / "offline-truth.json", seal["truth_sha256"])
    report = pinned(raw / "run.json", seal["run_sha256"])
    if (
        obs["allocation_sha256"] != alloc_sha
        or truth["allocation_sha256"] != alloc_sha
        or decision["index_sha256"] != seal["index_sha256"]
        or truth["episode"] != obs["episode"]
        or len(obs["frames"]) != len(decision["decisions"])
    ):
        raise ValueError("foreign truth/decisions or missing frame")
    steps = checked_steps(
        truth["samples"], obs["episode"], alloc["asset_sha256"], truth["asset_sha256"]
    )
    rows = decision["decisions"]
    for source, row in zip(obs["frames"], rows, strict=True):
        if {k: row[k] for k in source} != source or row["physics_step"] not in steps:
            raise ValueError("missing or mismatched sealed step/frame")
        frame_from_row(raw, source, obs["episode"], obs["scene"], alloc["geometry"])
    actions = []
    for a in report["actions"]:
        window = [r for r in rows if r["label"].startswith(a["skill"] + "/")]
        stage = {**a, "sampling": subset(window, steps)}
        if a.get("entered_step") is not None:
            stage["observed_motion"] = motion(steps, a["entered_step"], a["end_step"])
        actions.append(stage)
    windows = {}
    for skill, span in (("LIFT", 120), ("RELEASE", 240)):
        dispatch = next(a for a in actions if a["skill"] == skill)
        start = dispatch.get("dwell_start_step")
        window = fixed_window(steps, start, span)
        if start is not None:
            window["sampling"] = subset(
                [r for r in rows if start <= r["physics_step"] <= start + span], steps
            )
        windows[skill] = window
    write(
        out,
        {
            "schema": "graduation.dynamic.r593.development.v1",
            "id": alloc["case"]["visual_id"],
            "allocation_sha256": alloc_sha,
            "source_seals": {**seal, **{"decisions_sha256": pixel_seal["sha256"]}},
            "pixel_then_truth": True,
            "episode": obs["episode"],
            "asset_sha256": truth["asset_sha256"],
            "physics_samples": len(steps),
            "last_step": max(steps),
            "first_step": 0,
            "whole": {**subset(rows, steps), **motion(steps, 0, max(steps))},
            "feedback_only": subset([r for r in rows if r["label"].endswith("/feedback")], steps),
            "explicit_frames": len(rows),
            "stages": actions,
            "windows": windows,
            "bootstrap": report.get("bootstrap"),
            "initial_and_terminal_pixels": [
                {
                    "label": row["label"],
                    "step": row["physics_step"],
                    "frame_id": row["frame_id"],
                    "checksum_sha256": row["checksum_sha256"],
                    "object_top_center_world_m": row["estimate"]["object_top_center_world_m"],
                }
                for row in rows
                if row["label"] in {"reset", "bootstrap", "terminal"}
            ],
            "candidate": report.get("candidate"),
            "stop": report.get("stop"),
            "safe_stop": report.get("safe_stop"),
            "lease": report["lease_summary"],
            "control": report["control"],
            "capture_grid": alloc["capture_grid"],
            "controller_dispatches": sum(a.get("dispatched", False) for a in actions),
            "completed_posts": sum(a["status"] == "PASS" for a in actions),
            "trace_scope": "Production components in one independent development episode",
            "formal_claims": 0,
            "task_model_calls": 0,
            "hardware_actions": 0,
            "formal_lifted": "UNKNOWN",
            "formal_stable": "UNKNOWN",
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["pixels", "score"])
    parser.add_argument("raw", type=Path)
    parser.add_argument("allocation", type=Path)
    parser.add_argument("allocation_sha256")
    parser.add_argument("--out", type=Path)
    arg = parser.parse_args()
    if arg.command == "pixels":
        pixels(arg.raw, arg.allocation, arg.allocation_sha256)
    else:
        score(arg.raw, arg.allocation, arg.allocation_sha256, arg.out)


if __name__ == "__main__":
    main()
