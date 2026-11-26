"""Independently rerun the frozen static scan and verify diagnostic controls."""
import argparse
import hashlib
from pathlib import Path

import mujoco as mj
import numpy as np

import fixed_tcp_geometry as scan


def controls(plan):
    slots, calibration, _ = scan.preflight(plan)
    model = mj.MjModel.from_xml_path(str(scan.ASSET))
    model.opt.timestep = 1/240
    data = mj.MjData(model)
    scan.restore(model, data, slots["B/dense-fit-01/5397"], calibration)
    code = model.geom("g1_dual_id8_r2c2")
    geom = data.geom(code.id)
    point = geom.xpos + code.size[2] * geom.xmat.reshape(3,3)[:,2]
    rays = scan.Rays(model,data,calibration["primary_camera"])
    baseline_target = scan.pose(data)
    real = rays.seen(point,"g1_dual_id8_")[0]
    wrong = not rays.seen(point,"g1_dual_id7_")[0]
    if not (real and wrong):
        raise ValueError("target identity controls failed")
    reference = data.qpos.copy()
    data.qpos[int(model.joint("joint1").qposadr[0])] += 0.002
    mj.mj_forward(model,data)
    pos, rot = scan.residuals(data, baseline_target)
    pose_bad = np.linalg.norm(pos) > 1e-7 and np.linalg.norm(rot) > 1e-6
    data.qpos[:] = reference
    mj.mj_forward(model,data)
    allowed = scan.live_pairs(model,data)
    original_gaps = {pair:scan.distance(model,data,*pair) for pair in allowed}
    require_safe = scan.screen(model,data,allowed,original_gaps)["pass"]
    object_addr = int(model.joint("object_free").qposadr[0])
    data.qpos[object_addr:object_addr+3] = data.geom("hand").xpos
    mj.mj_forward(model,data)
    collision = not scan.screen(model,data,allowed,original_gaps)["pass"]
    if not all((pose_bad, require_safe, collision)):
        raise ValueError("pose and static contact controls failed")
    return {"real_visible_code":real,"wrong_code_rejected":wrong,
            "off_pose_rejected":bool(pose_bad),"overlap_rejected":collision,
            "original_static_clearance":require_safe}


def verify(root):
    original = scan.read(root/"primary.json")
    plan = scan.read(scan.HERE/"plan.json")
    fresh = scan.run(plan)
    scan.write(root/"independent.json",fresh)
    require = scan.require
    require((root/"primary.json").read_bytes() == (root/"independent.json").read_bytes(),
            "static scans differ between processes")
    require(fresh["plan_sha256"] == scan.sha(scan.HERE/"plan.json"), "wrong registration")
    require(len(fresh["states"]) == 10 and fresh["integration_steps"] == fresh["renders"] == 0,
            "incomplete geometry evidence")
    summary = {}
    for key, state in original["states"].items():
        rows = state["per_offset_deg"]
        require(set(rows) == {str(x) for x in plan["grid_degrees"]}, "incomplete signed grid")
        reference = rows["0"]
        require(reference["static_collision"]["pass"] and reference["markers"]["8"]["visible"] == 1024,
                "zero-offset control failed")
        require(sum(v.get("corrections",0) for v in rows.values()) <= 240,
                "iteration budget exceeded")
        visibility = {delta: result["markers"]["7"]["visible"] for delta, result in rows.items()
                      if result.get("markers")}
        best_value = max(visibility.values())
        summary[key] = {
            "axis":state["axis"], "static_valid_rows": len(visibility),
            "id7_points_zero":visibility["0"], "id7_max_points":best_value,
            "id7_best_offsets_deg":[int(k) for k,v in visibility.items() if v==best_value],
            "id7_visibility_by_offset":visibility,
            "edge_columns_by_offset":{delta:value["markers"]["7"]["depth_only_edge_columns"]
                                     for delta,value in rows.items() if value.get("markers")},
            "unique_partial_code_count":sum(len(value["markers"]["7"]["compatible_dictionary_orientations"]) == 1
                                            for value in rows.values() if value.get("markers")),
            "full_id7_face_count":sum(v==1024 for v in visibility.values()),
            "minimum_static_separation_m":min(x["static_collision"]["minimum_gap_m"] for x in rows.values()
                                               if x.get("markers")),
            "max_position_error_m":max(x["tcp_position_error_m"] for x in rows.values() if x.get("markers")),
            "max_rotation_error_rad":max(x["tcp_rotation_error_rad"] for x in rows.values() if x.get("markers")),
        }
    return {"scan_sha256":hashlib.sha256((root/"primary.json").read_bytes()).hexdigest(),
            "controls":controls(plan),"states":summary,
            "new_steps":0,"new_exposures":0,"runtime_claims":0,"formally_certified":False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("result", type=Path)
    args = parser.parse_args()
    scan.write(args.result,verify(args.root))
