"""Development-only two-board rigid registration built from the exact r593 scene."""

from __future__ import annotations

import hashlib
import json
import math
from functools import lru_cache
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np

FAMILY = "g1_development_dual_id7_y100_id8_x100_v1"
REGISTRATION_ID = "g1-development-only-dual-7y-8x-rigid-v1"
ASSET_PATH = "assets/robots/franka_panda/scene_g1_development_dual_id7_y100_id8_x100_v1.xml"
BASE_ASSET_PATH = "assets/robots/franka_panda/scene_pose_marker_side_y_plus_75mm_r593.xml"
BASE_SHA = "1e95054dc74e1c8ff51042290450b5e01e7410dd653870c553f056892efca140"
ASSET_SHA = "5c8e97f5dd17cf719d579d1badeab85de2e8f52dd14f6be0ef5dd2ff28159e66"
OLD_PREFIX = "pose_marker_outboard_v3_"
MARKER_PREFIXES = {7: "g1_dual_id7_", 8: "g1_dual_id8_"}
CENTERS = {7: (0.0, 0.1, 0.03505), 8: (0.1, 0.0, 0.03505)}
SCENE_ID = "S01_NORMAL_STATIC"
BODY_MASS_KG = 0.10036
AGREEMENT_M = 0.010
SOURCE_FILES = tuple(
    f"scripts/graduation/g1_dual_{n}.py" for n in ("asset", "observer", "runtime_adapter")
)
POSES = ((0.45, 0.0, 0.035, 0.0), (0.445, 0.008, 0.035, 0.07))


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def transform(x=0.0, y=0.0, z=0.0):
    return [1, 0, 0, x, 0, 1, 0, y, 0, 0, 1, z, 0, 0, 0, 1]


def bits(marker_id):
    import cv2

    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    return cv2.aruco.generateImageMarker(dictionary, marker_id, 6) > 0


def local_corners():
    return [
        [-0.0375, 0.0375, 0.0],
        [0.0375, 0.0375, 0.0],
        [0.0375, -0.0375, 0.0],
        [-0.0375, -0.0375, 0.0],
    ]


def box_names():
    return {"object_geom"} | {
        prefix + name
        for prefix in MARKER_PREFIXES.values()
        for name in [
            "plate",
            "support",
            "quiet",
            *(f"r{r}c{c}" for r in range(6) for c in range(6)),
        ]
    }


def build_xml(r593):
    if _sha(r593) != BASE_SHA:
        raise ValueError("exact original r593 asset required")
    tree = ET.fromstring(r593)
    body = tree.find("./worldbody/body[@name='object']")
    for node in list(body):
        if node.get("name", "").startswith(OLD_PREFIX):
            body.remove(node)

    def box(name, position, half, gray, mass):
        attrs = {
            "name": name,
            "type": "box",
            "pos": " ".join(f"{v:.10f}" for v in position),
            "size": " ".join(f"{v:.10f}" for v in half),
            "rgba": f"{gray} {gray} {gray} 1",
            "mass": str(mass),
            "contype": "1" if mass else "0",
            "conaffinity": "3" if mass else "0",
        }
        if not mass:
            attrs.update(density="0", group="2")
        ET.SubElement(body, "geom", attrs)

    # Each 2mm sheet meets the 15mm bridge along its face. The bridge meets the
    # 70mm cube. All four structural pieces use 500 kg/m³ effective density.
    for marker_id, (x, y, _) in CENTERS.items():
        prefix = MARKER_PREFIXES[marker_id]
        box(prefix + "plate", (x, y, 0.03401), (0.05, 0.05, 0.001), 0.6, 0.010)
        bridge = (0.006, 0.0075, 0.001) if marker_id == 7 else (0.0075, 0.006, 0.001)
        box(prefix + "support", (0.425 * x, 0.425 * y, 0.03401), bridge, 0.4, 0.00018)
        box(prefix + "quiet", (x, y, 0.03502), (0.05, 0.05, 0.00001), 0.98, 0)
        for r, row in enumerate(bits(marker_id)):
            for c, white in enumerate(row):
                box(
                    prefix + f"r{r}c{c}",
                    (x + (c - 2.5) * 0.0125, y + (2.5 - r) * 0.0125, 0.03504),
                    (0.00625, 0.00625, 0.00001),
                    0.98 if white else 0.01,
                    0,
                )
    ET.indent(tree, space="  ")
    return ET.tostring(tree, encoding="utf-8") + b"\n"


def pose_registration(marker_id):
    from cloud_edge_robot_arm.vision.pose_markers import PoseMarkerRegistration

    if marker_id not in CENTERS:
        raise ValueError("unregistered development marker ID")
    return PoseMarkerRegistration(marker_id, 0.075, ASSET_SHA)


def family():
    from cloud_edge_robot_arm.vision.marker_families import MarkerFamily

    return MarkerFamily(
        FAMILY,
        ASSET_PATH,
        ASSET_SHA,
        7,
        "DICT_4X4_50",
        0.075,
        REGISTRATION_ID,
        tuple(transform(*CENTERS[7])),
    )


@lru_cache(maxsize=1)
def _descriptor_json():
    root = Path(__file__).resolve().parents[2]
    focal = 120 / math.tan(math.radians(50) / 2)
    intrinsics = [focal, focal, 159.5, 119.5]
    extrinsics = [1, 0, 0, 0.35, 0, -1, 0, 0, 0, 0, -1, 1.4, 0, 0, 0, 1]
    camera = dict(
        width=320,
        height=240,
        intrinsics=intrinsics,
        camera_to_world=extrinsics,
        calibration_version=_sha(np.asarray(intrinsics + extrinsics, dtype="<f8").tobytes())[:16],
        source="mujoco_camera",
    )
    sources = {name: _sha((root / name).read_bytes()) for name in SOURCE_FILES}
    markers = {}
    for marker_id, center in CENTERS.items():
        pose = pose_registration(marker_id)
        markers[str(marker_id)] = dict(
            marker_id=marker_id,
            dictionary=pose.dictionary,
            marker_size_m=pose.marker_size_m,
            marker_registration_hash=pose.digest(),
            object_T_marker=transform(*center),
            ordered_corners_marker_m=local_corners(),
            dictionary_rows=["".join("1" if b else "0" for b in row) for row in bits(marker_id)],
        )
    return _json(
        dict(
            registration_id=REGISTRATION_ID,
            marker_family=FAMILY,
            object_id="object",
            object_class="cube",
            target_region_id="target_region",
            asset_path=ASSET_PATH,
            pose_marker=dict(
                marker_id=7,
                marker_size_m=0.075,
                marked_asset_sha256=ASSET_SHA,
                dictionary="DICT_4X4_50",
            ),
            marker_to_object=transform(*CENTERS[7]),
            object_half_extent_m=[0.035] * 3,
            contact_points_m=dict(top=[0, 0, 0.035], left=[0, 0.035, 0], right=[0, -0.035, 0]),
            object_to_tcp=transform(0, 0, 0.01),
            tool_to_tcp=transform(0.105, 0, 0),
            camera=camera,
            region_world_m=[0.2, 0.25, 0.004],
            support_height_m=0.0,
            development_dual=dict(
                schema="g1.development.dual-registration.v1",
                scene_id=SCENE_ID,
                scene_asset_sha256=ASSET_SHA,
                camera_sha256=_sha(_json(camera).encode()),
                development_sources_sha256=sources,
                development_source_generation=_sha(_json(sources).encode()),
                markers=markers,
                agreement_m=AGREEMENT_M,
                prefer_id=7,
                authority="DEVELOPMENT_ONLY",
                structure_mass_kg=BODY_MASS_KG - 0.08,
            ),
        )
    )


def geometry_descriptor():
    return json.loads(_descriptor_json())


def matches_identity(payload):
    return (
        payload.get("marker_family") == FAMILY
        or "development_dual" in payload
        or payload.get("asset_path") == ASSET_PATH
        or payload.get("registration_id") == REGISTRATION_ID
        or isinstance(payload.get("pose_marker"), dict)
        and payload["pose_marker"].get("marked_asset_sha256") == ASSET_SHA
    )


def validate_geometry(payload):
    if _json(payload) != _descriptor_json():
        raise ValueError(
            "development dual camera, marker, transform, asset or source binding differs"
        )


def validate_asset(root):
    from cloud_edge_robot_arm.vision.native_calibration import _safe

    base = _safe(root, BASE_ASSET_PATH).read_bytes()
    actual = _safe(root, ASSET_PATH).read_bytes()
    if _sha(actual) != ASSET_SHA or actual != build_xml(base):
        raise ValueError("development physical board or registered asset bytes differ")


def check_source_binding(payload, catalog):
    from scripts.graduation.g1_dual_runtime_adapter import SOURCE_SHA256

    validate_geometry(payload)
    expected = {
        **payload["development_dual"]["development_sources_sha256"],
        ASSET_PATH: ASSET_SHA,
        BASE_ASSET_PATH: BASE_SHA,
    }
    root = Path(__file__).resolve().parents[2]
    for name, baseline_sha in SOURCE_SHA256.items():
        effective_sha = _sha((root / name).read_bytes())
        if effective_sha == baseline_sha:
            raise ValueError("unadapted baseline supplied as development runtime source")
        expected[name] = effective_sha
    if any(catalog.get(name) != digest for name, digest in expected.items()):
        raise ValueError("development dual registration and runtime sources differ")
    return set(expected)


def compiled_world_bounds(kind, size, center, rotation):
    """Tight world-axis bounds for a compiled box, capsule or cylinder."""
    import mujoco

    size, center, rotation = (np.asarray(x, dtype=float) for x in (size, center, rotation))
    if (
        size.shape != (3,)
        or center.shape != (3,)
        or rotation.shape != (3, 3)
        or not all(np.isfinite(x).all() for x in (size, center, rotation))
        or not np.allclose(rotation.T @ rotation, np.eye(3), rtol=0, atol=1e-12)
        or not math.isclose(float(np.linalg.det(rotation)), 1.0, rel_tol=0, abs_tol=1e-12)
    ):
        raise ValueError("invalid compiled finite world geometry or rotation")
    axis = abs(rotation[:, 2])
    if kind == mujoco.mjtGeom.mjGEOM_BOX and np.all(size > 0):
        extent = abs(rotation) @ size
        shape = "BOX"
    elif kind == mujoco.mjtGeom.mjGEOM_CAPSULE and np.all(size[:2] > 0):
        extent = size[0] + size[1] * axis
        shape = "CAPSULE"
    elif kind == mujoco.mjtGeom.mjGEOM_CYLINDER and np.all(size[:2] > 0):
        extent = size[1] * axis + size[0] * np.sqrt(np.maximum(0, 1.0 - axis**2))
        shape = "CYLINDER"
    else:
        raise ValueError("unsupported shape or nonpositive size for reset clearance")
    lo, hi = center - extent, center + extent
    rounding = 1e-12
    return dict(
        shape=shape,
        size_m=size.tolist(),
        center_world_m=center.tolist(),
        rotation_to_world=rotation.ravel().tolist(),
        minimum_world_m=lo.tolist(),
        maximum_world_m=hi.tolist(),
        outward_margin_per_face_m=rounding,
        expanded_minimum_world_m=np.nextafter(lo - rounding, -math.inf).tolist(),
        expanded_maximum_world_m=np.nextafter(hi + rounding, math.inf).tolist(),
    )


def reset_pair_clearance(model, data, name, other):
    """Prove static separation. Keep the simulator distance return as its own observation."""
    import mujoco

    shapes = []
    for role in (name, other):
        geom, world = model.geom(role), data.geom(role)
        shape = compiled_world_bounds(geom.type[0], geom.size, world.xpos, world.xmat.reshape(3, 3))
        shapes.append(dict(name=role, **shape))
    a, b = shapes

    def axis_gaps(prefix):
        lo, hi = prefix + "minimum_world_m", prefix + "maximum_world_m"
        return np.maximum(0, np.maximum(np.asarray(a[lo]) - b[hi], np.asarray(b[lo]) - a[hi]))

    raw_gaps, expanded_gaps = axis_gaps(""), axis_gaps("expanded_")
    lower = float(np.linalg.norm(expanded_gaps))
    first, second = model.geom(name).id, model.geom(other).id
    raw = float(mujoco.mj_geomDistance(model, data, first, second, 3.0, None))
    actual_contact = any({int(c.geom1), int(c.geom2)} == {first, second} for c in data.contact)
    if (
        actual_contact
        or not math.isfinite(raw)
        or raw < 0
        or not math.isfinite(lower)
        or lower <= 0
    ):
        raise ValueError(
            f"reset strict separation unproved for {name}/{other}: "
            f"contact={actual_contact}, raw={raw}, expanded lower bound={lower}"
        )
    table_gap = None
    if other == "table" and a["shape"] == b["shape"] == "BOX":
        r0 = np.asarray(a["rotation_to_world"]).reshape(3, 3)
        r1 = np.asarray(b["rotation_to_world"]).reshape(3, 3)
        # If the block's bottom center projects strictly into the horizontal tabletop,
        # that vertical segment actually attains the separating-plane lower bound.
        horizontal = all(np.array_equal(abs(r[:, 2]), [0.0, 0.0, 1.0]) for r in (r0, r1))
        delta = r1.T @ (np.asarray(a["center_world_m"]) - b["center_world_m"])
        if horizontal and np.all(abs(delta[:2]) < np.asarray(b["size_m"])[:2] - 1e-12):
            table_gap = a["minimum_world_m"][2] - b["maximum_world_m"][2]
            if not math.isclose(
                table_gap, float(np.linalg.norm(raw_gaps)), rel_tol=0, abs_tol=1e-12
            ):
                raise ValueError(f"inconsistent exact tabletop separation for {name}/{other}")
    zero = raw == 0.0
    queries = {}
    if zero:
        for cutoff in (0.05, 0.1, 0.3, 1.0, 3.0):
            endpoints = np.zeros(6)
            forward = float(mujoco.mj_geomDistance(model, data, first, second, cutoff, endpoints))
            reverse = float(mujoco.mj_geomDistance(model, data, second, first, cutoff, None))
            if not np.isfinite([forward, reverse, *endpoints]).all():
                raise ValueError("nonfinite secondary reset clearance witness")
            queries[str(cutoff)] = dict(
                forward_m=forward, reverse_m=reverse, witness_world_m=endpoints.tolist()
            )
    return dict(
        geometries=shapes,
        units="m",
        raw_distmax_m=3.0,
        raw_mj_geomDistance_m=raw,
        raw_axis_gaps_m=raw_gaps.tolist(),
        expanded_axis_gaps_m=expanded_gaps.tolist(),
        raw_aabb_lower_bound_m=float(np.linalg.norm(raw_gaps)),
        expanded_aabb_lower_bound_m=lower,
        table_vertical_gap_m=table_gap,
        contact_observed=actual_contact,
        raw_zero_despite_separation=zero,
        additional_distance_queries=queries,
        criterion="strictly positive outward-expanded world-AABB Euclidean lower bound",
    )


def audit_asset(root):
    """Compile and verify the developed assembly at the two prescribed poses, zero mj_step calls."""
    import mujoco

    from cloud_edge_robot_arm.vision.marker_families import _canonical

    def require(ok, reason):
        if not ok:
            raise ValueError("development assembly differs: " + reason)

    root = Path(root)
    validate_asset(root)
    xml, old_xml = (ET.parse(root / p).getroot() for p in (ASSET_PATH, BASE_ASSET_PATH))
    model, old = (
        mujoco.MjModel.from_xml_path(str(root / p)) for p in (ASSET_PATH, BASE_ASSET_PATH)
    )

    def strip(tree, prefixes):
        obj = tree.find("./worldbody/body[@name='object']")
        for node in list(obj):
            if node.get("name", "").startswith(prefixes):
                obj.remove(node)

    body = xml.find("./worldbody/body[@name='object']")
    nodes = {g.attrib["name"]: dict(g.attrib) for g in body.findall("geom")}
    require(set(nodes) == box_names() and len(body.findall("geom")) == 79, "79 named direct boxes")
    strip(xml, tuple(MARKER_PREFIXES.values()))
    strip(old_xml, (OLD_PREFIX,))
    require(_canonical(xml) == _canonical(old_xml), "non-marker physics, camera or controller XML")
    shared = (
        "qpos0",
        "body_parentid",
        "body_pos",
        "body_quat",
        "jnt_type",
        "jnt_bodyid",
        "jnt_axis",
        "jnt_qposadr",
        "jnt_dofadr",
        "jnt_range",
        "jnt_limited",
        "dof_damping",
        "dof_armature",
        "actuator_trnid",
        "actuator_trntype",
        "actuator_gaintype",
        "actuator_biastype",
        "actuator_ctrlrange",
        "actuator_gainprm",
        "actuator_biasprm",
        "cam_pos",
        "cam_quat",
        "cam_fovy",
        "cam_bodyid",
        "site_pos",
        "site_quat",
        "site_bodyid",
    )
    for key in shared:
        require(np.array_equal(getattr(model, key), getattr(old, key)), key)
    require(
        model.opt.timestep == old.opt.timestep
        and model.opt.integrator == old.opt.integrator
        and np.array_equal(model.opt.gravity, old.opt.gravity),
        "physics options",
    )
    obj = model.body("object").id
    structural = [
        "object_geom",
        *(p + s for p in MARKER_PREFIXES.values() for s in ("plate", "support")),
    ]
    masses = np.array([float(nodes[n]["mass"]) for n in structural])
    centers = np.array([model.geom(n).pos for n in structural])
    half = np.array([model.geom(n).size for n in structural])
    com = np.average(centers, axis=0, weights=masses)
    tensor = np.zeros((3, 3))
    pieces = {}
    for name, m, c, h in zip(structural, masses, centers, half, strict=True):
        box_inertia = m / 3 * (h @ h - h * h)
        d = c - com
        tensor += np.diag(box_inertia) + m * ((d @ d) * np.eye(3) - np.outer(d, d))
        geom = model.geom(name)
        require(
            geom.bodyid[0] == obj
            and (geom.contype[0], geom.conaffinity[0]) == (1, 3)
            and m > 0
            and np.all(h > 0),
            "structural collision shell and mass " + name,
        )
        pieces[name] = dict(
            mass_kg=float(m),
            half_extent_m=h.tolist(),
            center_object_m=c.tolist(),
            density_kg_m3=float(m / (8 * np.prod(h))),
            inertia_at_center_kg_m2=box_inertia.tolist(),
            contype=int(geom.contype[0]),
            conaffinity=int(geom.conaffinity[0]),
        )
    rot = np.zeros(9)
    mujoco.mju_quat2Mat(rot, model.body_iquat[obj])
    rot = rot.reshape(3, 3)
    compiled_tensor = rot @ np.diag(model.body_inertia[obj]) @ rot.T
    require(
        abs(model.body_mass[obj] - BODY_MASS_KG) < 1e-12
        and np.allclose(com, model.body_ipos[obj], atol=1e-12, rtol=0)
        and np.allclose(compiled_tensor, tensor, atol=1e-9, rtol=0),
        "physical assembly mass/COM/inertia",
    )
    for body_id in range(model.nbody):
        if body_id != obj:
            for key in ("body_mass", "body_ipos", "body_iquat", "body_inertia"):
                require(
                    np.array_equal(getattr(model, key)[body_id], getattr(old, key)[body_id]),
                    "non-object " + key,
                )
    plate_bounds = []
    for code, prefix in MARKER_PREFIXES.items():
        glyph = bits(code)
        for r, row in enumerate(glyph):
            for c, white in enumerate(row):
                name = prefix + f"r{r}c{c}"
                geom = model.geom(name)
                center = np.array(CENTERS[code]) + [
                    (c - 2.5) * 0.0125,
                    (2.5 - r) * 0.0125,
                    -0.00001,
                ]
                require(
                    np.allclose(geom.pos, center, atol=1e-12, rtol=0)
                    and np.array_equal(geom.quat, [1, 0, 0, 0])
                    and np.allclose(geom.size, [0.00625, 0.00625, 0.00001], rtol=0, atol=1e-12)
                    and np.allclose(
                        geom.rgba, [0.98 if white else 0.01] * 3 + [1], atol=1e-7, rtol=0
                    )
                    and nodes[name]["mass"] == "0"
                    and geom.bodyid[0] == obj
                    and geom.contype[0] == geom.conaffinity[0] == 0,
                    "printed bit " + name,
                )
        plate, bridge, quiet, cube = (
            model.geom(n)
            for n in (prefix + "plate", prefix + "support", prefix + "quiet", "object_geom")
        )
        lo, hi = plate.pos - plate.size, plate.pos + plate.size
        plate_bounds.append((lo, hi))
        require(
            abs(hi[2] - (quiet.pos[2] - quiet.size[2])) < 1e-12
            and abs((quiet.pos[2] + quiet.size[2]) - 0.03503) < 1e-12
            and np.array_equal(quiet.size[:2], plate.size[:2])
            and np.array_equal(quiet.pos[:2], plate.pos[:2])
            and np.allclose(quiet.rgba, [0.98, 0.98, 0.98, 1], atol=1e-7, rtol=0)
            and quiet.contype[0] == quiet.conaffinity[0] == 0,
            "supported quiet zone",
        )
        axis = 1 if code == 7 else 0
        for lower, upper in ((cube, bridge), (bridge, plate)):
            overlaps = np.minimum(lower.pos + lower.size, upper.pos + upper.size) - np.maximum(
                lower.pos - lower.size, upper.pos - upper.size
            )
            require(
                abs(overlaps[axis]) < 1e-12 and np.delete(overlaps, axis).min() > 0,
                "positive common support face without interpenetration",
            )
    (lo0, hi0), (lo1, hi1) = plate_bounds
    overlap = np.maximum(0, np.minimum(hi0, hi1) - np.maximum(lo0, lo1))
    require(float(np.prod(overlap[:2])) < 1e-18, "board footprints overlap")
    observations = []
    arm = [
        "base",
        *(f"link{i}" for i in range(1, 7)),
        "hand",
        "left_finger_geom",
        "right_finger_geom",
    ]
    for x, y, z, yaw in POSES:
        data = mujoco.MjData(model)
        data.qpos[model.joint("joint1").qposadr[0]] = -0.8
        for finger in ("finger_left_joint", "finger_right_joint"):
            data.qpos[model.joint(finger).qposadr[0]] = 0.04
        q = model.joint("object_free").qposadr[0]
        data.qpos[q : q + 7] = [x, y, z, math.cos(yaw / 2), 0, 0, math.sin(yaw / 2)]
        mujoco.mj_forward(model, data)
        cube = data.geom("object_geom")
        world_object = np.eye(4)
        world_object[:3, :3], world_object[:3, 3] = cube.xmat.reshape(3, 3), cube.xpos
        fk = {}
        for code, prefix in MARKER_PREFIXES.items():
            world_marker = world_object @ np.asarray(transform(*CENTERS[code])).reshape(4, 4)
            actual, errors = [], []
            for (r, c), corner in zip(
                ((0, 0), (0, 5), (5, 5), (5, 0)), local_corners(), strict=True
            ):
                name = prefix + f"r{r}c{c}"
                geom = data.geom(name)
                local = model.geom(name).size * [1 if c else -1, -1 if r else 1, 1]
                point = geom.xpos + geom.xmat.reshape(3, 3) @ local
                actual.append(point.tolist())
                errors.append(float(np.linalg.norm(point - (world_marker @ [*corner, 1])[:3])))
            require(max(errors) < 1e-10, "ordered grid corner FK")
            fk[str(code)] = dict(
                ordered_corners_world_m=actual,
                world_T_marker=world_marker.ravel().tolist(),
                maximum_corner_error_m=max(errors),
            )
        pair_evidence = {
            name + "/" + other: reset_pair_clearance(model, data, name, other)
            for name in structural[1:]
            for other in ("table", *arm)
        }
        clearance = {key: row["expanded_aabb_lower_bound_m"] for key, row in pair_evidence.items()}
        contacts = [[model.geom(c.geom1).name, model.geom(c.geom2).name] for c in data.contact]
        require(
            not any(set(pair) & set(structural[1:]) for pair in contacts), "reset structure contact"
        )
        observations.append(
            dict(
                xyz_yaw=[x, y, z, yaw],
                markers=fk,
                structure_to_arm_and_table_clearance_m=clearance,
                clearance_semantics="conservative lower bounds after outward rounding, metres",
                shape_pair_evidence=pair_evidence,
                contacts=contacts,
                site_tcp_world_m=data.site("tcp").xpos.tolist(),
                registered_grasp_world_m=(world_object @ [0, 0, 0.01, 1])[:3].tolist(),
            )
        )
    return dict(
        schema="g1.development.compiled-dual-asset.v1",
        asset_sha256=ASSET_SHA,
        geometry=geometry_descriptor(),
        direct_boxes=len(nodes),
        structure=pieces,
        original_body_mass_kg=float(old.body_mass[old.body("object").id]),
        compiled_body_mass_kg=float(model.body_mass[obj]),
        com_object_m=com.tolist(),
        compiled_principal_inertia_kg_m2=model.body_inertia[obj].tolist(),
        inertia_tensor_object_kg_m2=compiled_tensor.tolist(),
        model_options_checked=True,
        controller_camera_tool_compiled_fields=list(shared),
        plate_overlap_m2=float(np.prod(overlap[:2])),
        camera_fovy_deg=float(model.cam("rgbd").fovy[0]),
        tool_tcp_offset_m=model.site("tcp").pos.tolist(),
        reset_fk=observations,
        verified_reset_pair_count=sum(len(pose["shape_pair_evidence"]) for pose in observations),
        raw_zero_despite_separation_count=sum(
            row["raw_zero_despite_separation"]
            for pose in observations
            for row in pose["shape_pair_evidence"].values()
        ),
        physics_steps=0,
        dispatched_commands=0,
    )
