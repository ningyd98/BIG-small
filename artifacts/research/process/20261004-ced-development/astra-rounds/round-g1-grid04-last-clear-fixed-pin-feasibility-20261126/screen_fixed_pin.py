"""Rule out the existing fixed diagnostic pin against two full pixel footprints."""

import argparse
import itertools
from pathlib import Path
from xml.etree import ElementTree

import numpy as np
from scripts.graduation.perception_io import read, sha, write

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / ".git").exists())
PLAN = read(HERE / "plan.json")
OUT = ROOT / PLAN["private_output"]
SIGNS = np.asarray(list(itertools.product((-1, 1), repeat=3)), dtype=float)
BAND = PLAN["registered_optical_band_m"]
TOL = PLAN["strict_geometric_separation_m"]


def require(ok, message):
    if not ok:
        raise ValueError(message)


def canonical(element):
    return element.tag, tuple(sorted(element.items())), tuple(canonical(child) for child in element)


def pin_layout():
    original = ElementTree.parse(ROOT / PLAN["original_xml"]).getroot()
    alias = ElementTree.parse(ROOT / PLAN["old_pin"]).getroot()
    world = alias.find("./worldbody")
    pin = world.find("./geom[@name='diagnostic_pin']")
    require(pin is not None and pin.attrib["type"] == "box", "frozen pin missing")
    require(
        not {"euler", "axisangle", "quat", "zaxis", "xyaxes"} & pin.attrib.keys(),
        "expected stationary identity orientation",
    )
    center = np.fromstring(pin.attrib["pos"], sep=" ")
    half = np.fromstring(pin.attrib["size"], sep=" ")
    require(center.shape == half.shape == (3,) and np.all(half > 0), "unsupported pin geometry")
    world.remove(pin)
    tip_material = alias.find("./asset/material[@name='diagnostic_reflective_tip']")
    require(
        tip_material is not None and pin.attrib["material"] == tip_material.attrib["name"],
        "material altered",
    )
    material = dict(tip_material.attrib)
    asset = alias.find("asset")
    asset.remove(tip_material)
    if not len(asset) and original.find("asset") is None:
        alias.remove(asset)
    return (
        center,
        half,
        {
            "pin": dict(pin.attrib),
            "material": material,
            "world_pose_only_support_not_evidenced": True,
            "original_tree_exact_after_removing_pin_and_material": canonical(alias)
            == canonical(original),
        },
    )


def world_planes(camera, u, v, start, end):
    tf = np.asarray(camera["camera_to_world"]).reshape(4, 4)
    require(np.allclose(tf[:3, :3].T @ tf[:3, :3], np.eye(3), atol=1e-12), "camera axes drift")
    fx, fy, cx, cy = camera["intrinsics"]
    x0, x1 = (np.array([u - 0.5, u + 0.5]) - cx) / fx
    y0, y1 = (np.array([v - 0.5, v + 0.5]) - cy) / fy
    norms = (
        np.array([[-1, 0, x0], [1, 0, -x1], [0, -1, y0], [0, 1, -y1], [0, 0, -1], [0, 0, 1]])
        @ tf[:3, :3].T
    )
    limits = norms @ tf[:3, 3] + [0, 0, 0, 0, -start, end]
    return norms, limits


def intersect(A, B, center, half):
    shifted = B - A @ center
    gap = (-np.abs(A) @ half - shifted) / np.linalg.norm(A, axis=1)
    corner_gap = ((center + SIGNS * half) @ A.T - B).min(axis=0) / np.linalg.norm(A, axis=1)
    require(np.allclose(gap, corner_gap, atol=1e-12), "support and corner methods disagree")
    plane = int(gap.argmax())
    if gap[plane] > TOL:
        return {
            "relation": "strictly_disjoint",
            "plane_index": plane,
            "separating_normal_world": (A[plane] / np.linalg.norm(A[plane])).tolist(),
            "separation_m": float(gap[plane]),
            "intersection_volume_m3": 0.0,
        }
    eye = np.eye(3)
    joined = np.vstack((A, eye, -eye))
    bounds = np.r_[B, center + half, half - center]
    triples = np.array(list(itertools.combinations(range(len(bounds)), 3)))
    mat = joined[triples]
    regular = abs(np.linalg.det(mat)) > 1e-11
    points = np.linalg.solve(mat[regular], bounds[triples[regular], None])[..., 0]
    vertices = points[np.all(points @ joined.T <= bounds + 5e-11, axis=1)]
    rank = np.linalg.matrix_rank(vertices[1:] - vertices[:1], tol=TOL) if len(vertices) else 0
    spare = 0.0
    if rank == 3:
        center_inside = vertices.mean(axis=0)
        spare = float(((bounds - joined @ center_inside) / np.linalg.norm(joined, axis=1)).min())
    volume = 4 * np.pi * spare**3 / 3 if spare > TOL else 0.0
    return {
        "relation": "finite_volume_intersection" if volume > 0 else "unresolved_or_boundary",
        "plane_index": plane,
        "separation_m": float(max(gap[plane], 0)),
        "interior_ball_volume_lower_bound_m3": float(volume),
        "vertices": vertices.tolist(),
    }


def run(reader):
    for path, expected in PLAN["source_sha256"].items():
        require(sha(ROOT / path) == expected, f"changed frozen input: {path}")
    center, half, layout = pin_layout()
    require(
        layout["original_tree_exact_after_removing_pin_and_material"],
        "old pin contains more than registered geom and material",
    )
    camera = read(ROOT / PLAN["slot_optical_registration"])["geometry"]["camera"]
    raw = read(ROOT / PLAN["blind_reference"])
    ray_faces = {}
    for pixel in PLAN["pixels"]:
        _, frame_pixel = next(
            (key, value) for key, value in enumerate(raw["2384"]["pixels"]) if value["uv"] == pixel
        )
        at = frame_pixel["depth_m"][1][1]
        table = frame_pixel["empty_depth_m"][1][1]
        last_clear = next(row for row in raw["2376"]["pixels"] if row["uv"] == pixel)
        require(
            frame_pixel["near_mask"][1][1] and table > at + BAND, "specified near return missing"
        )
        segments = [(0.01, at - BAND), (at - BAND, at + BAND), (at + BAND, table + BAND)]
        results = [
            intersect(*world_planes(camera, *pixel, a, b), center, half) for a, b in segments
        ]
        clear_band = intersect(
            *world_planes(camera, *pixel, 0.01, last_clear["empty_depth_m"][1][1] + BAND),
            center,
            half,
        )
        ray_faces[str(pixel)] = {
            "refusal_axial_m": at,
            "empty_reference_m": table,
            "last_clear_axial_m": last_clear["depth_m"][1][1],
            "last_clear_same_pixel_full_frustum": clear_band,
            "segments": [
                {"axis_depth_m": [a, b], **res}
                for (a, b), res in zip(segments, results, strict=True)
            ],
        }
    A, b = world_planes(camera, *PLAN["pixels"][0], 0.01, 2.0)
    tf = np.asarray(camera["camera_to_world"]).reshape(4, 4)
    u, v = PLAN["pixels"][0]
    fx, fy, cx, cy = camera["intrinsics"]
    test_center = tf[:3, 3] + tf[:3, :3] @ [(u - cx) / fx, (v - cy) / fy, 1.0]
    require(
        intersect(A, b, test_center, np.full(3, 0.0001))["relation"]
        == "finite_volume_intersection",
        "frustum positive control failed",
    )
    require(
        intersect(A, b, test_center + tf[:3, 0], np.full(3, 0.0001))["relation"]
        == "strictly_disjoint",
        "frustum negative control failed",
    )
    ruled_out = all(
        r["relation"] == "strictly_disjoint" for p in ray_faces.values() for r in p["segments"]
    )
    require(
        ruled_out, "first gate cannot resolve candidate; conditional native stop comparison remains"
    )
    OUT.mkdir(parents=True, exist_ok=True)
    write(
        OUT / f"{reader}.json",
        {
            "status": "FIXED_PRIOR_PIN_OUTSIDE_BOTH_2384_FULL_PIXEL_FRUSTA",
            "layout": layout,
            "frusta": ray_faces,
            "plan_sha256": sha(HERE / "plan.json"),
            "reader_sha256": sha(Path(__file__)),
            "opened_native_stop_branches": 0,
            "new_integrations": 0,
            "new_reference_renders": 0,
            "new_exposures": 0,
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reader", choices=("reader-1", "reader-2"))
    run(parser.parse_args().reader)
