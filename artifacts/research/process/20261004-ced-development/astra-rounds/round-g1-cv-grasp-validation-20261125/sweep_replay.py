"""Screen one isolated RGB-D packet and a registered local assembly, without future-state inputs."""

import argparse
import base64
import json
import math
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from scripts.graduation.g1_visibility_vision import measure_frame
from scripts.graduation.perception_io import sha
from sweep_depth import DepthView
from sweep_evaluate import Scene, evaluate, fingerprint, load_support, orientation_wxyz, qualify
from sweep_geometry import parse_tool, world_assembly, yaw_basis
from sweep_start import nominal_to_high, quaternion_matrix, robot_state

from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.tracking import _rgb

ROUND = Path(__file__).resolve().parent
sys.path.insert(0, str(ROUND.parent / "round-g1-general-cv-grasp-20261125"))
from surface_pilot import color_surface  # noqa: E402

OFFSETS = list(
    dict.fromkeys([0, *[s * k for k in range(7, 50, 7) for s in (-1, 1)], *range(-49, 50)])
)
PHASES = ["high_shift", "descend", "close"]
LIMITS = dict(
    marker_agreement_mm=10.0,
    depth_classification_band_mm=4.0,
    max_per_feedback_target_change_mm=10.0,
    max_total_feedback_target_correction_mm=50.0,
    arrival_translation_mm=5.0,
    arrival_rotation_deg=5.0,
    original_sample_and_ik_ms=100.0,
    nominal_high_min_mm=160.0,
)
SOURCES = (
    "sweep_geometry.py",
    "sweep_depth.py",
    "sweep_evaluate.py",
    "sweep_start.py",
    "sweep_replay.py",
)


def uncertainty(tool):
    pads = {}
    for b, sign, rng in [(tool["palm"], 0, [0.0, 0.0]), *tool["fingers"]]:
        c = b.c.copy()
        c[1] += sign * rng[1]
        radius = float(np.linalg.norm(np.abs(c) + b.h))
        rotation = 2 * radius * np.sin(np.radians(5) / 2)
        pads[b.name] = dict(
            radius_from_tcp_mm=radius * 1000,
            arrival_orientation_displacement_mm=rotation * 1000,
            arrival_combined_mm=5.0 + rotation * 1000,
            registered_correction_plus_arrival_and_optical_band_mm=50.0
            + 5.0
            + rotation * 1000
            + 4.0,
        )
    return dict(
        per_part=pads,
        limits=LIMITS,
        maximum_vertex_motion_mm=1.0,
        absolute_object_pose_bound_mm=None,
        full_path_tracking_error_mm=None,
        mechanical_stop_travel_mm=None,
        note=(
            "10 mm is a same-frame cross-check. The 5 mm and 5 degree limits apply at arrival. "
            "Depth-band and command-correction limits do not bound the full motion."
        ),
    )


def directions(yaw):
    defs = []
    for name, a in (
        ("object_X", yaw),
        ("object_Y", yaw + np.pi / 2),
        ("existing_tool_closure_axis", np.pi / 2),
    ):
        found = next((d for d in defs if abs(np.sin(a - d["world_angle"])) < 1e-9), None)
        if found is not None:
            found["aliases"].append(name)
            if name == "existing_tool_closure_axis":
                found["world_angle"] = a
        else:
            defs.append(dict(direction=name, aliases=[name], world_angle=a))
    return defs


def counts(rows, key):
    return dict(Counter(r[key] for r in rows))


def screen_frame(frame, geometry, assembly_xml, *, robot_measurement=None):
    assembly_xml = Path(assembly_xml)
    digest = sha(assembly_xml)
    if digest != geometry["pose_marker"]["marked_asset_sha256"]:
        raise ValueError("registered gripper/assembly SHA mismatch")
    base = dict(
        frame_id=frame.frame_id,
        checksum=frame.checksum_sha256,
        checksum_sha256=frame.checksum_sha256,
        calibration=frame.calibration_version,
        xml_sha256=digest,
        source_sha256={name: sha(ROUND / name) for name in SOURCES},
        selected=None,
        candidates=[],
        counts={},
        status="UNKNOWN",
    )
    if frame.model_dump(mode="json", include=set(geometry["camera"])) != geometry["camera"]:
        return base | dict(reason="camera_registration_mismatch")
    tool = parse_tool(assembly_xml)
    shape = (frame.height, frame.width)
    depth = np.frombuffer(base64.b64decode(frame.depth_float32_base64), dtype="<f4").reshape(shape)
    valid = np.frombuffer(frame.valid_mask_bytes(), dtype=np.uint8).reshape(shape).astype(bool)
    valid &= np.isfinite(depth) & (depth > 0)
    band = min(0.004, geometry.get("depth_error_bound_m") or 0.004)
    color = color_surface(frame, _rgb(frame), depth, valid, 2 * tool["target"].h[:2], band)
    m = measure_frame(frame, geometry)
    assert m["frame_id"] == frame.frame_id and m["checksum"] == frame.checksum_sha256
    distance = (
        float(1000 * np.linalg.norm(np.subtract(m["object_top_world_m"], color["top_center_m"])))
        if m["usable"] and color["status"] == "SUPPORTED"
        else None
    )
    base.update(
        color=color,
        marker={
            k: m[k]
            for k in (
                "usable",
                "reason",
                "selected_id",
                "observed_ids",
                "usable_ids",
                "object_center_world_m",
                "rotation_object_to_world",
                "grasp_world_m",
                "target_disagreement_m",
            )
        },
        current_top_delta_mm=distance,
        uncertainty=uncertainty(tool),
    )
    if not m["usable"]:
        if color["status"] == "SUPPORTED":
            base["color_only_geometry"] = dict(
                observed_top_m=color["top_center_m"],
                measured_sides_m=[
                    s["rectangle_sides_m"] for s in color["candidates"] if s["accepted"]
                ],
                nominal_face_widths_mm=(2000 * tool["target"].h[:2]).tolist(),
                aperture_mm=tool["opening"] * 1000,
                identity="unverified",
                bracket_binding="unknown",
            )
        return base | dict(reason=m["reason"])
    if distance is not None and distance > 10:
        return base | dict(reason="current_color_marker_top_disagreement")
    center = np.asarray(m["object_center_world_m"])
    rot = np.array(m["rotation_object_to_world"]).reshape(3, 3)
    tcp = np.asarray(m["grasp_world_m"])
    yaw = float(np.arctan2(rot[1, 0], rot[0, 0]))
    objrot = yaw_basis(yaw)
    high = tcp.copy()
    high[2] = max(0.16, tcp[2] + 0.1)
    boxes = world_assembly(tool, center, yaw)
    view = DepthView(depth, valid, frame.intrinsics, frame.camera_to_world, band)
    scene = Scene(boxes, geometry["support_height_m"], view)
    # The local vertical-box model uses the registered upright family. Bound each body's
    # displacement to the full measured optical attitude, including lever-arm effects.
    local_parts = [tool["target"], *tool["attachments"]]
    attitude_projection = {
        b.name: float(1000 * np.max(np.linalg.norm(b.corners() @ (rot - objrot).T, axis=1)))
        for b in local_parts
    }
    base["measured_attitude_to_upright_max_vertex_mm"] = attitude_projection
    robot = robot_state(robot_measurement, frame, assembly_xml, tool)
    base.update(
        measured_robot=robot,
        source_bounds=LIMITS,
        object_yaw_deg=math.degrees(yaw),
        measured_upright_tilt_deg=float(np.degrees(np.arccos(np.clip(rot[2, 2], -1, 1)))),
        registered_solids=[b.name for b in boxes],
        object_pose_side="measured yaw and center of the registered upright family",
        high_tcp_m=high.tolist(),
        approach_tcp_m=tcp.tolist(),
        initial_routes={},
    )
    rows = []
    eligible = []
    ray_memo = {}
    for direction in directions(yaw):
        name = direction["direction"]
        angle = direction["world_angle"]
        relative = angle - yaw
        axis = np.array([np.cos(angle), np.sin(angle), 0.0])
        tangent = np.array([axis[1], -axis[0], 0.0])
        quaternion = orientation_wxyz(axis)
        can_orient = "existing_tool_closure_axis" in direction["aliases"]
        base["initial_routes"][name] = nominal_to_high(
            robot, tool, high, quaternion_matrix(quaternion), scene
        )
        limit = 1000 * (
            np.abs((objrot.T @ tangent)[:2]) @ tool["target"].h[:2]
            + min(b.h[2] for b, _, _ in tool["fingers"])
            - 0.014
        )
        dt = 1000 * float(tangent @ (tcp - center))
        offsets = list(
            dict.fromkeys([*map(float, OFFSETS), round(-limit - dt, 8), round(limit - dt, 8)])
        )
        for mm in offsets:
            e = evaluate(tool, center, tcp, yaw, relative, mm / 1000, scene)
            e.update(
                candidate_id=f"{name}:{mm:+.6f}",
                direction=name,
                aliases=direction["aliases"],
                tangent_mm=mm,
                offset_object_m=(objrot.T @ tangent * mm / 1000).tolist(),
                world_offset_m=(tangent * mm / 1000).tolist(),
                orientation_wxyz=quaternion,
                original_orientation=can_orient,
                frame_id=frame.frame_id,
                checksum=frame.checksum_sha256,
            )
            lower_after = e["registered_min_sep_bound_mm"] - max(
                p["registered_correction_plus_arrival_and_optical_band_mm"]
                for p in base["uncertainty"]["per_part"].values()
            )
            e["known_components_inflated_sep_bound_mm"] = lower_after - max(
                attitude_projection.values()
            )
            bounds = dict(
                tracking_mm=None, stopping_mm=None, object_pose_mm=None, depth_mm=band * 1000
            )
            e["full_physical_clearance"], e["full_reasons"] = qualify(
                e, bounds, base["initial_routes"][name]["status"]
            )
            e["bound_missing"] = [
                "absolute_object_pose",
                "full_trajectory_tracking",
                "stopping_distance",
            ]
            if e["geometric_status"] == "CLEAR":
                # Evaluate the registered static model separately from measured bilateral contact.
                k = (round(relative % (2 * np.pi), 12), round(mm, 8))
                if k not in ray_memo:
                    ray_memo[k] = load_support(
                        tool, center, tcp, yaw, relative, mm / 1000, e["patch"]
                    )
                e["load_support"] = ray_memo[k]
            else:
                e["load_support"] = {"status": "no_geometrically_viable_grasp"}
            if can_orient and e["full_physical_clearance"] == "CLEAR":
                eligible.append(e)
            rows.append(e)
    if eligible:
        selected = min(
            eligible,
            key=lambda e: (
                -e["known_components_inflated_sep_bound_mm"],
                -min(e["patch"]["contact_area_each_mm2"]),
                abs(e["tangent_mm"]),
            ),
        )
        base["selected"] = selected | {"proof_sha256": fingerprint(selected)}
    from sweep_geometry import contact_patch

    diagonal = contact_patch(tool, tcp, center, tool["target"].h, yaw, np.pi / 4, 0.0)
    return base | dict(
        candidates=rows,
        counts=counts(rows, "full_physical_clearance"),
        nominal_counts=counts(rows, "geometric_status"),
        observed_sweep_counts=counts(rows, "clearance"),
        matched=bool(base["selected"]),
        diagonal_control=diagonal,
        status="CLEAR" if base["selected"] else "UNKNOWN",
        reason="qualified" if base["selected"] else "no_evidenced_executable_clearance",
    )


def dump(path, obj):
    with Path(path).open("x") as handle:
        json.dump(
            obj, handle, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
        )
        handle.write("\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["frame"])
    for name in ("frame", "geometry", "xml", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--robot-measurement", type=Path)
    a = parser.parse_args()
    frame = RGBDObservation.model_validate_json(a.frame.read_bytes())
    geom = json.loads(a.geometry.read_bytes())
    output = screen_frame(
        frame,
        geom,
        a.xml,
        robot_measurement=json.loads(a.robot_measurement.read_bytes())
        if a.robot_measurement
        else None,
    )
    dump(a.output, output)
