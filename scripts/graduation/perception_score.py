"""Join sealed pixel estimates to independent same-step simulator geometry once."""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scripts.graduation.perception_io import MODES, ROOT, pinned, sha, write

from cloud_edge_robot_arm.research.native_geometry_calibration import full_rigid_geometry_errors
from cloud_edge_robot_arm.vision.native_calibration import NativeGeometryRegistration

METRICS = (
    "object_top_center_3d_m",
    "object_center_3d_m",
    "marker_center_3d_m",
    "marker_optical_depth_abs_m",
    "marker_depth_at_same_ray_abs_m",
    "orientation_angle_rad",
    "full_rigid_max_m",
)
KEY = ("cell_id", "step", "scene_id", "episode_id", "sim_time_s", "frame_id", "checksum_sha256")


def same_acquisition(first: dict, second: dict) -> None:
    if any(name not in first or name not in second or first[name] != second[name] for name in KEY):
        raise ValueError("different acquisition identity, physics step or pixels")


def indexed(rows: list[dict]) -> dict:
    lookup = {(r["cell_id"], r["step"]): r for r in rows}
    if len(lookup) != len(rows) or len({r["frame_id"] for r in rows}) != len(rows):
        raise ValueError("duplicate step or frame identity in independent source")
    return lookup


def metrics(observed: dict, frame: dict, state: dict, geometry: dict) -> dict:
    c = np.array(state["object_center_world_m"])
    r = np.array(state["rotation_to_world"]).reshape(3, 3)
    if state["half_extent_m"] != geometry["object_half_extent_m"]:
        raise ValueError("truth dimensions differ from allocated asset")
    attachment = np.array(geometry["marker_to_object"]).reshape(4, 4)
    top = c + r[:, 2] * state["half_extent_m"][2]
    marker = c + r @ attachment[:3, 3]
    camera = np.array(frame["camera_to_world"]).reshape(4, 4)
    axis, origin = camera[:3, 2], camera[:3, 3]
    marker_z = float(axis @ (marker - origin))
    fx, fy, cx, cy = frame["intrinsics"]
    u, v = observed["sampled_marker_center_px"]
    ray = camera[:3, :3] @ [(u - cx) / fx, (v - cy) / fy, 1.0]
    normal = r @ attachment[:3, 2]
    if abs(normal @ ray) < 1e-9:
        raise ValueError("cannot intersect observed ray with reference marker plane")
    true_ray_z = float((normal @ (marker - origin)) / (normal @ ray))
    z = observed["marker_center_optical_depth_m"]
    er = np.array(observed["rotation_to_world"]).reshape(3, 3)
    angle = float(np.arccos(np.clip((np.trace(er.T @ r) - 1) / 2, -1.0, 1.0)))
    rigid = full_rigid_geometry_errors(
        NativeGeometryRegistration(geometry),
        observed["object_center_world_m"],
        observed["rotation_to_world"],
        c.tolist(),
        r.ravel().tolist(),
    )
    return {
        "object_top_center_3d_m": float(
            np.linalg.norm(observed["object_top_center_world_m"] - top)
        ),
        "object_center_3d_m": float(np.linalg.norm(observed["object_center_world_m"] - c)),
        "marker_center_3d_m": float(np.linalg.norm(observed["marker_center_world_m"] - marker)),
        "marker_optical_depth_abs_m": abs(z - marker_z),
        "marker_depth_at_same_ray_abs_m": abs(z - true_ray_z),
        "orientation_angle_rad": angle,
        "full_rigid_max_m": rigid.joint_geometry_error_m,
    }


def distribution(values: list[float]) -> dict | None:
    if not values:
        return None
    arr = np.asarray(values, dtype=float)
    if not np.isfinite(arr).all():
        raise ValueError("nonfinite observed errors")
    return {
        "n": len(values),
        "p50": float(np.median(arr)),
        "p90": float(np.quantile(arr, 0.9)),
        "max": float(np.max(arr)),
    }


def step_gaps(rows: list[dict]) -> dict:
    cells: dict[str, list[int]] = defaultdict(list)
    for r in rows:
        cells[r["cell_id"]].append(r["step"])
    gaps = Counter(int(gap) for steps in cells.values() for gap in np.diff(sorted(steps)))
    return {str(step): count for step, count in sorted(gaps.items())}


def describe(rows: list[dict]) -> dict:
    measured = [r for r in rows if r["status"] == "OBSERVED"]
    captured = [r for r in rows if r["status"] != "NOT_CAPTURED"]
    return {
        "allocated": len(rows),
        "captured": len(captured),
        "observed": len(measured),
        "coverage": len(measured) / len(rows) if rows else None,
        "unavailable_by_reason": dict(
            Counter(r["reason"] for r in rows if r["status"] != "OBSERVED")
        ),
        "captured_adjacent_physics_step_gaps": step_gaps(captured),
        "observed_adjacent_physics_step_gaps": step_gaps(measured),
        "errors": {
            key: distribution([r["metrics"][key] for r in measured if key in r["metrics"]])
            for key in METRICS
        },
    }


def stratify(rows: list[dict], columns: tuple[str, ...]) -> list[dict]:
    strata: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        strata[tuple(row[c] for c in columns)].append(row)
    return [
        {**dict(zip(columns, key, strict=True)), **describe(group)}
        for key, group in sorted(strata.items())
    ]


def view_comparison(rows: list[dict]) -> list[dict]:
    result = []
    for split in ("exploration", "holdout"):
        selected = [r for r in rows if r["mode"] == "SUBPIX" and r["split"] == split]
        lookup = {
            (r["group"], r["initial_height_offset_m"], r["step"], r["view"]): r for r in selected
        }
        for view in ("left", "right"):
            paired = [
                (a, lookup[a["group"], a["initial_height_offset_m"], a["step"], view])
                for a in selected
                if a["view"] == "axial"
            ]
            both = [
                (a["metrics"]["object_top_center_3d_m"], b["metrics"]["object_top_center_3d_m"])
                for a, b in paired
                if a["status"] == b["status"] == "OBSERVED"
            ]
            marginal = Counter(
                (a["status"] == "OBSERVED", b["status"] == "OBSERVED") for a, b in paired
            )
            result.append(
                {
                    "split": split,
                    "view": view,
                    "paired_allocations": len(paired),
                    "axial_only": marginal[True, False],
                    "alternative_only": marginal[False, True],
                    "neither": marginal[False, False],
                    "common": len(both),
                    "paired_p90_axial_mm": None
                    if not both
                    else float(np.quantile([a for a, _ in both], 0.9) * 1000),
                    "paired_p90_alternative_mm": None
                    if not both
                    else float(np.quantile([b for _, b in both], 0.9) * 1000),
                    "smaller_top_center_error_for_alternative": sum(b < a for a, b in both),
                    "median_paired_alternative_minus_axial_mm": None
                    if not both
                    else float(np.median([b - a for a, b in both]) * 1000),
                }
            )
    return result


def view_montage(raw: Path, captures: dict, destination: Path) -> dict:
    """Paste three original 320x240 RGB frames at native resolution."""
    canvas = Image.new("RGB", (984, 292), "white")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.truetype("DejaVuSans.ttf", size=15)
    panels = []
    for index, view in enumerate(("axial", "left", "right")):
        cell_id = "graduation-dev-r593-p2-h0-" + view
        row = captures.get((cell_id, 0))
        left = 6 + index * 326
        draw.text(
            (left, 6),
            {"axial": "Axial (registered camera)", "left": "Left view", "right": "Right view"}[
                view
            ],
            font=font,
            fill="#223246",
        )
        if row is None:
            panels.append({"cell_id": cell_id, "step": 0, "status": "NOT_CAPTURED"})
            continue
        source = pinned(raw / "pixels" / row["file"], row["sha256"])
        rgb = base64.b64decode(source["rgb_png_base64"])
        with Image.open(io.BytesIO(rgb)) as im:
            if im.mode != "RGB" or im.size != (320, 240):
                raise ValueError("unexpected source RGB encoding for public figure")
            canvas.paste(im, (left, 31))
        panels.append(
            {
                "cell_id": cell_id,
                "step": 0,
                "status": "CAPTURED",
                "frame_checksum_sha256": row["checksum_sha256"],
                "source_png_sha256": hashlib.sha256(rgb).hexdigest(),
                "image_rect_xywh": [left, 31, 320, 240],
            }
        )
    draw.text(
        (6, 272),
        "Development placement P2 | initial height offset 0 mm | physics step 0",
        font=font,
        fill="#223246",
    )
    with destination.open("xb") as stream:
        canvas.save(stream, format="PNG")
    return {"filename": destination.name, "sha256": sha(destination), "panels": panels}


def score(
    allocation_path: Path,
    allocation_sha: str,
    raw: Path,
    capture_sha: str,
    estimates: Path,
    estimate_sha: str,
    sensitivity_dir: Path,
    sensitivity_sha: str,
    public: Path,
    detail: Path,
) -> None:
    # The official frozen teacher originals and database are outside this data flow.
    alloc = pinned(allocation_path, allocation_sha)
    cap = pinned(raw / "capture-seal.json", capture_sha)
    seal = pinned(estimates / "estimate-seal.json", estimate_sha)
    if not (
        cap["allocation_sha256"] == seal["allocation_sha256"] == allocation_sha
        and cap["pixel_index_sha256"] == seal["pixel_index_sha256"]
    ):
        raise ValueError("capture and estimation identified different inputs")
    decisions = pinned(estimates / "decisions.json", seal["decision_file_sha256"])
    idx = pinned(raw / "pixels" / "index.json", cap["pixel_index_sha256"])
    if (
        decisions["allocation_sha256"] != allocation_sha
        or idx["allocation_sha256"] != allocation_sha
        or decisions["pixel_index_sha256"] != cap["pixel_index_sha256"]
        or idx["geometry"] != alloc["geometry"]
    ):
        raise ValueError("pixel geometry or decision binding differs from allocation")
    # No offline states are opened until the independent pixel-decision hash is verified.
    truth = pinned(raw / "offline-truth" / "states.json", cap["offline_states_sha256"])
    if truth["allocation_sha256"] != allocation_sha:
        raise ValueError("offline states have different allocation")
    captures, answers, states = map(indexed, (idx["frames"], decisions["frames"], truth["states"]))
    if set(captures) != set(answers) or set(captures) != set(states):
        raise ValueError("every captured frame needs its own decision and physics sample")
    cells = alloc["cells"]
    requested = {(c["id"], s) for c in cells for s in c["steps"]}
    if not set(captures) <= requested or len(requested) != 324:
        raise ValueError("captured key outside the preallocated grid")
    for key, raw_row in captures.items():
        same_acquisition(raw_row, answers[key])
        same_acquisition(raw_row, states[key])
        if sha(raw / "pixels" / raw_row["file"]) != raw_row["sha256"]:
            raise ValueError("original pixels changed after detector read")
    rows = []
    for cell in cells:
        for step in cell["steps"]:
            key = (cell["id"], step)
            for mode in MODES:
                observed = None if key not in answers else answers[key]["modes"][mode]
                row = {
                    "split": cell["split"],
                    "group": cell["group"],
                    "cell_id": cell["id"],
                    "step": step,
                    "initial_height_offset_m": cell["initial_height_offset_m"],
                    "view": cell["view"],
                    "mode": mode,
                    "status": "NOT_CAPTURED" if observed is None else observed["status"],
                    "reason": "allocated_frame_missing" if observed is None else observed["reason"],
                    "metrics": {},
                }
                if observed is not None and observed["status"] == "OBSERVED":
                    row["metrics"] = metrics(observed, answers[key], states[key], alloc["geometry"])
                rows.append(row)
    write(detail, {"schema": "graduation.r593.joined-residuals.v1", "rows": rows})
    cold = [r for r in rows if r["split"] == "holdout" and r["mode"] == "SUBPIX"]
    holdout_by_view = []
    for view in ("axial", "left", "right"):
        measured = describe([r for r in cold if r["view"] == view])
        error = measured["errors"]["object_top_center_3d_m"]
        holdout_by_view.append(
            {
                "view": view,
                "allocated": measured["allocated"],
                "observed": measured["observed"],
                "top_center_p90_mm": None if error is None else error["p90"] * 1000,
            }
        )
    counts: Counter = Counter()
    command_counts: Counter = Counter()
    for finished in idx["cells"]:
        counts.update(finished["camera_counts"])
        command_counts.update(finished["commands"])
    calibrations = {
        view: sorted(
            {r["calibration_version"] for key, r in captures.items() if key[0].endswith("-" + view)}
        )
        for view in ("axial", "left", "right")
    }
    phase7 = ROOT / (
        "artifacts/research/process/20261004-ced-development/astra-rounds/"
        "round-v10-phase7-20261123/vision.public.json"
    )
    historical = pinned(phase7, "08ac6b27227c3c7b88a21b91697b171c2468fb1db88b6eeac500373058f08ab2")
    report = {
        "schema": "graduation.r593.development-perception.v1",
        "scope": "DEVELOPMENT_ONLY",
        "calibration_views_figure": view_montage(
            raw, captures, public.with_name("calibration-views.public.png")
        ),
        "primary_mode": "SUBPIX",
        "unit": "placement group",
        "holdout_groups": 3,
        "holdout_by_view": holdout_by_view,
        "paired_view_comparisons": view_comparison(rows),
        "by_split_and_mode": stratify(rows, ("split", "mode")),
        "by_split_view_mode": stratify(rows, ("split", "view", "mode")),
        "by_split_height_mode": stratify(rows, ("split", "initial_height_offset_m", "mode")),
        "by_split_view_height_mode": stratify(
            rows, ("split", "view", "initial_height_offset_m", "mode")
        ),
        "by_placement_and_mode": stratify(rows, ("split", "group", "mode")),
        "each_allocated_cell": [
            {
                "cell_id": c["id"],
                "view": c["view"],
                "initial_height_offset_m": c["initial_height_offset_m"],
                "split": c["split"],
                "allocated": len(c["steps"]),
                **{
                    m: dict(
                        Counter(
                            r["status"] for r in rows if r["cell_id"] == c["id"] and r["mode"] == m
                        )
                    )
                    for m in MODES
                },
            }
            for c in cells
        ],
        "capture": {
            "allocated": len(requested),
            "captured": len(captures),
            "cells": len(cells),
            "unique_episodes": len({r["episode_id"] for r in captures.values()}),
            "actual_physics_steps": sum(c["physics_steps"] for c in idx["cells"]),
            "zero_step_frames": sum(k[1] == 0 for k in captures),
            "cell_errors": {
                c["cell_id"]: c["capture_errors"] for c in idx["cells"] if c["capture_errors"]
            },
            **counts,
            "implicit_end_of_scope_acquisitions": counts["camera_acquisitions"] - len(captures),
            "actual_development_commands": dict(command_counts),
            "calibration_versions": calibrations,
            "detector_calls_in_blind_grid": seal["detector_calls"],
            "formal_claims": 0,
            "task_model_calls": 0,
            "teacher_attempts": 0,
            "hardware_actions": 0,
        },
        "sensitivity": pinned(sensitivity_dir / "summary.json", sensitivity_sha),
        "lift": {
            "historical_reference": str(phase7.relative_to(ROOT)),
            "historical_nominal_lift_m": historical["lift"][
                "nominal_endpoint_center_height_change_m"
            ],
            "historical_facts": historical["lift"]["physical_facts"],
            "certified_height_change_lower_bound_m": None,
            "continuous_linear_speed_upper_bound_m_s": None,
            "continuous_angular_speed_upper_bound_rad_s": None,
            "development_grasp_or_lift_actions": 0,
        },
        "interpretation": {
            "error_definitions": (
                "Euclidean errors separately at the tag centre, rigid-object centre "
                "and centre of its top face. Optical depth is reported at the true "
                "tag centre and at the detected centre ray intersected with the "
                "simulator tag plane."
            ),
            "physical_scope": (
                "Initial heights and free fall, sampled at six predetermined "
                "physics steps. There is no executed pick, lift, or hold in this "
                "grid."
            ),
            "unavailable": (
                "All allocated rows remain in coverage. Error quantiles are "
                "conditional on a decoded pose."
            ),
            "pairing": (
                "Each view uses a fresh reset with a distinct depth-noise seed. "
                "Comparisons pair placement, initial height and step; the "
                "particular noise draws differ."
            ),
            "statistical_bound": None,
            "formal_G1": "UNKNOWN",
            "formal_G3": "UNKNOWN",
        },
        "sha256": {
            "allocation": allocation_sha,
            "capture_seal": capture_sha,
            "pixel_index": cap["pixel_index_sha256"],
            "offline_states": cap["offline_states_sha256"],
            "estimation_seal": estimate_sha,
            "blind_decisions": seal["decision_file_sha256"],
            "paired_residuals": sha(detail),
            "sensitivity": sensitivity_sha,
            "phase7_reference": sha(phase7),
        },
    }
    write(public, report)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("allocation", "raw", "estimates", "sensitivity", "public", "detail"):
        parser.add_argument("--" + name, required=True, type=Path)
    for name in ("allocation", "capture", "estimate", "sensitivity"):
        parser.add_argument("--" + name + "-sha256", required=True)
    args = parser.parse_args()
    score(
        args.allocation,
        args.allocation_sha256,
        args.raw,
        args.capture_sha256,
        args.estimates,
        args.estimate_sha256,
        args.sensitivity,
        args.sensitivity_sha256,
        args.public,
        args.detail,
    )


if __name__ == "__main__":
    main()
