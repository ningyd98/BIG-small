"""Cold-read the predeclared physical courses, frozen selections and optical certificates."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


HERE = Path(__file__).resolve().parent
RAW = Path("experiments/results/g1-lift-corridor-20261125")
H = HERE.parent / "round-g1-skill-handoff-20261125"
FIXED = "r+0_t+0_h22"
NOMINAL = "rad+0_h10"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def generate(root):
    raw = root / RAW
    calib = raw / "candidate-calibration-01"
    public_inputs = [p for p in HERE.glob("handoff-physics-*")
                     if p.suffix in {".json", ".py"} and p.name != "handoff-physics-results.public.json"]
    inputs = [HERE / "plan.json", HERE / "plan.md", H / "handoff-physics-results.public.json",
              H / "handoff-physics-native.py", *public_inputs]
    records = {}
    for path in sorted((calib / "courses").glob("*/*/result.json")):
        course = read(path)
        if course["series_sha256"] != sha(path.with_name("series.npz")):
            raise ValueError(f"trajectory changed {path}")
        records[path.parent] = course
        inputs.append(path)
    if len(records) != 382:
        raise ValueError("expected 382 complete native mechanical comparisons")
    bank = read(HERE / "handoff-physics-sensor-preview-freeze.public.json")
    if len(bank["names"]) != 24 or any(n.startswith(("new", "fresh")) for n in bank["names"]):
        raise ValueError("trajectory partition changed")
    optical = {}
    for group, directory in (("fit", "candidate-closure-gpu-fit-01"), ("fresh", "candidate-closure-gpu-new-01")):
        path = raw / directory / "index.json"
        index = read(path)
        inputs.append(path)
        for row in index["courses"]:
            for frame in row["captures"]:
                if sha(path.parent / frame["frame"]) != frame["sha256"]:
                    raise ValueError("changed RGB-D evidence")
        optical[group] = {}
        for candidate in sorted({v["candidate"] for v in index["courses"]}):
            cases = [v for v in index["courses"] if v["candidate"] == candidate]
            frames = [cap for v in cases for cap in v["captures"]]
            optical[group][candidate] = dict(
                poses=len(cases), frames=len(frames), pass_frames=sum(f["allowed"] for f in frames),
                poses_passing_all_three=sum(all(f["allowed"] for f in row["captures"]) for row in cases),
                reasons=dict(Counter(f["reason"] or "PASS" for f in frames)),
                measured_closure_heights_m=[v["measured_closure_height_m"] for v in cases],
            )
    new = []
    for name in ("freshA", "freshB", "freshC", "freshD", "freshE", "freshF"):
        prefix = calib / "prefix" / name
        selection = read(prefix / "selection.json")
        inputs.extend([prefix / "prefix.json", prefix / "selection.json"])
        if selection["freeze_sha256"] != sha(HERE / "handoff-physics-sensor-preview-freeze.public.json"):
            raise ValueError("postfreeze selection did not bind locked bank")
        choice = selection["selection"]["choice"]
        vals = {}
        for key in dict.fromkeys([NOMINAL, FIXED, *([choice] if choice else [])]):
            course = records[calib / "courses" / name / key]
            clock = course["source_return_step"]
            elapsed = []
            for action in course["actions"]:
                elapsed.append((action["end"] - clock) / 240)
                clock = action["end"]
            vals[key] = {k: course[k] for k in (
                "eligible", "grasp_bilateral", "last_120_bilateral_over_50mm", "stable_inside",
                "actual_structure_contact_steps", "lift_peak_lateral_m", "lift_120_min_gain_m",
                "terminal_stage", "terminal_error", "terminal_grasp_force_N"
            )} | {"longest_observed_native_action_s": max(elapsed)}
        new.append({"case": name, "registered_choice": choice, "outcomes": vals})
    wrenches = raw / "candidate-contact-wrenches-01/index.json"
    inputs.append(wrenches)
    for row in read(wrenches)["courses"]:
        if sha(wrenches.parent / row["contact_file"]) != row["contact_sha256"]:
            raise ValueError("changed native wrench manifold")
    live = {}
    for name in ("t01", "t02"):
        same = raw / "live-native-optical-lift-gpu-01" / name / "live.json"
        inputs.append(same)
        x = read(same)
        for frame_dir in ("physical-optics-gpu-01",):
            inputs.append(raw / frame_dir / name / "index.json")
        modes = {}
        for label, directory, mode in (("registered", "live-candidate-paired-gpu-01", "original"),
                                      ("height18", "live-candidate-paired-gpu-01", "rule"),
                                      ("height22", "live-refined-paired-gpu-01", "rule")):
            path = raw / directory / name / mode / "results.json"
            inputs.append(path)
            result = read(path)
            for frame in result["frames"]:
                if sha(path.parent / frame["file"]) != frame["file_sha"]:
                    raise ValueError("changed original-prefix live RGB-D")
            modes[label] = {k: result[k] for k in (
                "actual_control_lift_lateral_peak_m", "actual_held_over_50mm_for_120", "forbidden_contact_steps"
            )} | {"actions": [{k: a[k] for k in ("skill", "success", "start", "end", "code")} for a in result["actions"]]}
        live[name] = {"identical_approach_return": {k: x[k] for k in (
            "achieved_lateral_peak_m", "lift_success", "lift_error", "live_provider_max_target_change_m",
            "actual_LIFT_movement_feedback_count", "max_native_feedback_and_IK_ms",
            "physical_fixed_target_trajectory_maximum_residual_on_common_steps")}, "reexecute_approach": modes}
    paths = {p.relative_to(root).as_posix(): sha(p) for p in sorted(set(inputs))}
    return {
        "schema": "g1.corridor-physical-results.v1", "qualification": False, "formal": 0, "hardware": 0,
        "reserved_native_eval_slots_consumed": 0,
        "physical_native_course_counts": {"coarse_fit": 72, "first_frozen_four": 8,
            "refined_same_six_fit": 180, "additional_18_fitting_poses": 108, "final_six_frozen": 14},
        "refined_bank_full_physical_success_per_24": {k: sum(v) for k, v in bank["success"].items()},
        "fresh_six_native": new, "optical_grasp_gate": optical, "source_live": live,
        "fresh_contact_wrenches": read(wrenches)["courses"], "bindings": paths,
        "scope": "Candidate course certificates use a real original controller and frozen optical return, followed by fixed nominal waypoints. Three-skill new-frame diagnostic and earlier seven-transition actual stopping branches remain separately identified. No candidate establishes complete qualification.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    result = generate(args.root.resolve())
    output = HERE / "handoff-physics-results.public.json"
    if args.verify:
        if result != read(output):
            raise ValueError("sealed readback mismatch")
    else:
        with output.open("x") as f:
            json.dump(result, f, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
            f.write("\n")
    print(len(result["bindings"]), sha(output))
