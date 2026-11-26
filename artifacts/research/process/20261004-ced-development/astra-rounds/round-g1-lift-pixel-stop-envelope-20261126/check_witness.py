"""Verify the sealed prediction and old needle's actual archived discrete sweep."""

import argparse
from itertools import combinations
from xml.etree import ElementTree as ET

import numpy as np
from read_envelopes import HERE, OUT, PLAN, ROOT, pinned, require, save
from scripts.graduation.perception_io import read, sha

TRIPLES = np.array(list(combinations(range(12), 3)))


def overlap_vertices(center, orientation, half, pin_center, pin_half):
    outward = np.vstack((orientation.T, -orientation.T, np.eye(3), -np.eye(3)))
    limits = np.r_[
        outward[:6] @ center + np.tile(half, 2), outward[6:] @ pin_center + np.tile(pin_half, 2)
    ]
    matrix = outward[TRIPLES]
    valid = np.abs(np.linalg.det(matrix)) > 1e-10
    vertices = np.linalg.solve(matrix[valid], limits[TRIPLES[valid], None])[..., 0]
    return vertices[np.all(vertices @ outward.T <= limits + 1e-10, axis=1)]


def original_projection(camera, points):
    transform = np.asarray(camera["camera_to_world"]).reshape(4, 4)
    camera_points = (points - transform[:3, 3]) @ transform[:3, :3]
    fx, fy, cx, cy = camera["intrinsics"]
    image = camera_points[:, :2] * [fx, fy] / camera_points[:, 2, None] + [cx, cy]
    return np.column_stack((image, camera_points[:, 2]))


def needle_witness():
    needle = PLAN["old_needle"]
    trace = ROOT / needle["trace"]
    receipt = read(trace.with_name("receipt.json"))
    (observed,) = [row for row in receipt["stages"] if row["mode"] == "observed"]
    (stop,) = [row for row in observed["stops"] if row["step"] == 2112]
    require(stop["sha256"] == sha(trace), "attempt to substitute the old stop")
    root = ET.parse(ROOT / needle["xml"]).getroot()
    original = ET.parse(ROOT / PLAN["asset"]).getroot()
    pin = root.find("worldbody/geom[@name='diagnostic_pin']")
    cube = original.find(".//geom[@name='object_geom']")
    require(
        pin.get("type") == "box"
        and set(pin.attrib).isdisjoint({"quat", "euler", "axisangle", "zaxis", "xyaxes", "fromto"}),
        "unexpected old needle frame",
    )
    center = np.fromstring(pin.attrib["pos"], sep=" ")
    pin_half = np.fromstring(pin.attrib["size"], sep=" ")
    cube_half = np.fromstring(cube.attrib["size"], sep=" ")
    with np.load(trace, allow_pickle=False) as data:
        centers, rotations = data["centers"][:, 10], data["rotation"][:, 10]
    require(
        centers.shape == (241, 3)
        and rotations.shape == (241, 3, 3)
        and np.isfinite(centers).all()
        and np.isfinite(rotations).all(),
        "archived stop shape differs",
    )
    camera = read(ROOT / PLAN["calibration"] / "manifest.json")["primary_camera"]
    every = []
    for tick, (c, r) in enumerate(zip(centers, rotations, strict=True)):
        vertices = overlap_vertices(c, r, cube_half, center, pin_half)
        if len(vertices):
            every.append((tick, original_projection(camera, vertices)))
    bounds = np.concatenate([points for _, points in every])
    expected = np.asarray(needle["pixel"])
    require(
        every[0][0] == needle["relative_tick"]
        and len(every) == needle["intersections"]
        and np.all(np.abs(bounds[:, :2] - expected) <= 0.5),
        "old intersecting subpixel witness failed",
    )
    return {
        "native_discrete_pose_count": len(centers),
        "first_intersection_stop_step": every[0][0],
        "intersecting_discrete_poses": len(every),
        "projection_uv_and_axial_bounds": [bounds.min(0).tolist(), bounds.max(0).tolist()],
        "old_trace_sha256": sha(trace),
    }


def identify_alias():
    raw = ROOT / "experiments/results/g1-same-view-needle-sampling-20261126/capture-01"
    members = read(raw / "seal.json")["members"]
    index = read(pinned(raw, "index.json", members["index.json"]))
    candidates = [row for row in index["frames"] if row["step"] == 2112 and row["scale"] == 1]
    require([row["model"] for row in candidates] == ["bare", "pin"], "old optical pair missing")
    bare, pin = candidates
    exempt = {"file", "model", "frame_id", "capture_ns"}
    require(
        {k: v for k, v in bare.items() if k not in exempt}
        == {k: v for k, v in pin.items() if k not in exempt}
        and bare["frame_id"] != pin["frame_id"],
        "old optical pair mismatched",
    )
    paths = [pinned(raw, row["file"], row["file_sha256"]) for row in candidates]
    require(all(members[path.name] == sha(path) for path in paths), "unsealed old optical packet")
    require(paths[0].read_bytes() == paths[1].read_bytes(), "old 320 pair differs")
    return {
        "bare_and_pin_RGB_depth_mask_identical": True,
        "original_camera_pair_sha256": sha(paths[0]),
        "original_source_frame_id": bare["original_frame_id"],
        "registered_seed": bare["seed"],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prediction-sha", required=True)
    args = parser.parse_args()
    prediction = pinned(OUT, "prediction.json", args.prediction_sha)
    pinned(OUT, "prediction.cold.json", args.prediction_sha)
    require(read(prediction)["plan_sha256"] == sha(HERE / "plan.json"), "prediction plan drift")
    for name, digest in PLAN["control_sha256"].items():
        pinned(ROOT, name, digest)
    for name, location in PLAN["captures"].items():
        folder = ROOT / location
        members = read(folder / "seal.json")["sealed_sha256"]
        require(len(members) == PLAN["seal_members"][name], "sealed members count changed")
        for path, hexdigest in members.items():
            pinned(folder, path, hexdigest)
    save(
        "needle-witness.json",
        {
            "prediction_sha256": args.prediction_sha,
            "native_optical_alias": identify_alias(),
            "old_no_pin_stop_with_pin_geometry": needle_witness(),
            "new_trial_stop_sweeps_verified": 0,
        },
    )


if __name__ == "__main__":
    main()
