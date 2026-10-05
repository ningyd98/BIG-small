"""Save one real MuJoCo RGB-D capture and an independent table-plane measurement."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession, save_captured_frame


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/research/process/20261003-phase1/capture"),
    )
    args = parser.parse_args()
    with MuJoCoCaptureSession(SimulatorConfig(render_rgb=True, render_depth=True)) as session:
        captured = session.capture_with_instances()
        paths = save_captured_frame(captured, args.output)
    table_ids = [key for key, label in captured.instance_labels.items() if label == "table"]
    if len(table_ids) != 1:
        raise RuntimeError("expected one rendered table geom")
    width = captured.observation.width
    table_pixels = [
        (index % width, index // width)
        for index, geom_id in enumerate(captured.instance_ids)
        if geom_id == table_ids[0]
    ]
    valid_mask = captured.observation.valid_mask_bytes()
    valid_pixels = [
        pixel
        for pixel in table_pixels
        if valid_mask[pixel[1] * width + pixel[0]]
    ]
    if len(valid_pixels) < 1000:
        raise RuntimeError("too few valid rendered table pixels")
    sampled = valid_pixels[:: max(1, len(valid_pixels) // 100)][:100]
    # scene.xml: table centre z=-0.025 m, half-height=0.025 m, top plane z=0.
    plane_z_m = 0.0
    errors = [abs(captured.observation.world_point(pixel).z - plane_z_m) for pixel in sampled]
    if max(errors) > 0.005:
        raise RuntimeError(f"table-plane back-projection exceeds 5 mm: {max(errors):.6f} m")
    measurement = {
        "reference": "assets/robots/franka_panda/scene.xml table top plane z=0 m",
        "sample_count": len(sampled),
        "table_visible_valid_pixel_count": len(valid_pixels),
        "max_abs_z_error_m": max(errors),
        "mean_abs_z_error_m": sum(errors) / len(errors),
        "threshold_m": 0.005,
        "physics_state_hash": captured.physics_state_hash,
        "pass_state_hashes": list(captured.pass_state_hashes),
        "observation_id": captured.observation.observation_id,
        "episode_id": captured.observation.episode_id,
        "scene_id": captured.observation.scene_id,
        "calibration_version": captured.observation.calibration_version,
        "renderer_closed_after_session": session._backend._camera is None,
        "file_sha256": {
            name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in paths.items()
        },
    }
    measurement_path = args.output / "measurement.json"
    measurement_path.write_text(
        json.dumps(measurement, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"measurement": str(measurement_path), **measurement}, ensure_ascii=False))


if __name__ == "__main__":
    main()
