"""Independently recompute current-frame candidate paths with the bound native high target."""

import argparse
import base64
import json
import math
from pathlib import Path

import numpy as np
from route_forces import stability
from route_geometry import direct_envelope, mot_targets, wrist
from scripts.graduation.g1_visibility_vision import measure_frame
from scripts.graduation.perception_io import sha
from sweep_depth import DepthView
from sweep_evaluate import Scene, evaluate, qualify
from sweep_geometry import contact_patch, hand_sweeps, parse_tool, world_assembly, yaw_basis
from sweep_replay import OFFSETS, color_surface, counts, directions, dump, uncertainty
from sweep_start import quaternion_matrix, robot_state

from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.tracking import _rgb


class VolumeView(DepthView):
    def assess(self, box):
        v = super().assess(box)
        vol = 8 * np.prod(box.h) * 1e9
        # This rigorous lower bound applies to this box only. The per-pixel
        # uncertain-volume upper sum covers all non-free space when no return
        # intersects. A box with an occupied return retains its FREE ray counts.
        lower = (
            0.0 if v["counts"].get("occupied", 0) else max(0.0, vol - v["unknown_volume_upper_mm3"])
        )
        return v | dict(free_volume_lower_mm3=lower)


def screen_frame(frame, geometry, assembly_xml, *, robot_measurement=None):
    xml = Path(assembly_xml)
    tool = parse_tool(xml)
    if sha(xml) != geometry["pose_marker"]["marked_asset_sha256"]:
        raise ValueError("wrong registered XML")
    base = dict(
        frame_id=frame.frame_id,
        checksum=frame.checksum_sha256,
        checksum_sha256=frame.checksum_sha256,
        xml_sha256=sha(xml),
        source_sha256={
            f: sha(Path(__file__).parent / f)
            for f in ("route_forces.py", "route_geometry.py", "route_screen.py")
        },
        selected=None,
        candidates=[],
        counts={},
        initial_routes={},
        status="UNKNOWN",
    )
    if frame.model_dump(mode="json", include=set(geometry["camera"])) != geometry["camera"]:
        return base | dict(reason="camera_registration_mismatch")
    size = (frame.height, frame.width)
    depth = np.frombuffer(base64.b64decode(frame.depth_float32_base64), "<f4").reshape(size)
    valid = (
        np.frombuffer(frame.valid_mask_bytes(), np.uint8).reshape(size).astype(bool)
        & np.isfinite(depth)
        & (depth > 0)
    )
    band = min(0.004, geometry.get("depth_error_bound_m") or 0.004)
    color = color_surface(frame, _rgb(frame), depth, valid, 2 * tool["target"].h[:2], band)
    mark = measure_frame(frame, geometry)
    assert (mark["frame_id"], mark["checksum"]) == (frame.frame_id, frame.checksum_sha256)
    base.update(
        color=color,
        marker={
            k: mark[k]
            for k in (
                "usable",
                "reason",
                "usable_ids",
                "selected_id",
                "grasp_world_m",
                "object_center_world_m",
                "object_top_world_m",
                "rotation_object_to_world",
            )
        },
        uncertainty=uncertainty(tool),
    )
    if not mark["usable"]:
        return base | dict(reason=mark["reason"])
    separation = (
        float(1000 * np.linalg.norm(np.subtract(color["top_center_m"], mark["object_top_world_m"])))
        if color["status"] == "SUPPORTED"
        else None
    )
    base["current_top_delta_mm"] = separation
    if separation is not None and separation > 10:
        return base | dict(reason="current_color_marker_top_disagreement")
    center = np.array(mark["object_center_world_m"])
    tcp = np.array(mark["grasp_world_m"])
    rot = np.array(mark["rotation_object_to_world"]).reshape(3, 3)
    yaw = float(np.arctan2(rot[1, 0], rot[0, 0]))
    upright = yaw_basis(yaw)
    camera = VolumeView(depth, valid, frame.intrinsics, frame.camera_to_world, band)
    scene = Scene(world_assembly(tool, center, yaw), geometry["support_height_m"], camera)
    state = robot_state(robot_measurement, frame, xml, tool)
    base.update(
        measured_robot=state,
        object_yaw_deg=float(np.degrees(yaw)),
        registered_solids=[o.name for o in scene.boxes],
        measured_attitude_to_upright_max_vertex_mm={
            b.name: float(1000 * np.linalg.norm(b.corners() @ (rot - upright).T, axis=1).max())
            for b in [tool["target"], *tool["attachments"]]
        },
    )
    rows = []
    for d in directions(yaw):
        name = d["direction"]
        angle = d["world_angle"]
        rel = angle - yaw
        axis = np.array([np.cos(angle), np.sin(angle), 0.0])
        tan = np.array([axis[1], -axis[0], 0.0])
        native = "existing_tool_closure_axis" in d["aliases"]
        quat = wrist(axis, native)
        limit = 1000 * (
            abs((upright.T @ tan)[:2]) @ tool["target"].h[:2]
            + min(b.h[2] for b, _, _ in tool["fingers"])
            - 0.014
        )
        dt = 1000 * float(tan @ (tcp - center))
        offsets = list(
            dict.fromkeys([*map(float, OFFSETS), round(-limit - dt, 8), round(limit - dt, 8)])
        )
        options = []
        for mm in offsets:
            delta = upright.T @ tan * mm / 1000
            low, high = mot_targets(tcp, rot, delta)
            options.append((mm, delta, low, high))
        route = direct_envelope(
            state, tool, [q[3] for q in options], quaternion_matrix(quat), scene
        )
        base["initial_routes"][name] = route
        for mm, delta, low, high in options:
            # A zero lateral offset to this already-transformed TCP leaves one high
            # snapshot, a continuous vertical descent, and two independent jaw slides.
            e = evaluate(tool, center, low, yaw, rel, 0.0, scene)
            patch = e["patch"]
            parts = hand_sweeps(
                tool, low, axis, 0.0, patch["required_width_m"], patch["tcp_normal_offset_m"]
            )
            boxes = []
            totals = dict(free_volume_lower_mm3=0.0, unknown_volume_upper_mm3=0.0)
            for (phase, b), stats in zip(parts, e["phase_evidence"], strict=True):
                v = scene.depth(b)
                phase = "actual_high" if phase == "high_shift" else phase
                boxes.append(
                    dict(
                        phase=phase,
                        part=b.name,
                        min_registered_gap_mm=stats[2],
                        ray=v["state"],
                        ray_counts=v["counts"],
                        free_volume_lower_mm3=v["free_volume_lower_mm3"],
                        unknown_volume_upper_mm3=v["unknown_volume_upper_mm3"],
                        continuous_method="stationary"
                        if phase == "actual_high"
                        else "exact axis-aligned translation union",
                        tessellation_remainder_mm=0.0,
                    )
                )
                totals["free_volume_lower_mm3"] = max(
                    totals["free_volume_lower_mm3"], v["free_volume_lower_mm3"]
                )
                totals["unknown_volume_upper_mm3"] += v["unknown_volume_upper_mm3"]
            e["phase_evidence"] = boxes
            e["hits"] = [
                ("actual_high" if s == "high_shift" else s, *other) for s, *other in e["hits"]
            ]
            if e["limiting_pair"][0] == "high_shift":
                e["limiting_pair"] = ("actual_high", *e["limiting_pair"][1:])
            e["volume_bounds"] = totals
            gap = e["registered_min_sep_bound_mm"]
            if route.get("minimum_union_gap_mm") is not None:
                gap = min(gap, route["minimum_union_gap_mm"])
            e["full_physical_clearance"], e["full_reasons"] = qualify(
                e,
                dict(tracking_mm=None, stopping_mm=None, object_pose_mm=None, depth_mm=band * 1000),
                "NOMINALLY_CLEAR" if route["status"] == "CLEAR" else route["status"],
            )
            e["known_components_inflated_sep_bound_mm"] = (
                gap
                - max(
                    s["registered_correction_plus_arrival_and_optical_band_mm"]
                    for s in base["uncertainty"]["per_part"].values()
                )
                - max(base["measured_attitude_to_upright_max_vertex_mm"].values())
            )
            e["load_support"] = (
                stability(tool, center, low, yaw, rel, patch)
                if e["geometric_status"] == "CLEAR"
                else dict(status="NO_NOMINALLY_CLEAR_GRASP")
            )
            rad = math.radians(patch["face_alignment_error_deg"])
            e.update(
                candidate_id=f"{name}:{mm:+.6f}",
                direction=name,
                aliases=d["aliases"],
                tangent_mm=mm,
                offset_object_m=delta.tolist(),
                world_offset_m=(low - tcp).tolist(),
                target_high_m=high.tolist(),
                target_low_m=low.tolist(),
                orientation_wxyz=quat,
                original_orientation=native,
                projected_overlap_boundary=mm not in OFFSETS,
                frame_id=frame.frame_id,
                checksum=frame.checksum_sha256,
                high_route_key=name,
                high_group_registered_clearance_mm=route.get("minimum_union_gap_mm"),
                actual_closure_observed=False,
                nominal_requested_face="X" if abs(np.cos(rel)) >= abs(np.sin(rel)) else "Y",
                passive_alignment=dict(
                    observed=False,
                    required_angle_deg=patch["face_alignment_error_deg"],
                    maximum_cube_corner_motion_mm=2000
                    * np.linalg.norm(tool["target"].h[:2])
                    * np.sin(rad / 2),
                    required_width_change_mm=1000
                    * (patch["required_width_m"] - 2 * min(tool["target"].h[:2])),
                    nominal_projected_face_patches_mm=patch["face_patch_each_side_mm"],
                ),
            )
            rows.append(e)
    good = [
        e
        for e in rows
        if e["original_orientation"]
        and e["full_physical_clearance"] == "CLEAR"
        and e["load_support"]["status"] == "WITNESS"
    ]
    if good:
        base["selected"] = min(
            good,
            key=lambda e: (
                -e["known_components_inflated_sep_bound_mm"],
                -min(e["patch"]["contact_area_each_mm2"]),
                abs(e["tangent_mm"]),
            ),
        )
    return base | dict(
        status="CLEAR" if good else "UNKNOWN",
        reason="qualified" if good else "no_evidenced_executable_clearance",
        candidates=rows,
        counts=counts(rows, "full_physical_clearance"),
        observed_sweep_counts=counts(rows, "clearance"),
        nominal_counts=counts(rows, "geometric_status"),
        diagonal_control=contact_patch(tool, tcp, center, tool["target"].h, yaw, np.pi / 4, 0.0),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for n in ("frame", "geometry", "xml", "output"):
        parser.add_argument("--" + n, type=Path, required=True)
    parser.add_argument("--robot-measurement", type=Path)
    a = parser.parse_args()
    dump(
        a.output,
        screen_frame(
            RGBDObservation.model_validate_json(a.frame.read_bytes()),
            json.loads(a.geometry.read_bytes()),
            a.xml,
            robot_measurement=json.loads(a.robot_measurement.read_bytes())
            if a.robot_measurement
            else None,
        ),
    )
