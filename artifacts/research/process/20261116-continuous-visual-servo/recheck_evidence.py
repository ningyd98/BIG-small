"""Read-only local recheck of the development evidence retained with this change."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))


def main() -> None:
    from scripts.verify_visual_servo import case_passed

    from cloud_edge_robot_arm.vision.observations import RGBDObservation

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-root", type=Path)
    parser.add_argument("--worker-root", type=Path)
    args = parser.parse_args()
    process = Path(__file__).resolve().parent
    manifests = [
        (process / "raw-manifest.json", args.raw_root),
        (process / "worker-raw-manifest.json", args.worker_root),
    ]
    roots = []
    file_count = 0
    for path, override in manifests:
        manifest = json.loads(path.read_text())
        root = override or Path(manifest["root"])
        roots.append(root)
        for relative, expected in manifest["files"].items():
            actual = hashlib.sha256((root / relative).read_bytes()).hexdigest()
            if actual != expected:
                raise ValueError(f"raw checksum mismatch: {relative}")
            file_count += 1
    raw, worker = roots
    protocol = json.loads((raw / "protocol.json").read_text())
    for relative, expected in protocol["source_sha256"].items():
        if hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() != expected:
            raise ValueError(f"current source differs from validated source: {relative}")

    observations = {}
    frame_count = 0
    for folder in (raw, worker / "component/servo-frames"):
        for metadata in folder.rglob("observation.json"):
            values = json.loads(metadata.read_text())
            values = {k: v for k, v in values.items() if k in RGBDObservation.model_fields}
            for field, filename in (
                ("rgb_png_base64", "rgb.png"),
                ("depth_float32_base64", "depth.f32"),
                ("valid_mask_base64", "valid_mask.u8"),
            ):
                values[field] = base64.b64encode((metadata.parent / filename).read_bytes()).decode()
            observation = RGBDObservation.model_validate(values)
            observations[observation.observation_id] = observation
            frame_count += 1

    summary = json.loads((raw / "summary.json").read_text())
    if {result["case"] for result in summary["results"]} != set(protocol["cases"]):
        raise ValueError("case set differs from the declared protocol")
    for result in summary["results"]:
        if not case_passed(result):
            raise ValueError(f"development gate failed: {result['case']}")
        folder = raw / result["case"]
        control = json.loads((folder / "control-samples.json").read_text())
        if any(b["physics_step"] - a["physics_step"] != 8
               for a, b in zip(control, control[1:], strict=False)):
            raise ValueError("visual cadence differs from eight physics steps")
        physical = json.loads((folder / "physical-evidence.json").read_text())
        last = physical[-1]
        error = math.dist(last["tcp_position_m"][:2], last["object_position_m"][:2])
        if result["case"] != "loss" and not math.isclose(
            error, result["independent_horizontal_error_m"], abs_tol=1e-10
        ):
            raise ValueError("independent endpoint error does not match physical evidence")
        commands = json.loads((folder / "commands.json").read_text())
        if commands[-1]["type"] != "hold_current_joints":
            raise ValueError("motion did not end with hold")
        if result["case"] == "loss" and any(
            command["type"] == "joint_target"
            and command["physics_step"] >= result["loss_injected_at_step"]
            for command in commands
        ):
            raise ValueError("joint command submitted after the loss injection")

    episode = json.loads((worker / "component/episode.json").read_text())
    checks = [check for check in episode["safety_checks"] if check["phase"] == "SERVO"]
    if not all(check["observation_id"] in observations for check in checks):
        raise ValueError("a dynamic safety check lacks archived RGBD")
    print(json.dumps({
        "valid": True,
        "raw_files_checked": file_count,
        "rgbd_reconstructed_and_checksum_validated": frame_count,
        "development_cases_passed": len(summary["results"]),
        "worker_dynamic_checks_with_raw": len(checks),
        "worker_physical_success": episode["physical_success"],
        "worker_terminal_reason": episode["terminal_reason"],
        "scope": "LOCAL_DEVELOPMENT_NOT_FORMAL_ACCEPTANCE",
    }, indent=2))


if __name__ == "__main__":
    main()
