"""Read-only recheck of the current-capability test and retained local raw."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))


def read(path: Path) -> Any:
    return json.loads(path.read_text())


def capture_gap_ms(frames: list[dict[str, Any]]) -> float:
    times = [datetime.fromisoformat(frame["captured_at"]) for frame in frames]
    return max((b - a).total_seconds() * 1000
               for a, b in zip(times, times[1:], strict=False))


def main() -> None:
    from scripts.verify_visual_servo import case_passed

    from cloud_edge_robot_arm.vision.observations import RGBDObservation

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-root", type=Path)
    args = parser.parse_args()
    process = Path(__file__).resolve().parent
    manifest = read(process / "raw-manifest.json")
    raw = args.raw_root or Path(manifest["root"])
    for relative, expected in manifest["files"].items():
        if hashlib.sha256((raw / relative).read_bytes()).hexdigest() != expected:
            raise ValueError(f"raw checksum mismatch: {relative}")
    sources = read(process / "source-manifest.json")
    for relative, expected in sources["files"].items():
        if hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() != expected:
            raise ValueError(f"current source differs from tested source: {relative}")

    observed_ids: set[str] = set()
    frame_count = 0

    def frames(folder: Path) -> None:
        nonlocal frame_count
        for metadata in folder.rglob("observation.json"):
            values = {k: v for k, v in read(metadata).items()
                      if k in RGBDObservation.model_fields}
            for field, name in (("rgb_png_base64", "rgb.png"),
                                ("depth_float32_base64", "depth.f32"),
                                ("valid_mask_base64", "valid_mask.u8")):
                values[field] = base64.b64encode((metadata.parent / name).read_bytes()).decode()
            observation = RGBDObservation.model_validate(values)
            observed_ids.add(observation.observation_id)
            frame_count += 1

    visual = []
    workers = []
    for repeat in range(1, 4):
        folder = raw / f"visual-{repeat:02d}"
        frames(folder)
        for result in read(folder / "summary.json")["results"]:
            case = folder / result["case"]
            passed = case_passed(result)
            if not passed:
                raise ValueError(f"development gate failed: {repeat}/{result['case']}")
            control = read(case / "control-samples.json")
            if any(b["physics_step"] - a["physics_step"] != 8
                   for a, b in zip(control, control[1:], strict=False)):
                raise ValueError("visual cadence differs from eight physics steps")
            last = read(case / "physical-evidence.json")[-1]
            error = math.dist(last["tcp_position_m"][:2], last["object_position_m"][:2])
            if result["case"] != "loss" and not math.isclose(
                error, result["independent_horizontal_error_m"], abs_tol=1e-10
            ):
                raise ValueError("endpoint error differs from independent physical evidence")
            commands = read(case / "commands.json")
            if commands[-1]["type"] != "hold_current_joints":
                raise ValueError("motion did not end with hold")
            if result["case"] == "loss" and any(
                command["type"] == "joint_target"
                and command["physics_step"] >= result["loss_injected_at_step"]
                for command in commands
            ):
                raise ValueError("joint command submitted after loss")
            visual.append({
                "repeat": repeat, "development_gate_passed": passed,
                **{k: v for k, v in result.items() if k not in {
                    "scope", "semantic_nomination", "formal_research", "hardware_dispatch",
                }},
                "max_wall_capture_interval_ms": capture_gap_ms(read(case / "frames.json")[2:]),
            })

        episodes = list((raw / f"worker-{repeat:02d}").rglob("component/episode.json"))
        if len(episodes) != 1:
            raise ValueError("expected exactly one worker episode per repeat")
        episode = read(episodes[0])
        frames(episodes[0].parent / "servo-frames")
        checks = [check for check in episode["safety_checks"] if check["phase"] == "SERVO"]
        if not all(check["observation_id"] in observed_ids for check in checks):
            raise ValueError("a dynamic safety check lacks raw RGBD")
        actions = []
        for action in episode["actions"]:
            servo = action.get("visual_servo", {})
            samples = servo.get("control_samples", [])
            actions.append({
                "skill": action["skill"],
                "controller_success": action.get("controller_result", {}).get("success"),
                "accepted_feedback": len(samples),
                "wall_feedback_hz": (len(samples) - 1) / (
                    samples[-1]["wall_elapsed_s"] - samples[0]["wall_elapsed_s"]
                ) if len(samples) > 1 else None,
                "max_sample_and_ik_ms": max(
                    (s["sample_and_ik_s"] * 1000 for s in samples), default=None
                ),
                "max_wall_capture_interval_ms": capture_gap_ms(servo["visual_samples"])
                if len(servo.get("visual_samples", [])) > 1 else None,
            })
        workers.append({
            "repeat": repeat, "physical_success": episode["physical_success"],
            "terminal_reason": episode["terminal_reason"],
            "blocking_rule": checks[-1]["verdict"]["limiting_rule"],
            "dynamic_checks_with_raw": len(checks), "actions": actions,
            "software_model_protocol_requests": episode["model_calls"],
            "paid_model_calls": 0,
        })

    match = re.search(r"(\d+) passed in ([\d.]+)s", (raw / "targeted_tests-01.log").read_text())
    if match is None:
        raise ValueError("missing completed targeted-test result")
    records = read(raw / "run-results.json")
    print(json.dumps({
        "evidence_valid": True, "base_commit": sources["base_commit"],
        "scope": "FIXED_SCENE_REPEATABILITY_NOT_NEW_SEED_GENERALIZATION",
        "raw_files_checked": len(manifest["files"]),
        "source_files_checked": len(sources["files"]),
        "rgbd_reconstructed_and_checksum_validated": frame_count,
        "all_test_commands_exit_zero": all(record["returncode"] == 0 for record in records),
        "targeted_tests_passed": int(match[1]), "targeted_tests_wall_s": float(match[2]),
        "visual_development_passes": sum(row["development_gate_passed"] for row in visual),
        "visual_cases": visual, "worker_runs": workers,
        "worker_full_task_successes": sum(worker["physical_success"] for worker in workers),
        "paid_model_calls": 0, "hardware_dispatch": False, "formal_research": "NOT_ACCEPTED",
    }, indent=2))


if __name__ == "__main__":
    main()
