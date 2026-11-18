"""Trace the original region decision on archived RGBD without live TTL evaluation."""

import argparse
import base64
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

from cloud_edge_robot_arm.vision.marker_families import marker_family
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.pose_markers import PoseMarkerRegistration, detect_pose_marker
from cloud_edge_robot_arm.vision.servo_region import measure_servo_region
from cloud_edge_robot_arm.vision.tracking import OpenCVTargetTracker


class ArchivedReferenceTracker(OpenCVTargetTracker):
    """Build immutable reference geometry at its historical capture time."""

    def _binding_reason(self, observation):
        return self._binding_reason_at(observation, self._reference.captured_at)


def read_json(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_frame(folder):
    metadata = read_json(folder / "observation.json")
    payload = {
        key: metadata[key]
        for key in RGBDObservation.model_fields.keys() & metadata.keys()
    }
    for key, name in {
        "rgb_png_base64": "rgb.png",
        "depth_float32_base64": "depth.f32",
        "valid_mask_base64": "valid_mask.u8",
    }.items():
        payload[key] = base64.b64encode((folder / name).read_bytes()).decode()
    observation = RGBDObservation.model_validate(payload)
    for key in ("rgb_sha256", "depth_sha256", "checksum_sha256"):
        assert observation.evidence()[key] == metadata[key]
    return observation


def trace_geometry(observation, tracker):
    state = {}

    def collect(frame, event, _value):
        if frame.f_code is not measure_servo_region.__code__:
            return None
        if event == "return":
            state.update(frame.f_locals)
        frame.f_trace_lines = False
        return collect

    previous = sys.gettrace()
    try:
        sys.settrace(collect)
        support, reason = measure_servo_region(observation, tracker)
    finally:
        sys.settrace(previous)
    return support, reason, state


def describe_frame(folder, tracker, registration, mask_dir):
    observation = load_frame(folder)
    support, reason, state = trace_geometry(observation, tracker)
    marker = detect_pose_marker(observation, registration, corner_refinement="SUBPIX")
    description = {
        "frame": str(folder),
        "bindings": observation.evidence(),
        "sha256": {file.name: sha(file) for file in sorted(folder.iterdir()) if file.is_file()},
        "marker_status": marker.status,
        "marker_reason": marker.reason,
        "strict_region_support": support,
        "strict_region_rejection": reason,
    }
    masks = {}
    for key in ("expected", "color", "selected", "visible_plane", "core", "valid", "missing"):
        if key in state:
            masks[key] = state[key].astype(bool)
    if "missing" in masks:
        masks["missing_valid_depth"] = masks["missing"] & masks["valid"]
        masks["missing_invalid_depth"] = masks["missing"] & ~masks["valid"]
        masks["color_off_plane"] = masks["selected"] & ~masks["visible_plane"]
    if "corners" in state:
        description["projected_corners_xy"] = state["corners"].tolist()
        description["unrounded_projected_corners_xy"] = state["pixels"].tolist()
    if "anchors" in state:
        description["corner_support"] = [
            bool(state["visible_plane"][y - 1:y + 2, x - 1:x + 2].any())
            for x, y in state["corners"]
        ]
        description["observed_corner_anchors"] = state["anchors"]
    if "plane" in state:
        description["region_plane_z_m"] = state["plane"]
        description["plane_band_m"] = state["span"]
        description["certified_depth_bound_m"] = state["bound"] or None
    if "foreground" in state:
        ys, xs = state["ys"], state["xs"]
        world = state["foreground"]
        position = (ys, xs)
        threshold = np.maximum(state["span"] + state["bound"], state["z_footprint"])
        high = world[:, 2] > state["plane"] + threshold
        vector_masks = {"high_foreground": high}
        for key in (
            "positive_side", "target_side_color", "connected", "sidewall", "mixed_footprint",
        ):
            if key in state:
                vector_masks[key] = state[key]
        unsupported = ~high
        if "sidewall" in state:
            unsupported &= ~state["sidewall"] & ~state["mixed_footprint"]
        vector_masks["unsupported_missing_color"] = unsupported
        for key, vector in vector_masks.items():
            target = np.zeros(masks["missing"].shape, dtype=bool)
            target[position] = vector
            masks[key] = target
        description["unexplained_pixels"] = [
            {
                "pixel_xy": [int(xs[i]), int(ys[i])],
                "rgb": state["rgb"][ys[i], xs[i]].astype(int).tolist(),
                "optical_z_m": float(state["depth"][ys[i], xs[i]]),
                "world_xyz_m": world[i].tolist(),
                "height_above_region_plane_m": float(world[i, 2] - state["plane"]),
                "propagated_footprint_z_m": float(state["z_footprint"][i]),
                "high_foreground_margin_m": float(threshold[i]),
                "registered_rgb_mix_weight": float(state["weight"][i]),
                "adjacent_to_measured_foreground": bool(
                    state["near_measured_foreground"][ys[i], xs[i]]
                ),
                **{key: bool(vector[i]) for key, vector in vector_masks.items()},
            }
            for i in np.flatnonzero(unsupported)
        ]
    description["mask_counts"] = {name: int(mask.sum()) for name, mask in masks.items()}
    if masks:
        dest = mask_dir / f"{folder.name}.npz"
        assert not dest.exists()
        np.savez_compressed(dest, **masks)
        description["masks_file"] = {"path": dest.name, "sha256": sha(dest)}
    return description


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    tracker_folder = args.archive / "component/frames/post-cloud"
    reference = load_frame(tracker_folder)
    planning = read_json(args.archive / "planning/planning-stage-02.json")
    grounding = planning["attempts"][-1]["draft"]["observation_evidence"]
    tracker = ArchivedReferenceTracker(reference, grounding)
    assignment = read_json(args.archive / "scene-assignment.json")
    family = marker_family(assignment["marker_family_id"])
    registration = PoseMarkerRegistration(
        marker_id=family.marker_id, marker_size_m=family.marker_size_m,
        dictionary=family.dictionary, marked_asset_sha256=family.asset_sha256,
    )
    step = args.archive / "component/servo-frames/step-05"
    names = ("reference", "sample-0104", "sample-0105", "sample-0105-view-01")
    frames = [describe_frame(step / name, tracker, registration, args.output) for name in names]
    report = {
        "scope": "ARCHIVED_RGBD_GEOMETRY_ONLY_NO_LIVE_TTL_OR_CONTROL",
        "tracker_reference": {
            "path": str(tracker_folder),
            "bindings": reference.evidence(),
            "historical_reference_evaluated_at": reference.captured_at.isoformat(),
            "sha256": {name: sha(tracker_folder / name) for name in (
                "observation.json", "rgb.png", "depth.f32", "valid_mask.u8",
            )},
            "target_pixel_xy": list(tracker.target_pixel),
            "destination_pixel_xy": list(tracker.destination_pixel),
            "region_uncertainty_m": tracker.destination["uncertainty_m"],
        },
        "region_source_sha256": sha(Path(measure_servo_region.__code__.co_filename)),
        "frames": frames,
    }
    (args.output / "diagnostic.json").write_text(json.dumps(report, indent=2) + "\n")
    assert frames[-1]["strict_region_rejection"] == (
        "region_missing_color_not_explained_by_foreground"
    )
    assert frames[-1]["unexplained_pixels"]
    assert frames[-2]["marker_status"] == "UNKNOWN"


if __name__ == "__main__":
    main()
