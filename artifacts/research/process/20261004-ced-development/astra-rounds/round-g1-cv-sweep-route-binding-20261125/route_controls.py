"""Recheck individual direct routes, a direct-only obstacle, and the unchanged frozen controls."""

import base64
import gzip
import json
from pathlib import Path

import numpy as np
from route_batch import PARENT, ROUND, encode, sha
from route_forces import stability
from route_geometry import direct_envelope
from route_screen import VolumeView
from sweep_evaluate import Scene
from sweep_geometry import Box, contact_patch, parse_tool, world_assembly
from sweep_start import quaternion_matrix

from cloud_edge_robot_arm.vision.observations import RGBDObservation


def box(name, c, h):
    return Box(name, np.array(c), np.array(h), np.eye(3))


def tests(raw):
    allrows = json.loads(
        gzip.decompress(
            base64.b64decode(
                json.load((ROUND / "route-candidates.public.json").open())["data_base64"]
            )
        )
    )
    assets = Path("assets/robots/franka_panda")
    tool = parse_tool(assets / "scene_g1_development_dual_id7_y130_id8_x130_low_bracket_v3.xml")
    found = []
    for framekey, fr, choice in zip(
        ("A", "B"), allrows[-2:], ("object_Y", "object_X"), strict=True
    ):
        img = RGBDObservation.model_validate_json((raw / framekey / "frame.json").read_bytes())
        assert (img.frame_id, img.checksum_sha256) == (fr["frame_id"], fr["checksum"])
        shape = (img.height, img.width)
        depth = np.frombuffer(base64.b64decode(img.depth_float32_base64), "<f4").reshape(shape)
        valid = np.frombuffer(img.valid_mask_bytes(), np.uint8).reshape(shape).astype(bool)
        view = VolumeView(depth, valid, img.intrinsics, img.camera_to_world, 0.004)
        scene = Scene(
            world_assembly(
                tool,
                np.array(fr["marker"]["object_center_world_m"]),
                np.radians(fr["object_yaw_deg"]),
            ),
            0.0,
            view,
        )
        for axis, mm in (
            (choice, 0.0),
            (choice, -7.0),
            (choice, 7.0),
            (choice, 41.0 if framekey == "A" else 44.0),
            ("existing_tool_closure_axis", 0.0),
        ):
            r = next(
                e for e in fr["candidates"] if e["direction"] == axis and e["tangent_mm"] == mm
            )
            group = fr["initial_routes"][axis]
            exact = direct_envelope(
                fr["measured_robot"],
                tool,
                [np.array(r["target_high_m"])],
                quaternion_matrix(r["orientation_wxyz"]),
                scene,
            )
            assert exact["minimum_union_gap_mm"] + 1.0 >= group["minimum_union_gap_mm"]
            found.append(
                dict(
                    frame=framekey,
                    candidate=r["candidate_id"],
                    family_status=group["status"],
                    single_status=exact["status"],
                    single_min_bound_mm=exact["minimum_union_gap_mm"],
                    family_min_bound_mm=group["minimum_union_gap_mm"],
                    single_segments=exact["segments"],
                    family_segments=group["segments"],
                    single_midpoint_hits=exact["actual_midpoint_hits"],
                    first_separate_unknown=exact["first_unconfirmed_ray_box"],
                )
            )
    original = parse_tool(assets / "scene_pose_marker_side_y_plus_75mm_r593.xml")
    state = dict(
        status="MEASURED",
        tcp_m=[0.0, -0.17, 0.25],
        rotation=np.eye(3).tolist(),
        finger_interval_m=[[0.04, 0.04], [0.04, 0.04]],
    )
    highs = np.array([[0.0, 0.04, 0.25], [0.049, 0.04, 0.25]])
    target = box("object_geom", [0.6, 0.6, 0], [0.02] * 3)
    obstacle = box("direct_only", [0.046, -0.038, 0.276], [0.001] * 3)
    clear = Scene([target], 0, known_static_volume=True)
    blocked = Scene([target, obstacle], 0, known_static_volume=True)
    controls = {}
    for label, start, h, sc in (
        ("positive_zero_and_nonzero_group", state, highs, clear),
        ("central_old_first_stage", state, highs[:1], blocked),
        ("central_old_second_stage", state | dict(tcp_m=highs[0].tolist()), highs[1:], blocked),
        ("direct_witness", state, highs[1:], blocked),
        ("group_with_blocked_and_clear_members", state, highs, blocked),
    ):
        ans = direct_envelope(start, original, h, np.eye(3), sc)
        controls[label] = {
            k: ans[k]
            for k in [
                "status",
                "segments",
                "max_vertex_motion_mm",
                "within_segment_pad_mm",
                "minimum_union_gap_mm",
                "actual_midpoint_hits",
                "pieces",
            ]
        }
    center = np.array([0, 0, 0.035])
    tcp = np.array([0, 0, 0.045])
    pa = contact_patch(original, tcp, center, original["target"].h, 0.0, 0.0, 0.0)
    force = stability(original, center, tcp, 0.0, 0.0, pa)
    heavy = stability(original | dict(mass=100.0), center, tcp, 0.0, 0.0, pa)
    return dict(
        individual_direct_paths=found,
        controlled_routes=controls,
        centered_80g=force,
        overweight_100kg=heavy,
        source_sha256=sha(Path(__file__)),
        candidate_sha256=sha(ROUND / "route-candidates.public.json"),
        original_frozen_depth_and_full_gripper_controls_sha256=sha(
            PARENT / "sweep-controls.public.json"
        ),
        red=[
            "Both central stages are clear, while the direct path hits the obstacle.",
            "Original direction gate rejects recomputed fixed quaternion.",
            "First-generation simplex reports no verified witness on centered 80 g cube.",
            "New tests before implementation: ModuleNotFoundError route_geometry.",
        ],
        current_pytest_cases=10,
    )


if __name__ == "__main__":
    out = tests(Path("experiments/results/g1-cv-grasp-validation-20261125/capture-v2/blind"))
    with (ROUND / "route-controls.public.json").open("xb") as f:
        f.write(encode(out))
