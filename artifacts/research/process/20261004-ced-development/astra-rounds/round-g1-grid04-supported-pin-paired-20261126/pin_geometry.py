"""Zero-integration endpoint and shutter-pose checks for the registered pin."""

from itertools import combinations
from xml.etree import ElementTree as ET

import mujoco
import numpy as np
from pin_evidence import HERE, ROOT, read, require, runtime_root, sha, source_module
from pin_prefix import COLLIDABLE, archived_samples, tick_index
from scripts.graduation.g1_complete_cv_clearance import camera_encoder_pose

WORLD_AXES = np.eye(3)
HALFSPACE_TRIPLES = np.array(list(combinations(range(12), 3)))


def compile_pair(plan, output):
    pin, runtime = plan["pin"], plan["runtime"]
    asset = runtime_root(plan) / runtime["asset_relative"].removeprefix("runtime-source/")
    bare = asset.read_bytes()
    root = ET.fromstring(bare)
    require(not any("file" in node.attrib for node in root.iter()), "XML has external assets")
    attributes = {
        "name": pin["name"],
        "type": pin["world_geom"],
        "pos": " ".join(map(str, pin["center_m"])),
        "size": " ".join(map(str, pin["half_size_m"])),
        "quat": " ".join(map(str, pin["quat_wxyz"])),
        "rgba": " ".join(map(str, pin["rgba"])),
        **{key: str(pin[key]) for key in ("group", "contype", "conaffinity")},
    }
    geom = ET.tostring(ET.Element("geom", attributes), encoding="utf-8")
    tag = b"</worldbody>"
    addition = b"  " + geom + b"\n  "
    require(bare.count(tag) == 1, "original worldbody layout differs")
    modified = bare.replace(tag, addition + tag)
    amended = ET.fromstring(modified)
    world = amended.find("worldbody")
    (node,) = world.findall(f"geom[@name='{pin['name']}']")
    require(node.attrib == attributes, "registered pin shape differs")
    world.remove(node)
    require(
        ET.canonicalize(ET.tostring(root), strip_text=True)
        == ET.canonicalize(ET.tostring(amended), strip_text=True),
        "XML differs beyond the single registered world geom",
    )

    with output.open("xb") as stream:
        stream.write(modified)
    a = mujoco.MjModel.from_xml_path(str(asset))
    b = mujoco.MjModel.from_xml_path(str(output))
    aid = np.arange(a.ngeom)
    names = [a.geom(i).name for i in aid]
    require(len(set(names)) == len(names) and all(names), "original geoms require unique names")
    bid = np.array([b.geom(name).id for name in names])
    probe = b.geom(pin["name"])
    require(
        b.ngeom == a.ngeom + 1 and len(set(bid)) == a.ngeom and probe.id not in bid,
        "compiled geom universe differs",
    )
    fields = (
        "bodyid",
        "type",
        "contype",
        "conaffinity",
        "size",
        "pos",
        "quat",
        "friction",
        "rgba",
        "group",
        "matid",
        "solref",
        "solimp",
        "margin",
        "gap",
        "condim",
        "priority",
    )
    for key in fields:
        require(
            np.array_equal(getattr(a, f"geom_{key}")[aid], getattr(b, f"geom_{key}")[bid]),
            f"original compiled geom {key} differs",
        )
    for key in (
        "body_mass",
        "body_inertia",
        "body_pos",
        "body_quat",
        "jnt_pos",
        "jnt_axis",
        "jnt_range",
        "actuator_gainprm",
        "actuator_biasprm",
        "actuator_ctrlrange",
        "cam_pos",
        "cam_quat",
        "cam_fovy",
        "light_pos",
        "light_dir",
    ):
        require(np.array_equal(getattr(a, key), getattr(b, key)), f"original {key} differs")
    a_camera = (a.stat.extent, a.vis.map.znear, a.vis.map.zfar, a.vis.quality.offsamples)
    b_camera = (b.stat.extent, b.vis.map.znear, b.vis.map.zfar, b.vis.quality.offsamples)
    require(
        a_camera == b_camera
        and a_camera[3] == plan["camera"]["offsamples"]
        and float(a.camera("rgbd").fovy[0]) == plan["camera"]["fovy_deg"],
        "original compiled projection setup differs",
    )
    require(
        probe.bodyid[0] == 0
        and np.array_equal(probe.pos, pin["center_m"])
        and np.array_equal(probe.size, pin["half_size_m"]),
        "compiled pin pose differs",
    )
    table = b.geom("table")
    require(
        np.array_equal(table.pos, [0.35, 0, -0.025])
        and np.array_equal(table.size, [0.65, 0.45, 0.025])
        and np.array_equal(table.quat, [1, 0, 0, 0]),
        "original table differs",
    )
    require(
        probe.pos[2] - probe.size[2] == table.pos[2] + table.size[2] == 0.0
        and (abs(probe.pos[:2] - table.pos[:2]) + probe.size[:2] < table.size[:2]).all(),
        "pin bottom is outside the table support plane",
    )
    pairs = [
        name
        for name in names
        if int(b.geom(name).contype[0]) & pin["conaffinity"]
        or int(b.geom(name).conaffinity[0]) & pin["contype"]
    ]
    require(
        set(pairs) == {*COLLIDABLE, "table"}
        and len(pairs) == plan["pin"]["original_collision_entities_excluding_table"] + 1,
        "registered collidable names differ from original bitmasks",
    )
    require(
        all(b.geom(name).type[0] == mujoco.mjtGeom.mjGEOM_BOX for name in COLLIDABLE),
        "registered collision inventory contains non-box geometry",
    )
    return (
        a,
        b,
        aid,
        bid,
        probe.id,
        {
            "original_asset_sha256": sha(asset),
            "diagnostic_asset_sha256": sha(output),
            "new_world_geom": attributes,
            "original_named_geoms": len(aid),
            "collision_entities": list(COLLIDABLE),
            "table_support_mm2": float(4e6 * np.prod(probe.size[:2])),
            "stat_extent": float(a.stat.extent),
            "near": float(a.vis.map.znear),
            "far": float(a.vis.map.zfar),
            "offsamples": a.vis.quality.offsamples,
        },
    )


def separating_axis(center, rotation, half, pin_center, pin_half):
    cross = np.cross(WORLD_AXES[:, None, :], rotation.T[None, :, :]).reshape(9, 3)
    axes = np.concatenate((WORLD_AXES, rotation.T, cross))
    norms = np.linalg.norm(axes, axis=1)
    axes = axes[norms > 1e-12] / norms[norms > 1e-12, None]
    delta = center - pin_center
    gaps = abs(axes @ delta) - abs(axes) @ pin_half - abs(axes @ rotation) @ half
    index = int(np.argmax(gaps))
    axis = axes[index]
    return float(gaps[index]), axis if axis @ delta >= 0 else -axis


def shared_interior(center, rotation, half, pin_center, pin_half):
    object_axes = np.vstack((rotation.T, -rotation.T))
    pin_axes = np.vstack((WORLD_AXES, -WORLD_AXES))
    matrix = np.vstack((object_axes, pin_axes))
    offsets = np.r_[
        object_axes @ center + np.tile(half, 2), pin_axes @ pin_center + np.tile(pin_half, 2)
    ]
    triples = matrix[HALFSPACE_TRIPLES]
    good = abs(np.linalg.det(triples)) > 1e-10
    vertices = np.linalg.solve(triples[good], offsets[HALFSPACE_TRIPLES[good]][:, :, None])[:, :, 0]
    inside = vertices[(vertices @ matrix.T <= offsets + 1e-12).all(axis=1)]
    require(len(inside) >= 4, "no independently supported overlap polytope")
    point = inside.mean(axis=0)
    return {"point_m": point.tolist(), "slack_mm": float(1e3 * np.min(offsets - matrix @ point))}


def endpoint_gap(model, data, probe_id, tolerance, tick, journal, representation):
    center = data.geom_xpos[probe_id]
    half = model.geom_size[probe_id]
    rows = []
    for name in COLLIDABLE:
        geom = model.geom(name).id
        location = data.geom_xpos[geom]
        rotation = data.geom_xmat[geom].reshape(3, 3)
        margin, axis = separating_axis(location, rotation, model.geom_size[geom], center, half)
        distance = float(mujoco.mj_geomDistance(model, data, geom, probe_id, 0.5, None))
        comparison = "both_signs"
        if abs(distance) <= tolerance and margin > tolerance:
            # A positive interval between two exact supporting planes certifies separation.
            upper = axis @ center + abs(axis) @ half
            lower = axis @ location - abs(axis @ rotation) @ model.geom_size[geom]
            require(
                lower - upper > tolerance, f"{representation} {tick} {name}: unresolved distance"
            )
            comparison = "separating_planes_when_native_zero"
        elif abs(distance) <= tolerance and margin < -tolerance:
            witness = shared_interior(location, rotation, model.geom_size[geom], center, half)
            require(witness["slack_mm"] > 1e3 * tolerance, "native zero without overlap witness")
            comparison = "halfspace_overlap_when_native_zero"
        else:
            require(
                abs(margin) > tolerance
                and abs(distance) > tolerance
                and (margin > 0.0) == (distance > 0.0),
                f"{representation} {tick} {name}: box and native sign do not agree",
            )
        rows.append(
            {
                "tick": tick,
                "entity": name,
                "representation": representation,
                "sat_margin_m": margin,
                "native_signed_distance_m": distance,
                "comparison": comparison,
            }
        )
    journal.extend(rows)
    return min(rows, key=lambda row: row["sat_margin_m"])


def static_pose(plan, asset, data, expected, observation):
    frame, encoder, label = observation
    names = [*(f"joint{i}" for i in range(1, 8)), "finger_left_joint", "finger_right_joint"]
    q = encoder["camera_joint_positions_rad"] + encoder["camera_finger_positions_m"]
    for name, value in zip(names, q, strict=True):
        data.qpos[int(asset.joint(name).qposadr[0])] = value
    joint = asset.joint("object_free")
    geom = asset.geom("object_geom")
    address = int(joint.qposadr[0])
    require(
        geom.bodyid[0] == joint.bodyid[0]
        and np.all(geom.pos == 0)
        and np.array_equal(geom.quat, [1, 0, 0, 0]),
        "original object geom transform differs from free joint",
    )
    rotation = np.asarray(label["rotation"])
    require(
        np.isfinite(rotation).all()
        and np.linalg.det(rotation) > 0
        and np.linalg.norm(rotation.T @ rotation - np.eye(3)) <= 1e-9,
        "source rotation is invalid",
    )
    data.qpos[address : address + 3] = label["center_m"]
    mujoco.mju_mat2Quat(data.qpos[address + 3 : address + 7], rotation.ravel())
    data.qvel[:] = expected["dq"]
    data.ctrl[:] = expected["ctrl"]
    data.time = frame.sim_time_s
    require(
        np.isfinite(data.qpos).all()
        and np.isfinite(data.qvel).all()
        and np.isfinite(data.ctrl).all(),
        "non-finite shutter state",
    )
    mujoco.mj_forward(asset, data)
    cp = data.geom("object_geom")
    actual = camera_encoder_pose(asset, data)
    enc = actual["camera_joint_positions_rad"] + actual["camera_finger_positions_m"]
    camera = plan["camera"]
    quaternion = np.empty(4)
    mujoco.mju_mat2Quat(quaternion, data.site("tcp").xmat)
    quaternion_error = min(
        np.linalg.norm(quaternion - encoder["tcp_quaternion_wxyz"]),
        np.linalg.norm(quaternion + encoder["tcp_quaternion_wxyz"]),
    )
    errors = {
        "object_position_l2_m": float(np.linalg.norm(cp.xpos - label["center_m"])),
        "object_rotation_frobenius": float(np.linalg.norm(cp.xmat.reshape(3, 3) - rotation)),
        "tcp_position_l2_m": float(
            np.linalg.norm(data.site("tcp").xpos - encoder["tcp_position_m"])
        ),
        "tcp_quaternion_l2": float(quaternion_error),
        "encoder_absolute": float(np.max(abs(np.array(enc) - q))),
        "final_joint_minus_shutter_max_rad": float(
            np.max(abs(np.asarray(q[:7]) - np.asarray(expected["q"][:7])))
        ),
    }
    for key, limit in (
        ("object_position_l2_m", "restore_position_l2_max_m"),
        ("object_rotation_frobenius", "restore_rotation_frobenius_max"),
        ("tcp_position_l2_m", "restore_position_l2_max_m"),
        ("tcp_quaternion_l2", "restore_rotation_frobenius_max"),
        ("encoder_absolute", "encoder_abs_max_per_native_unit"),
    ):
        require(errors[key] <= camera[limit], f"restored shutter {expected['tick']} {key} differs")
    require(
        data.time == expected["t"] == frame.sim_time_s == actual["camera_encoder_sim_time_s"]
        and abs(data.time - expected["tick"] / 240) <= camera["source_time_to_tick_abs_max_s"],
        "restored shutter clock differs",
    )
    return errors


def geometry(plan, prefix_rows, output, journal):
    a, b, aid, bid, probe, scene = compile_pair(plan, output)
    bdata = mujoco.MjData(b)
    adata = mujoco.MjData(a)
    tol = plan["pin"]["strict_separation_m_gt"]
    normal = read(ROOT / plan["roots"]["native"] / "normal.json")
    original = tick_index(normal[:865], "tick", 1520, 2384)
    ticks = tick_index(prefix_rows, "step", 0, 1520)

    def evaluate(tick, q, label):
        bdata.qpos[:] = q
        mujoco.mj_kinematics(b, bdata)
        return endpoint_gap(b, bdata, probe, tol, tick, journal, label)

    gaps = {}
    for tick in range(2385):
        q = ticks[tick]["q"] if tick < 1520 else original[tick]["q"]
        sample = evaluate(tick, q, "final_q_fk")
        require(sample["sat_margin_m"] > tol, f"normal endpoint {tick} fails separation: {sample}")
        gaps[tick] = sample
        if tick in ticks:
            state = ticks[tick]["geometry"]
            for name in COLLIDABLE:
                idx = b.geom(name).id
                bdata.geom_xpos[idx] = state[name]["center_m"]
                bdata.geom_xmat[idx] = np.asarray(state[name]["rotation"]).ravel()
            cached = endpoint_gap(b, bdata, probe, tol, tick, journal, "native_cache")
            require(
                cached["sat_margin_m"] > tol, f"cached endpoint {tick} fails separation: {cached}"
            )

    def margin(row):
        return row["sat_margin_m"]

    minimum = min(gaps.values(), key=margin)
    lift = min((gaps[tick] for tick in range(1520, 2385)), key=margin)
    approach = min((gaps[tick] for tick in (0, *range(872, 1281))), key=margin)
    require(
        lift["tick"] == 1639
        and round(1e3 * margin(lift), 3) == 0.299
        and round(1e3 * margin(approach), 3) == 2.272,
        "previously published minima differ",
    )
    cache = min((row for row in journal if row["representation"] == "native_cache"), key=margin)
    missing = set(range(1, 872)) | set(range(1281, 1520))
    gap_cache_min = min(
        (
            row
            for row in journal
            if row["representation"] == "native_cache" and row["tick"] in missing
        ),
        key=margin,
    )
    gap_fk_min = min((gaps[tick] for tick in missing), key=margin)

    previous_round = HERE.parent / "round-g1-grid04-2384-stop-space-separation-20261126"
    stop_reader = source_module(previous_round / "read_stop_space.py")
    published = read(previous_round / "stop-space.public.json")
    old_pin = published["checked"][0]["new_geometry_witness"]["point_world_m"]
    witness_model = mujoco.MjSpec.from_file(
        str(runtime_root(plan) / plan["runtime"]["asset_relative"].removeprefix("runtime-source/"))
    )
    witness_model.worldbody.add_geom(
        name="historical_pin_negative",
        type=mujoco.mjtGeom.mjGEOM_BOX,
        pos=[*old_pin[:2], old_pin[2] * 0.5],
        size=[0.00025, 0.00025, old_pin[2] * 0.5],
        contype=1,
        conaffinity=3,
    )
    old_model = witness_model.compile()
    old_data = mujoco.MjData(old_model)
    old_data.qpos[:] = original[1520]["q"]
    mujoco.mj_kinematics(old_model, old_data)
    old_distance = mujoco.mj_geomDistance(
        old_model,
        old_data,
        old_model.geom("object_geom").id,
        old_model.geom("historical_pin_negative").id,
        0.5,
        None,
    )
    require(round(1000 * float(old_distance), 3) == -0.744, "historical pin negative differs")
    stop_trajectories = {
        tick: stop_reader.load_trajectory(tick, tick, original) for tick in range(2376, 2385)
    }
    stops = [
        evaluate(offset, q, "original_2384_hold")
        for offset, q in enumerate(stop_trajectories[2384]["q"])
    ]
    intersecting = [row["tick"] for row in stops if margin(row) < -tol]
    require(
        len(stops) == 241
        and intersecting
        and intersecting[0] == 79
        and len(intersecting) == 162
        and margin(stops[78]) > tol,
        "original first stop intersection differs",
    )
    evaluate(79, stop_trajectories[2384]["q"][79], "first_overlap_witness")
    obj = b.geom("object_geom").id
    witness = shared_interior(
        bdata.geom_xpos[obj],
        bdata.geom_xmat[obj].reshape(3, 3),
        b.geom_size[obj],
        bdata.geom_xpos[probe],
        b.geom_size[probe],
    )
    require(round(witness["slack_mm"], 4) == 0.0285, "old HOLD overlap witness differs")

    case = ROOT / plan["roots"]["old"] / plan["roots"]["case_under_old"]
    declarations = [
        (row["file"], row["tick"], row["last_seq"], "LIFT", "FEEDBACK", "motion")
        for row in plan["shutters"]
    ]
    packets = archived_samples(case, declarations, plan["prefix"]["old_episode"])
    shutters = {}
    for slot in plan["shutters"]:
        tick = slot["tick"]
        packet = packets[slot["file"]]
        frame, robot, label = packet
        saved = original[tick]
        require(
            frame.frame_id == slot["original_frame_id"]
            and frame.checksum_sha256 == slot["original_checksum"]
            and frame.sim_time_s == slot["time_s"]
            and saved["phase_sha256"] == slot["phase_sha256"]
            and frame.calibration_version == plan["camera"]["calibration_version"]
            and list(frame.camera_to_world) == plan["camera"]["camera_to_world"]
            and list(frame.intrinsics) == plan["camera"]["intrinsics"]
            and np.array_equal(
                saved["q"][:9], robot["joint_positions_rad"] + robot["finger_positions_m"]
            )
            and saved["contacts"] == sorted(sorted(pair) for pair in label["touching"])
            and saved["cube"] == label["center_m"],
            f"shutter {tick} archive identity differs",
        )
        errors_a = static_pose(plan, a, adata, saved, packet)
        errors_b = static_pose(plan, b, bdata, saved, packet)
        require(
            np.array_equal(adata.geom_xpos[aid], bdata.geom_xpos[bid])
            and np.array_equal(adata.geom_xmat[aid], bdata.geom_xmat[bid]),
            f"original A/B geom transform differs at {tick}",
        )
        exposed = endpoint_gap(b, bdata, probe, tol, tick, journal, "archived_shutter")
        require(
            round(1e3 * margin(exposed), 3) == {2376: 5.090, 2384: 6.338}[tick],
            f"old shutter separation differs at {tick}",
        )
        shutters[str(tick)] = {
            "frame_id": frame.frame_id,
            "frame_checksum": frame.checksum_sha256,
            "phase_sha256": saved["phase_sha256"],
            "errors_A": errors_a,
            "errors_B": errors_b,
            "nearest_pin_margin": exposed,
            "time_s": frame.sim_time_s,
        }
    return {
        "scene": scene,
        "all_original_finite_endpoints": len(gaps),
        "missing_endpoints_now_checked": len(missing),
        "minimum_fk": minimum,
        "minimum_native_cache": cache,
        "new_intervals_minimum_fk": gap_fk_min,
        "new_intervals_minimum_cache": gap_cache_min,
        "minimum_lift": lift,
        "minimum_archived_approach": approach,
        "old_pin_LIFT_entry_native_mm": 1000 * float(old_distance),
        "original_stop_archives": len(stop_trajectories),
        "original_hold_2384": {
            "endpoint_count": len(stops),
            "first_overlap": intersecting[0],
            "overlap_count": len(intersecting),
            "preceding": stops[78],
            "minimum": min(stops, key=margin),
            "witness": witness,
        },
        "restored_static_shutters": shutters,
    }
