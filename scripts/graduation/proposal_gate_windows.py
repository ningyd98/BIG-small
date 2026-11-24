"""Pair frozen LIFT pixel estimates with independently scored per-step physical windows.

Run allocate, pixels, physics, then score with the SHA256 of each preceding seal.
Only the physical pass opens the simulated states and the original admission facts.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from scripts.graduation.dynamic_physics import CRITERIA, window_report
from scripts.graduation.perception_io import MODES, ROOT, pinned, sha, write

from cloud_edge_robot_arm.simulation.mujoco.backend import PhysicsStepObservation
from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import sample_physical_observation

STRIDE = 120
HZ = 240
LABELS = ("VALID", "INVALID", "UNKNOWN")
PHASE7 = Path("../../local-verification/round-v10-phase7-20261123.0z38LJs5/vision-final")
ORIGINALS = Path("experiments/results/phase-v10-formal-20261122/originals")
SCRIPT = Path(__file__).resolve()
ASSIGNMENT = "native-p0-v10-20261121-0001"
DEPENDENCIES = (
    "scripts/graduation/dynamic_physics.py",
    "scripts/graduation/perception_io.py",
    "src/cloud_edge_robot_arm/simulation/mujoco/episode_evaluator.py",
    "src/cloud_edge_robot_arm/simulation/mujoco/backend.py",
)


def require(assertion, message):
    if not assertion:
        raise ValueError(message)


def endpoints(first, post):
    require(type(first) is int and type(post) is int and 0 <= first <= post, "bad LIFT range")
    return sorted({*range(first, post + 1, STRIDE), post})


def jsonlines(path):
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            yield json.loads(line)


def allocate(plan_path, plan_sha, calibration_dir, originals, out):
    plan = pinned(plan_path, plan_sha)
    names = ("frames.private.jsonl", "source.private.json", "lift-steps.private.jsonl")
    pixel_files = {n: plan["input_sha256"][str(PHASE7 / n)] for n in names}
    registration = pinned(
        calibration_dir / "source.private.json", pixel_files["source.private.json"]
    )
    require(registration["details_sha256"] == pixel_files["frames.private.jsonl"], "pixel seal")
    inventory_id = registration["inventory_file_sha256"]
    index = pinned(originals / "inventory.json", inventory_id)["files"]
    originals_files = {
        n: index[n]["sha256"] for n in ("source-binding.json", "partial-originals.json")
    }
    binding = pinned(originals / "source-binding.json", originals_files["source-binding.json"])
    require(binding["assignment_id"] == ASSIGNMENT, "wrong original assignment")
    reg = registration["registration"]
    asset = reg["marked_asset_sha256"]
    asset_path = binding["geometry"]["asset_path"]
    require(
        binding["asset_sha256"]
        == plan["input_sha256"][asset_path]
        == asset
        == sha(ROOT / asset_path)
        and binding["source_generation"] == registration["source_generation"]
        and binding["geometry"]["camera"] == registration["camera"],
        "frozen camera/asset/generation mismatch",
    )
    reset = next(jsonlines(calibration_dir / "frames.private.jsonl"))
    require(reset["acquisition"] == 1 and reset["step"] == 0, "original reset frame missing")
    (lift,) = [row for row in registration["horizons"] if row["skill"] == "LIFT"]
    write(
        out,
        {
            "schema": "graduation.proposal-lift-window.allocation.v1",
            "created_utc": datetime.now(UTC).isoformat(),
            "plan_sha256": plan_sha,
            "script_sha256": sha(SCRIPT),
            "source_hashes": {p: sha(ROOT / p) for p in DEPENDENCIES},
            "assignment": binding["assignment_id"],
            "episode": reset["episode"],
            "asset_sha256": asset,
            "original_asset_path": asset_path,
            "source_generation": registration["source_generation"],
            "inventory_sha256": inventory_id,
            "phase7_files": pixel_files,
            "original_files": originals_files,
            "camera_version": registration["camera"]["calibration_version"],
            "registered_marker_id": reg["marker_id"],
            "reset_capture": reset["acquisition"],
            "dispatch_capture": int(registration["lift_dispatch_id"].removeprefix("acquisition-")),
            "post_capture": int(lift["terminal_acquisition_id"].removeprefix("acquisition-")),
            "dispatch": lift["dispatch_step"],
            "post": lift["terminal_step"],
            "end_steps": endpoints(lift["dispatch_step"], lift["terminal_step"]),
            "modes": list(MODES),
            "hold_steps": STRIDE,
            "physics_hz": HZ,
            "registered_lift_m": CRITERIA.lift_m,
            "max_stable_linear_speed_m_s": CRITERIA.max_stable_linear_speed_m_s,
            "max_stable_angular_speed_rad_s": CRITERIA.max_stable_angular_speed_rad_s,
            "reset_height_basis": "object center at reset; visual and physical sources independent",
            "window_rule": "121 inclusive states from end-120 to end, restricted to LIFT",
            "formal_claims": 0,
        },
    )


def check_frame(frame, episode, camera):
    require(
        not {"offline_labels", "physics_state", "offline_truth", "post_state_payload"}.intersection(
            frame
        ),
        "offline evidence on the pixel path",
    )
    step = frame["step"]
    stamp = datetime.fromisoformat(frame["captured_at"])
    require(
        type(step) is int
        and step >= 0
        and frame["episode"] == episode
        and frame["calibration_version"] == camera
        and stamp.utcoffset() is not None
        and math.isclose(frame["sim_time_s"], step / HZ, abs_tol=1e-8, rel_tol=0),
        "foreign frame, camera or physics clock",
    )


def marker_sample(mark, marker_id):
    pose = mark["registered_sample_object_pose"]
    if mark["status"] == "OBSERVED":
        require(pose is not None and mark["observed_marker_ids"] == [marker_id], "marker identity")
        z = pose["center_world_m"][2]
        require(math.isfinite(z), "nonfinite marker pose")
    else:
        require(mark["status"] == "UNKNOWN" and pose is None, "unknown marker has pose")
        z = None
    error = mark["geometric_error_bound_m"]
    require(error is None or math.isfinite(error) and error >= 0, "invalid geometry bound")
    # The frozen sensor's stability field is a sample diagnostic with no interval certificate.
    require(mark["stability_status"] == "UNKNOWN", "new stability evidence needs a new protocol")
    return {"z_m": z, "error_m": error, "reason": mark["reason"]}


def pixel_window(series, reset, first, end):
    steps = range(max(first, end - STRIDE), end + 1)
    require(all(i in series for i in steps), "allocated window lacks a frame")
    missing = [i for i in steps if series[i]["z_m"] is None]
    observed = [series[i] for i in steps if series[i]["z_m"] is not None]
    complete = len(steps) == STRIDE + 1 and not missing and reset["z_m"] is not None
    points = bounded = "UNKNOWN"
    differences = [] if reset["z_m"] is None else [m["z_m"] - reset["z_m"] for m in observed]
    if complete:
        points = "VALID" if min(differences) >= CRITERIA.lift_m - 1e-12 else "INVALID"
        if reset["error_m"] is not None and all(m["error_m"] is not None for m in observed):
            errors = [m["error_m"] + reset["error_m"] for m in observed]
            if all(
                d - e >= CRITERIA.lift_m - 1e-12 for d, e in zip(differences, errors, strict=True)
            ):
                bounded = "VALID"
            elif any(
                d + e < CRITERIA.lift_m - 1e-12 for d, e in zip(differences, errors, strict=True)
            ):
                bounded = "INVALID"
    return {
        "window_samples": len(steps),
        "observed_marker_samples": len(observed),
        "missing_marker_steps": missing,
        "all_marker_samples_observed": complete,
        "min_point_delta_from_reset_m": min(differences, default=None),
        "height_sample_points": points,
        "bounded_height": bounded,
        "bounded_stability": "UNKNOWN",
        "certified_joint": "INVALID" if bounded == "INVALID" else "UNKNOWN",
        "missing_geometry_bounds_on_observed": sum(m["error_m"] is None for m in observed),
    }


def identity(allocation, digest):
    return {
        "episode": allocation["episode"],
        "asset_sha256": allocation["asset_sha256"],
        "allocation_sha256": digest,
    }


def seal(directory, name, payload):
    data_name = f"{name}.json"
    write(directory / data_name, payload)
    write(
        directory / f"{name}.seal.json", {"file": data_name, "sha256": sha(directory / data_name)}
    )


def read_sealed(directory, name, seal_sha):
    seal_data = pinned(directory / f"{name}.seal.json", seal_sha)
    require(seal_data["file"] == f"{name}.json", "wrong sealed evidence type")
    return pinned(directory / seal_data["file"], seal_data["sha256"])


def pixels(alloc, digest, source_dir, out):
    source = source_dir / "frames.private.jsonl"
    require(sha(source) == alloc["phase7_files"][source.name], "frozen pixel evidence changed")
    selected = {}
    series = {mode: {} for mode in MODES}
    reset = None
    expected_step = alloc["dispatch"]
    last_utc = None
    for frame in jsonlines(source):
        step, capture = frame["step"], frame["acquisition"]
        is_reset = capture == alloc["reset_capture"]
        is_boundary = capture in (alloc["dispatch_capture"], alloc["post_capture"])
        is_sample = (
            alloc["dispatch"] < step < alloc["post"]
            and frame["role"] == "REGISTERED_PER_PHYSICS_STEP"
        )
        if not (is_reset or is_boundary or is_sample):
            continue
        check_frame(frame, alloc["episode"], alloc["camera_version"])
        stamp = datetime.fromisoformat(frame["captured_at"])
        require(last_utc is None or last_utc < stamp, "nonadvancing observation time")
        last_utc = stamp
        modes = {
            m: marker_sample(frame["markers"][m], alloc["registered_marker_id"]) for m in MODES
        }
        if is_reset:
            require(reset is None and step == 0, "ambiguous visual reset")
            reset = modes
            continue
        if is_boundary:
            expected = alloc["dispatch"] if capture == alloc["dispatch_capture"] else alloc["post"]
            require(
                step == expected and frame["role"] == "REGISTERED_ACTION_BOUNDARY", "wrong boundary"
            )
        require(
            step == expected_step, "missing, duplicated or reordered allocated physics-step frame"
        )
        expected_step += 1
        for m in MODES:
            series[m][step] = modes[m]
        selected[step] = {
            "step": step,
            "acquisition": capture,
            "captured_at": frame["captured_at"],
            "role": frame["role"],
        }
    require(
        reset is not None and expected_step == alloc["post"] + 1, "incomplete pixel denominator"
    )
    rows = []
    for end in alloc["end_steps"]:
        rows.append(
            {
                "end": end,
                "capture": selected[end]["acquisition"],
                "modes": {
                    m: pixel_window(series[m], reset[m], alloc["dispatch"], end) for m in MODES
                },
            }
        )
    seal(
        out,
        "pixels",
        {
            **identity(alloc, digest),
            "windows": rows,
            "selected": list(selected.values()),
            "reset_marker": reset,
            "input_sha256": sha(source),
            "first_missing_marker_after_dispatch": {
                m: next((i for i, mark in series[m].items() if mark["z_m"] is None), None)
                for m in MODES
            },
            "distinct_marker_frames_observed": {
                m: sum(mark["z_m"] is not None for mark in series[m].values()) for m in MODES
            },
        },
    )


def physical_label(complete, satisfied):
    if not complete:
        return "UNKNOWN"
    return "VALID" if satisfied else "INVALID"


def physics(alloc, allocation_sha, originals, out):
    original_path = originals / "partial-originals.json"
    raw = pinned(original_path, alloc["original_files"][original_path.name])
    source_id = raw["identity"]
    require(
        source_id["episode_id"] == alloc["episode"]
        and source_id["assignment_id"] == alloc["assignment"]
        and source_id["asset_hash"] == raw["reset_metadata"]["asset_hash"] == alloc["asset_sha256"],
        "original episode, assignment or asset mismatch",
    )
    require(
        raw["reset_count"] == 1 and raw["reset"]["physics_dt_s"] == 1 / HZ,
        "reset or timestep mismatch",
    )
    (horizon,) = [h for h in raw["horizons"] if h["skill"] == "LIFT"]
    require(
        (horizon["dispatch_step"], horizon["terminal_step"]) == (alloc["dispatch"], alloc["post"])
        and horizon["terminal_acquisition_id"] == f"acquisition-{alloc['post_capture']}",
        "original LIFT horizon mismatch",
    )
    original_decisions = [r["inputs"] for r in raw["decisions"] if r["inputs"]["skill"] == "LIFT"]
    require(
        [r["phase"] for r in original_decisions] == ["PRE", "POST"], "original admissions differ"
    )
    for row, step, capture in zip(
        original_decisions,
        (alloc["dispatch"], alloc["post"]),
        (alloc["dispatch_capture"], alloc["post_capture"]),
        strict=True,
    ):
        context = row["registered_inputs"]
        require(
            context["asset_sha256"] == alloc["asset_sha256"]
            and context["episode_id"] == alloc["episode"]
            and context["calibration_version"] == alloc["camera_version"]
            and row["capture"]["step"] == step
            and row["capture"]["acquisition_id"] == f"acquisition-{capture}"
            and row["step"]["step_id"] == horizon["step_id"],
            "foreign admission binding",
        )
    require(
        raw["total_physics_steps"] == len(raw["physics"]) == alloc["post"],
        "original physical denominator",
    )
    observations = [raw["reset"]["physics_state"]]
    for index, row in enumerate(raw["physics"], 1):
        require(
            type(row["physics_step"]) is int and row["physics_step"] == index,
            "wrong raw physics step",
        )
        observations.append(row["post_state_payload"])
    samples = []
    for i, state in enumerate(observations):
        require(
            state["episode_id"] == alloc["episode"]
            and type(state["physics_step"]) is int
            and state["physics_step"] == i
            and math.isclose(state["sim_time_s"], i / HZ, abs_tol=1e-8, rel_tol=0),
            "duplicate, missing, or foreign trajectory state or clock",
        )
        sample = sample_physical_observation(PhysicsStepObservation(**state), CRITERIA)
        require(
            all(
                math.isfinite(n)
                for n in (
                    *sample.object_position_m,
                    sample.object_linear_speed_m_s,
                    sample.object_angular_speed_rad_s,
                )
            ),
            "nonfinite physical measurement",
        )
        samples.append(sample)
    reset_z = samples[0].object_position_m[2]
    dispatch_z = samples[alloc["dispatch"]].object_position_m[2]
    rows = []
    for end in alloc["end_steps"]:
        subset = samples[max(end - STRIDE, alloc["dispatch"]) : end + 1]
        summary, _ = window_report("lift", subset, reset_z, dispatch_z, False)
        complete = len(subset) == STRIDE + 1
        failures = summary["failures_by_predicate"]
        height_ok = "height_from_reset" not in failures
        stable_ok = "angular_speed" not in failures and "linear_speed" not in failures
        contact_ok = "bilateral_contact" not in failures and "gripper_closed" not in failures

        rows.append(
            {
                "end": end,
                "samples": len(subset),
                "duration_s": summary["duration_s"],
                "height": physical_label(complete, height_ok),
                "speed_stability": physical_label(complete, stable_ok),
                "held_contact": physical_label(complete, contact_ok),
                "joint": physical_label(complete, summary["entire_registered_duration_met"]),
                "failed_samples_by_predicate": failures,
                "min_max": summary["min_max"],
                "independent_physical_predicates_required": [
                    "height_from_reset",
                    "linear_speed",
                    "angular_speed",
                    "bilateral_contact",
                    "gripper_closed",
                ],
            }
        )
    sensor_facts = original_decisions[-1]["facts"]
    seal(
        out,
        "physics",
        {
            **identity(alloc, allocation_sha),
            "windows": rows,
            "input_sha256": sha(original_path),
            "reset_center_z_m": reset_z,
            "physics_states_including_reset": len(samples),
            "post_center_z_m": samples[-1].object_position_m[2],
            "original_admission_steps": [r["capture"]["step"] for r in original_decisions],
            "original_post": {
                "shield_allowed": original_decisions[-1]["shield"]["allowed"],
                "facts": {
                    name: {k: sensor_facts[name][k] for k in ("value", "reasons")}
                    for name in ("object_lifted", "object_stable")
                },
            },
        },
    )


def check_rows(report, allocation):
    require(
        report["episode"] == allocation["episode"]
        and report["asset_sha256"] == allocation["asset_sha256"]
        and [r["end"] for r in report["windows"]] == allocation["end_steps"],
        "window allocation, episode or asset differs",
    )


def matrix(pairs):
    table = {truth: {v: 0 for v in LABELS} for truth in LABELS}
    for truth, pixel in pairs:
        table[truth][pixel] += 1
    return table


def score(alloc, allocation_sha, source_dir, directory, pixel_seal, physics_seal, out):
    pixel_data = read_sealed(directory, "pixels", pixel_seal)
    physics_data = read_sealed(directory, "physics", physics_seal)
    for report in (pixel_data, physics_data):
        check_rows(report, alloc)
        require(report["allocation_sha256"] == allocation_sha, "evidence from different allocation")
    previous = source_dir / "lift-steps.private.jsonl"
    require(sha(previous) == alloc["phase7_files"][previous.name], "phase 7 selection seal")
    prior_selection = [
        {k: p[k] for k in ("step", "acquisition", "captured_at", "role")}
        for p in jsonlines(previous)
    ]
    require(
        prior_selection == pixel_data["selected"], "independent representative selection differs"
    )
    physics_windows, pixels_windows = physics_data["windows"], pixel_data["windows"]
    joined = list(zip(physics_windows, pixels_windows, strict=True))
    counts = {
        test: dict(Counter(r[test] for r in physics_windows))
        for test in ("height", "speed_stability", "held_contact", "joint")
    }
    modes = {}
    for mode in MODES:
        rows = [p["modes"][mode] for p in pixels_windows]
        modes[mode] = {
            "distinct_marker_steps_observed": pixel_data["distinct_marker_frames_observed"][mode],
            "first_missing_marker_step": pixel_data["first_missing_marker_after_dispatch"][mode],
            "full_windows_every_marker_observed_including_reset": sum(
                r["all_marker_samples_observed"] for r in rows
            ),
            "first_uncertified_window_end": next(
                (
                    p["end"]
                    for p in pixels_windows
                    if p["modes"][mode]["certified_joint"] == "UNKNOWN"
                ),
                None,
            ),
            "bounded_height_by_physical_height": matrix(
                (t["height"], p["modes"][mode]["bounded_height"]) for t, p in joined
            ),
            "bounded_stability_by_physical_speed_stability": matrix(
                (t["speed_stability"], p["modes"][mode]["bounded_stability"]) for t, p in joined
            ),
            "certified_joint_by_physical_joint": matrix(
                (t["joint"], p["modes"][mode]["certified_joint"]) for t, p in joined
            ),
            "point_height_by_physical_height_diagnostic_only": matrix(
                (t["height"], p["modes"][mode]["height_sample_points"]) for t, p in joined
            ),
        }
    write(
        out,
        {
            "schema": "graduation.proposal-lift-window.results.v1",
            **identity(alloc, allocation_sha),
            "assignment": alloc["assignment"],
            "plan_sha256": alloc["plan_sha256"],
            "independently_sealed_inputs": {
                "pixels_sha256": pixel_seal,
                "physics_sha256": physics_seal,
            },
            "source_chain": {
                "phase7": alloc["phase7_files"],
                "originals": alloc["original_files"],
                "originals_inventory_sha256": alloc["inventory_sha256"],
                "analysis_source_sha256": alloc["script_sha256"],
            },
            "scope": "Development readback of two LIFT postconditions on one frozen formal episode",
            "independent_trajectories": 1,
            "allocated_window_endpoints": len(joined),
            "complete_half_second_windows": sum(
                r["samples"] == STRIDE + 1 for r in physics_windows
            ),
            "physics_samples_per_full_window": STRIDE + 1,
            "distinct_lift_steps": len(prior_selection),
            "physics_states_including_reset": physics_data["physics_states_including_reset"],
            "reset_center_z_m": physics_data["reset_center_z_m"],
            "post_center_z_m": physics_data["post_center_z_m"],
            "physical_counts": counts,
            "modes": modes,
            "matrix_orientation": "rows physical, columns pixel",
            "original_lift_admission_steps": physics_data["original_admission_steps"],
            "original_lift_post": physics_data["original_post"],
            "g3_pre_submit_b3_joint_replay": {
                "status": "UNAVAILABLE",
                "executed_rule_pairs": 0,
                "reason": (
                    "The archived native admissions are LIFT PRE/POST. Intermediate endpoints lack "
                    "contemporaneous candidate action contracts and pre-submit safety snapshots. "
                    "Labels here concern completed effects."
                ),
            },
            "formal_claims": 0,
            "new_physics_runs": 0,
            "interval_speed_certificate": None,
            "per_endpoint": [
                {
                    "step": p["end"],
                    "source_acquisition": p["capture"],
                    "physical_samples": t["samples"],
                    **{k: t[k] for k in ("height", "speed_stability", "held_contact", "joint")},
                    "minimum_measured_height_change_from_reset_m": t["min_max"][
                        "delta_height_reset_m"
                    ][0],
                    "maximum_linear_speed_m_s": t["min_max"]["linear_speed_m_s"][1],
                    "maximum_angular_speed_rad_s": t["min_max"]["angular_speed_rad_s"][1],
                    "failed_physical_samples_by_predicate": t["failed_samples_by_predicate"],
                    "pixel_modes": {
                        m: {k: v for k, v in p["modes"][m].items() if k != "missing_marker_steps"}
                        for m in MODES
                    },
                }
                for t, p in joined
            ],
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    alloc = commands.add_parser("allocate")
    alloc.add_argument("plan", type=Path)
    alloc.add_argument("plan_sha256")
    alloc.add_argument("out", type=Path)
    alloc.add_argument("--vision", type=Path, default=ROOT / PHASE7)
    alloc.add_argument("--originals", type=Path, default=ROOT / ORIGINALS)
    for name in ("pixels", "physics", "score"):
        p = commands.add_parser(name)
        p.add_argument("allocation", type=Path)
        p.add_argument("allocation_sha256")
        p.add_argument("directory", type=Path)
        if name in ("pixels", "score"):
            p.add_argument("--vision", type=Path, default=ROOT / PHASE7)
        if name == "physics":
            p.add_argument("--originals", type=Path, default=ROOT / ORIGINALS)
        if name == "score":
            p.add_argument("pixel_seal")
            p.add_argument("physics_seal")
            p.add_argument("out", type=Path)
    args = parser.parse_args()
    if args.command == "allocate":
        allocate(args.plan, args.plan_sha256, args.vision, args.originals, args.out)
        return
    alloc = pinned(args.allocation, args.allocation_sha256)
    require(sha(SCRIPT) == alloc["script_sha256"], "analysis source differs from allocation")
    require(
        all(sha(ROOT / p) == alloc["source_hashes"][p] for p in DEPENDENCIES),
        "analysis dependency differs from allocation",
    )
    if args.command == "pixels":
        pixels(alloc, args.allocation_sha256, args.vision, args.directory)
    elif args.command == "physics":
        physics(alloc, args.allocation_sha256, args.originals, args.directory)
    else:
        score(
            alloc,
            args.allocation_sha256,
            args.vision,
            args.directory,
            args.pixel_seal,
            args.physics_seal,
            args.out,
        )


if __name__ == "__main__":
    main()
