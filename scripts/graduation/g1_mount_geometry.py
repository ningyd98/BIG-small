"""Check the three archived mounts against their compiled cube, grid and registered grasp."""

from __future__ import annotations

import hashlib
import re
from math import cos, sin
from xml.etree import ElementTree as ET

import cv2
import mujoco
import numpy as np
from scripts.graduation.perception_io import ROOT, sha

from cloud_edge_robot_arm.research.native_collection_grounding import geometry_registration
from cloud_edge_robot_arm.vision.marker_families import (
    COMPONENT_DIAGNOSTIC_FAMILY,
    SIDE_PREPARE_ONLY_FAMILY,
    marker_family,
)
from cloud_edge_robot_arm.vision.native_calibration import NativeGeometryRegistration

PREFIX = "pose_marker_outboard_v3_"
NONMARKER_XML = "6d1c1df9d78eb8106454b9d97e95d4742c79de63295d4f617e97e024a9758d3e"
POSES = ((0.45, 0.0, 0.035, 0.0), (0.445, 0.008, 0.035, 0.07))
COMPILED = (
    "body_parentid",
    "body_pos",
    "body_quat",
    "body_mass",
    "body_subtreemass",
    "body_inertia",
    "body_ipos",
    "body_iquat",
    "jnt_type",
    "jnt_pos",
    "jnt_axis",
    "jnt_range",
    "jnt_bodyid",
    "jnt_qposadr",
    "jnt_dofadr",
    "jnt_limited",
    "dof_damping",
    "dof_armature",
    "cam_pos",
    "cam_quat",
    "cam_fovy",
    "cam_bodyid",
    "site_pos",
    "site_quat",
    "site_bodyid",
    "actuator_trnid",
    "actuator_trntype",
    "actuator_gaintype",
    "actuator_biastype",
    "actuator_ctrlrange",
    "actuator_gainprm",
    "actuator_biasprm",
    "geom_type",
    "geom_bodyid",
    "geom_quat",
    "geom_size",
    "geom_contype",
    "geom_conaffinity",
    "geom_friction",
    "geom_solref",
    "geom_solimp",
    "geom_rgba",
)


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def registered_family(mount):
    family = marker_family(mount["family"])
    require(
        family.asset_path == mount["asset_path"]
        and family.asset_sha256 == mount["asset_sha256"] == sha(ROOT / family.asset_path)
        and np.array_equal(
            np.asarray(family.marker_to_object).reshape(4, 4)[:3, 3],
            mount["object_T_marker_translation_m"],
        ),
        "mount family, asset SHA or rigid attachment differs",
    )
    return family


def descriptor(mount):
    """Return the native descriptor, or an explicitly offline component descriptor and refusal."""
    family = registered_family(mount)
    try:
        geometry = geometry_registration(marker_family_id=family.family_id)
        NativeGeometryRegistration(geometry).validate_asset(ROOT)
    except ValueError as exc:
        if family.family_id != COMPONENT_DIAGNOSTIC_FAMILY:
            raise
        native_error = str(exc)
        # The original registration also checks the common cube/tool/camera and target.
        common = geometry_registration(marker_family_id=SIDE_PREPARE_ONLY_FAMILY)
        geometry = {
            **common,
            "marker_family": family.family_id,
            "registration_id": family.registration_id,
            "asset_path": family.asset_path,
            "pose_marker": {
                "marker_id": family.marker_id,
                "marker_size_m": family.marker_size_m,
                "dictionary": family.dictionary,
                "marked_asset_sha256": family.asset_sha256,
            },
            "marker_to_object": list(family.marker_to_object),
        }
        return geometry, native_error
    return geometry, None


def verify_target(geometry, marker_center, marker_rotation, servo_target):
    """Independently compose world_T_marker · inverse(object_T_marker) · object_T_tcp."""
    world_marker = np.eye(4)
    world_marker[:3, :3] = np.asarray(marker_rotation).reshape(3, 3)
    world_marker[:3, 3] = marker_center
    world_object = world_marker @ np.linalg.inv(
        np.asarray(geometry["marker_to_object"]).reshape(4, 4)
    )
    tcp = (world_object @ np.asarray(geometry["object_to_tcp"]).reshape(4, 4))[:3, 3]
    require(np.allclose(tcp, servo_target, rtol=0, atol=1e-10), "registered TCP differs")
    return {
        "object_center_world_m": world_object[:3, 3].tolist(),
        "object_top_world_m": (world_object @ [0, 0, geometry["object_half_extent_m"][2], 1])[
            :3
        ].tolist(),
        "tcp_world_m": tcp.tolist(),
        "upright_zz": float(world_object[2, 2]),
    }


def bits():
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    return cv2.aruco.generateImageMarker(dictionary, 7, 6) > 0


def compiled_checks(model, marker_ids):
    checks = {}
    nonmarker = [i for i in range(model.ngeom) if i not in marker_ids]
    for key in (*COMPILED, "nonmarker_geom_pos", "model_options"):
        if key == "nonmarker_geom_pos":
            value = model.geom_pos[nonmarker]
        elif key == "model_options":
            value = np.r_[model.opt.timestep, model.opt.gravity, int(model.opt.integrator)]
        else:
            value = getattr(model, key)
        checks[key] = hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest()
    return checks, hashlib.sha256("".join(checks.values()).encode()).hexdigest()


def check_fk(model, attachment):
    data = mujoco.MjData(model)
    q = model.joint("object_free").qposadr[0]
    observations = []
    for x, y, z, yaw in POSES:
        data.qpos[q : q + 7] = [x, y, z, cos(yaw / 2), 0, 0, sin(yaw / 2)]
        mujoco.mj_forward(model, data)
        origin = data.geom("object_geom").xpos.copy()
        rotation = data.geom("object_geom").xmat.reshape(3, 3)
        max_error = 0.0
        points = []
        for row, col in ((0, 0), (0, 5), (5, 5), (5, 0)):
            sx, sy = (1 if col else -1), (-1 if row else 1)
            name = PREFIX + f"r{row}c{col}"
            geom = data.geom(name)
            local_corner = np.array([sx, sy, 1]) * model.geom(name).size
            actual = geom.xpos + geom.xmat.reshape(3, 3) @ local_corner
            expected = origin + rotation @ (attachment + [sx * 0.0375, sy * 0.0375, 0])
            max_error = max(max_error, float(np.linalg.norm(expected - actual)))
            points.append(actual.tolist())
        require(max_error < 1e-10, "rigid marker corner FK differs")
        observations.append(
            {
                "xyz_yaw": [x, y, z, yaw],
                "ordered_printed_corners_world_m": points,
                "max_corner_residual_m": max_error,
                "object_bottom_m": float(origin[2] - model.geom("object_geom").size[2]),
            }
        )
    return observations


def audit_mount(mount):
    family = registered_family(mount)
    path = ROOT / family.asset_path
    tree = ET.fromstring(path.read_bytes())
    model = mujoco.MjModel.from_xml_path(str(path))
    body = tree.find("./worldbody/body[@name='object']")
    body_id = model.body("object").id
    require(
        body is not None and model.joint("object_free").bodyid[0] == body_id, "cube parent changed"
    )
    cells = {PREFIX + f"r{r}c{c}" for r in range(6) for c in range(6)}
    marker_names = cells | {PREFIX + "quiet"}
    nodes = [n for n in tree.iter() if n.get("name", "").startswith(PREFIX)]
    require(
        len(nodes) == 37 and {n.get("name") for n in nodes} == marker_names, "grid/quiet incomplete"
    )
    code = bits()
    center = np.asarray(mount["object_T_marker_translation_m"])
    for node in nodes:
        name = node.get("name")
        geom = model.geom(name)
        require(
            node in list(body)
            and node.tag == "geom"
            and geom.bodyid[0] == body_id
            and float(node.get("mass")) == float(node.get("density")) == 0
            and geom.contype[0] == geom.conaffinity[0] == 0
            and np.array_equal(geom.quat, [1, 0, 0, 0])
            and geom.type[0] == int(mujoco.mjtGeom.mjGEOM_BOX),
            "wrong rigid zero-mass grid geom",
        )
        if name.endswith("quiet"):
            offset, size, white = [0, 0, -0.00003], [0.05, 0.05, 0.00001], True
        else:
            cell = re.fullmatch(PREFIX + r"r([0-5])c([0-5])", name)
            row, col = map(int, cell.groups())
            offset = [(col - 2.5) * 0.0125, (2.5 - row) * 0.0125, -0.00001]
            size, white = [0.00625, 0.00625, 0.00001], bool(code[row, col])
        require(
            np.allclose(geom.pos, center + offset, rtol=0, atol=1e-12)
            and np.allclose(geom.size, size, rtol=0, atol=1e-12)
            and np.allclose(geom.rgba, [0.98 if white else 0.01] * 3 + [1], atol=1e-7, rtol=0),
            "grid color, size or ordered cell attachment differs",
        )
        body.remove(node)
    common = hashlib.sha256(ET.tostring(tree)).hexdigest()
    require(common == NONMARKER_XML, "nonmarker camera/physics XML differs")
    compiled, digest = compiled_checks(model, {model.geom(n).id for n in marker_names})
    require(
        np.array_equal(model.geom("object_geom").size, [0.035] * 3)
        and np.array_equal(model.site("tcp").pos, [0.105, 0, 0])
        and model.cam("rgbd").fovy[0] == 50,
        "object/tool/camera differs",
    )
    return {
        "id": mount["id"],
        "asset_sha256": family.asset_sha256,
        "nonmarker_xml_sha256": common,
        "compiled_physics_sha256": digest,
        "compiled_field_sha256": compiled,
        "cells": len(cells),
        "ordered_grid_bits": ["".join("1" if b else "0" for b in row) for row in code],
        "mass_kg": float(model.body_mass[body_id]),
        "inertia_kg_m2": model.body_inertia[body_id].tolist(),
        "object_collision_masks": [
            int(model.geom("object_geom").contype[0]),
            int(model.geom("object_geom").conaffinity[0]),
        ],
        "board_gap_m": float(max(abs(center[:2])) - 0.05 - 0.035),
        "table_top_m": float(model.geom("table").pos[2] + model.geom("table").size[2]),
        "region_top_m": float(
            model.body("target_region").pos[2] + model.geom("target_region_geom").size[2]
        ),
        "local_front_normal": [0, 0, 1],
        "board_width_m": 0.1,
        "printed_width_m": 0.075,
        "attachment_m": center.tolist(),
        "fk": check_fk(model, center),
    }
