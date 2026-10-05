"""Actual clean RGB-D diagnostic; no metric bound or task success is invented."""
import base64
import hashlib
import io
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from cloud_edge_robot_arm.datasets.rgbd.models import SceneSpec
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession, save_captured_frame
from cloud_edge_robot_arm.vision.tracking import OpenCVTargetTracker

base = Path(__file__).resolve().parent / "t7b-real-clean-capture-3"
base.mkdir(exist_ok=False)
row = json.loads((base.parent / "t8-real-raw-development/assignment.json").read_text())
scene = SceneSpec.model_validate(row["scene"])
color = scene.scene_parameters["target"]["color_name"]

with MuJoCoCaptureSession(SimulatorConfig(domain_randomization=False)) as session:
    session.apply_scene(scene)
    session._backend.step(120)
    frame = session.capture_with_instances()
    observation = frame.observation
    save_captured_frame(frame, base / "initial")
    (base / "initial/observation-full.json").write_text(
        observation.model_dump_json(indent=2) + "\n")
    rgb = np.asarray(Image.open(io.BytesIO(base64.b64decode(
        observation.rgb_png_base64))).convert("RGB"))
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    saturated = (hsv[:, :, 1] > 70) & (hsv[:, :, 2] > 40)
    hue = hsv[:, :, 0]
    color_masks = {
        "yellow": saturated & (hue > 18) & (hue < 36),
        "blue": saturated & (hue > 90) & (hue < 130),
        "red": saturated & ((hue < 12) | (hue > 168)),
    }
    target = color_masks[color]
    region = saturated & (hue > 35) & (hue < 90)

    def pixel(mask):
        y, x = np.nonzero(mask)
        if not len(x):
            raise ValueError("instruction color absent from actual RGB")
        return [int(np.median(x)), int(np.median(y))]

    x, y = pixel(target)
    depth = np.frombuffer(base64.b64decode(observation.depth_float32_base64),
                          dtype="<f4").reshape(observation.height, observation.width)
    ys, xs = np.mgrid[max(y - 18, 0):min(y + 19, observation.height),
                      max(x - 18, 0):min(x + 19, observation.width)]
    points = OpenCVTargetTracker._points(
        observation, xs.ravel(), ys.ravel(), depth[ys, xs].ravel())
    outside = ((~target[ys, xs]).ravel() & (~region[ys, xs]).ravel()
               & (depth[ys, xs].ravel() > 0))
    grounding = {"original_pixel_target": [x, y],
                 "original_pixel_destination": pixel(region),
                 "top_grasp_support_height_m": float(np.median(points[outside, 2]))}
    try:
        tracker = OpenCVTargetTracker(observation, grounding)
        facts = tracker.facts(observation)
        status, reason = "VISIBLE_METRIC_UNKNOWN", None
    except ValueError as exc:
        facts = {}
        status, reason = "UNKNOWN", str(exc)
    assessment = {
        "kind": "REAL_CAPTURE", "scope": "DEVELOPMENT_ONLY",
        "reuse_group": scene.group_id, "target_instruction_color": color,
        "grounding": grounding,
        "grounding_source": "instruction color + actual RGB/depth; no instance or truth input",
        "actual_sensor_noise_std_m": session._backend._sensor_noise_std_m,
        "algorithm_sha256": hashlib.sha256(Path(
            "src/cloud_edge_robot_arm/vision/tracking.py").read_bytes()).hexdigest(),
        "depth_bound": "UNAVAILABLE", "status": status, "reason": reason,
        "model_requests": 0, "robot_actions": 0, "physical_success": "NOT_RUN",
        "facts": facts,
    }
    (base / "assessment.json").write_text(json.dumps(assessment, indent=2) + "\n")
    print(json.dumps({key: value for key, value in assessment.items() if key != "facts"}))
