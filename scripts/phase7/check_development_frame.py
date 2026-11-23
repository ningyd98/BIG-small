"""Read a fresh v10 registration and verify one settled RGB-D frame and its bootstrap."""

from __future__ import annotations

import argparse
from base64 import b64decode
from dataclasses import asdict
from io import BytesIO
from math import isclose
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from cloud_edge_robot_arm.research.native_calibration_collection import (
    REGISTERED_TEACHER_V10_SCHEMA,
    ROOT,
    detached,
    fresh_directory,
    load_json,
    read_protocol,
    save_exclusive,
)
from cloud_edge_robot_arm.research.native_collection_grounding import (
    collection_bootstrap_evidence,
    validate_camera,
)
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig
from cloud_edge_robot_arm.simulation.mujoco.backend import (
    BackendOperationBoundary,
    MuJoCoPhysicsBackend,
)
from cloud_edge_robot_arm.vision.native_calibration import NativeGeometryRegistration
from cloud_edge_robot_arm.vision.observations import RGBDObservation, observation_from_sensor_frame
from cloud_edge_robot_arm.vision.pose_markers import detect_pose_marker
from cloud_edge_robot_arm.vision.top_grasp import matches_calibrated_gripper


def check_frame(protocol_path: Path, output: Path) -> None:
    protocol = read_protocol(protocol_path)
    if protocol["schema_version"] != REGISTERED_TEACHER_V10_SCHEMA:
        raise ValueError("a v10 teacher registration is required")
    output = fresh_directory(output)
    geometry = NativeGeometryRegistration(protocol["geometry"])
    geometry.validate_asset(ROOT)
    marker = geometry.pose_marker
    (assignment,) = protocol["released_assignments"]
    (seed,) = (r["seed"] for r in protocol["assignments"] if r["assignment_id"] == assignment)
    config = SimulatorConfig(
        model_path=protocol["settings"]["model_path"],
        seed=seed,
        physics_dt_s=1 / 240,
        domain_randomization=False,
        render_rgb=True,
        render_depth=True,
    )
    backend = MuJoCoPhysicsBackend()
    captures: list[BackendOperationBoundary] = []

    def record_capture(event: BackendOperationBoundary) -> None:
        if event.kind == "CAPTURE":
            captures.append(event)

    try:
        backend.initialize(config)
        assert matches_calibrated_gripper(backend._model, protocol["settings"]["grasp_profile"])
        with (
            backend.observe_operation_boundaries(record_capture),
            backend.sensor_capture_on_demand(),
        ):
            backend.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=seed))
            backend.step(120)
        begin, end = captures
        assert not backend.operation_observer_failures
        assert (begin.phase, end.phase) == (
            "BEGIN",
            "END",
        ) and begin.operation_id == end.operation_id
        assert begin.physics_step == end.physics_step == backend.total_physics_steps == 120
        assert end.error_type is None and end.result is not None
        render_states = tuple(end.result["pass_state_hashes"])
        assert (
            len(render_states) == 2
            and len(set(render_states)) == 1
            and not end.result["instance_ids"]
        )
        frame = backend.get_sensor_frame()
        assert frame.frame_id == end.result["sensor_frame"]["frame_id"]
        assert isclose(frame.sim_time_s, 0.5, abs_tol=1e-12) and not backend.command_records
        original = observation_from_sensor_frame(frame, source="mujoco_camera")
        save_exclusive(output / "observation.json", original.model_dump(mode="json"))
        observation = RGBDObservation.model_validate(load_json(output / "observation.json"))
        assert observation == original
        validate_camera(observation, protocol["geometry"])
        with Image.open(BytesIO(b64decode(observation.rgb_png_base64))) as image:
            assert image.size == (320, 240) and image.mode == "RGB" and image.tobytes() == frame.rgb
        mask = observation.valid_mask_bytes()
        assert mask == frame.valid_mask and set(mask) <= {0, 1}
        valid = np.frombuffer(mask, dtype=np.uint8) == 1
        depth_bytes = b64decode(observation.depth_float32_base64)
        assert depth_bytes == np.asarray(frame.depth, dtype="<f4").tobytes()
        depth = np.frombuffer(depth_bytes, dtype="<f4")
        assert len(depth) == len(valid) == 320 * 240 and valid.any()
        assert (
            np.isfinite(depth[valid]).all()
            and (depth[valid] > 0).all()
            and (depth[~valid] == 0).all()
        )
        diagnostics: dict[str, Any] = {}
        estimate = detect_pose_marker(
            observation, marker, corner_refinement="SUBPIX", diagnostics=diagnostics
        )
        save_exclusive(
            output / "marker.json",
            detached({"estimate": asdict(estimate), "diagnostics": diagnostics}),
        )
        assert (
            marker.marker_id == 7
            and estimate.status == "OBSERVED"
            and estimate.observed_marker_ids == (7,)
        )
        assert estimate.registration_hash == marker.digest()
        assert estimate.measured_min_side_px is not None and estimate.measured_min_side_px >= 8
        assert estimate.observation_checksum_sha256 == observation.checksum_sha256
        bootstrap = collection_bootstrap_evidence(observation, protocol["geometry"])
        save_exclusive(output / "bootstrap.json", detached(bootstrap))
    finally:
        backend.shutdown()
    save_exclusive(
        output / "receipt.json",
        {
            "scope": "DEVELOPMENT_SINGLE_FRAME",
            "source_generation": protocol["source_generation"],
            "registered_sources": len(protocol["source_hashes"]),
            "physics_steps": end.physics_step,
            "rgbd_frames": len(captures) // 2,
            "render_passes": len(render_states),
            "formal_claims": 0,
            "controller_actions": 0,
            "teacher_attempts": 0,
            "backend_closed": True,
            "width": observation.width,
            "height": observation.height,
            "valid_depth_pixels": int(valid.sum()),
            "marker_family": geometry.marker_family_id,
            "marker_id": marker.marker_id,
            "marker_status": estimate.status,
            "min_side_px": estimate.measured_min_side_px,
            "bootstrap": "PASS",
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    check_frame(args.protocol, args.output)
