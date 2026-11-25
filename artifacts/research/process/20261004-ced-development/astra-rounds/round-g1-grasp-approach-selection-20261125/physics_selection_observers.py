"""Independent optical and mechanical readers for the finite original-controller study."""

import argparse
import fcntl
import gzip
import hashlib
import json
import time
import warnings
from pathlib import Path

import numpy as np

import physics_selection_study as study


def pairs(root, phase):
    reg, fits, blind = study.inputs(root)
    if phase in ("center-fit", "tangent-fit"):
        return [(n, c) for n in fits for c in study.allowed(root, root / study.RAW, phase, [n])]
    names = [p["name"] for p in reg["blind_mechanical_first" if phase == "blindM" else "blind_optical_first"]]
    return [(n, c) for n in names for c in study.allowed(root, root / study.RAW, "blind", [n])]


def camera_exposures(root, phase):
    import cv2
    import mujoco
    from OpenGL import GL
    from cloud_edge_robot_arm.simulation.mujoco.camera import MuJoCoRGBDCamera
    from cloud_edge_robot_arm.vision.observations import observation_from_sensor_frame
    from scripts.graduation.g1_formal_runtime import bind_scene
    cv2.setNumThreads(1)
    dest = root / study.RAW
    geom = study.geometry(root)
    model = mujoco.MjModel.from_xml_path(str(root / geom["asset_path"]))
    model.opt.timestep = 1 / 240
    data = mujoco.MjData(model)
    with (root / study.LOCK).open("rb") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        camera = MuJoCoRGBDCamera(mujoco, model, width=320, height=240)
        try:
            for case, cid in pairs(root, phase):
                target = dest / "independent-exposures" / case / cid
                if (target / "exposure.json").is_file():
                    continue
                course = dest / "courses" / case / cid
                handoffs = study.read(course / "handoffs.json")
                closure = next((h for h in handoffs if h["stage"] == "GRASP"), None)
                if not closure:
                    study.write(target / "exposure.json", {"case": case, "candidate": cid, "frames": []})
                    continue
                with np.load(course / "series.npz") as a:
                    steps = a["step"]
                    index = int(closure["step"] - steps[0])
                    data.qpos[:] = a["q"][index]
                    data.qvel[:] = a["qvel"][index]
                    data.ctrl[:] = a["ctrl"][index]
                data.time = closure["step"] / 240
                mujoco.mj_forward(model, data)
                scene = "selection-closure-" + case
                noise = hashlib.sha256(("selection-closure-v1/" + case + "/" + cid).encode()).digest()
                rng = np.random.default_rng(int.from_bytes(noise[:8], "big"))
                target.mkdir(parents=True, exist_ok=True)
                frames = []
                with bind_scene(scene):
                    for j in range(3):
                        start = time.monotonic_ns()
                        frame = observation_from_sensor_frame(camera.capture(
                            data, rng=rng, noise_std_m=.001, scene_id=scene, episode_id=scene
                        ), source="mujoco_camera", png_compress_level=1)
                        elapsed = (time.monotonic_ns() - start) / 1e6
                        path = target / f"exposure-{j}.json.gz"
                        path.write_bytes(gzip.compress(frame.model_dump_json().encode(), 3, mtime=0))
                        frames.append({"file": path.name, "sha256": study.sha(path), "capture_ms": elapsed,
                                       "frame_id": frame.frame_id, "checksum_sha256": frame.checksum_sha256})
                tcp = data.site("tcp")
                study.write(target / "exposure.json", {
                    "case": case, "candidate": cid, "frames": frames, "scene": scene,
                    "renderer": GL.glGetString(GL.GL_RENDERER).decode(), "step": closure["step"],
                    "encoder_q": data.qpos[:9].tolist(), "encoder_dq": data.qvel[:9].tolist(),
                    "tcp": tcp.xpos.tolist(), "wrist": tcp.xmat.reshape(3, 3).tolist(),
                    "asset": study.sha(root / geom["asset_path"]),
                })
        finally:
            camera.close()


def optical_margins(angle, patch, reason):
    if patch is None or "bilateral_contact_domain" not in patch:
        return {"eligible_fraction": -1.0}
    d = patch["bilateral_contact_domain"]
    moments = np.array(d["per_pad_moment_demand_capacity_Nm"])
    overlap = np.array(d["per_pad_xz_overlap_m"])
    margins = {
        "yaw_deg": 3 - float(angle["upper_error_deg"]),
        "combined_radius_allowance": 1 - d["squared_combined_domain_radius"],
        "opening_m": min(d["robust_per_pad_gap_m"]),
        "overlap_x_m": float(min(overlap[:, 0])) - .040,
        "overlap_z_m": float(min(overlap[:, 1])) - .032,
        "com_m": min(d["per_pad_com_edge_margin_m"]) - .003,
        "torque_Nm": float(min(moments[:, 1] - moments[:, 0])),
        "table_m": min(d["per_pad_min_table_gap_m"]) - .002,
    }
    score = min(margins[k] / scale for k, scale in zip(margins, (3, 1, .001, .04, .032, .003, .008, .002), strict=True))
    margins["eligible_fraction"] = min(score, -1e-6) if reason else max(0, score)
    return margins


def optics(root, phase):
    from cloud_edge_robot_arm.vision.observations import RGBDObservation
    from scripts.graduation.g1_complete_cv_angle import grasp_readiness
    from scripts.graduation.g1_formal_runtime import bind_scene
    from scripts.graduation.g1_visibility_vision import measure_frame
    dest = root / study.RAW
    geom = study.geometry(root)
    for case, cid in pairs(root, phase):
        output = dest / "optical-reader" / case / (cid + ".json")
        if output.is_file():
            continue
        source = dest / "independent-exposures" / case / cid / "exposure.json"
        z = study.read(source)
        rows = []
        for exposure in z["frames"]:
            source_frame = source.parent / exposure["file"]
            if study.sha(source_frame) != exposure["sha256"]:
                raise ValueError("changed optical input")
            frame = RGBDObservation.model_validate_json(gzip.decompress(source_frame.read_bytes()))
            start = time.monotonic_ns()
            with bind_scene(z["scene"]):
                marker = measure_frame(frame, geom)
                if marker["usable"]:
                    angle, patch, reason = grasp_readiness(
                        frame, marker, geom, marker["object_center_world_m"],
                        np.array(marker["rotation_object_to_world"]).reshape(3, 3), np.array(z["tcp"]),
                        np.array(z["wrist"]), np.array(z["encoder_q"][7:9]), closure=True)
                else:
                    angle, patch, reason = None, None, marker["reason"]
            rows.append({"frame_id": frame.frame_id, "status": reason or "PASS", "ids": marker["usable_ids"],
                         "angle": angle, "patch": patch, "margins": optical_margins(angle, patch, reason),
                         "optical_read_ms": (time.monotonic_ns() - start) / 1e6})
        study.write(output, {
            "case": case, "candidate": cid, "exposures_sha256": study.sha(source), "frames": rows,
            "all_pass": len(rows) == 3 and all(r["status"] == "PASS" for r in rows),
            "worst_optical_margin": min((f["margins"]["eligible_fraction"] for f in rows), default=-1),
        })


def physical_raw(root, phase):
    import mujoco
    engine = study.native_engine(root)
    dest = root / study.RAW
    for case, cid in pairs(root, phase):
        out = dest / "physical-reader" / case / cid / "physical.json"
        if out.is_file():
            continue
        source = dest / "courses" / case / cid
        result = study.read(source / "result.json")
        a = np.load(source / "series.npz")
        stage = a["stage"]
        contacts, qvel = a["contact_count"], a["qvel"]
        steps = a["step"]
        lift = np.flatnonzero(stage == "LIFT")
        grasp = np.flatnonzero(stage == "GRASP")
        final = np.flatnonzero(stage == "FINAL_OBSERVATION")
        stable = len(final) == 240 and bool(
            np.all(abs(a["cube_corners_world"][final, :, :2] - [.2, .25]) < [.08, .08])
            and np.all(contacts[final, 2] > 0)
            and np.max(np.linalg.norm(qvel[final, 9:12], axis=1)) < .01
            and np.max(np.linalg.norm(qvel[final, 12:15], axis=1)) < .1)
        elapsed, last = {}, int(steps[0])
        for action in result["actions"]:
            elapsed[action["stage"]] = (action["end"] - last) / 240
            last = action["end"]
        b, _ = engine.setup(root, case)
        try:
            sensors = engine.native.Sensors(b)
            grouped = {"GRASP": grasp[-1:].tolist()}
            if len(lift):
                free = lift[contacts[lift, 2] == 0]
                grouped["load_transfer"] = ([int(free[0])] if len(free) else [])
                grouped["LIFT_last"] = [int(lift[-1])]
            selected = [(k, j) for k, indices in grouped.items() for j in indices]
            packed, ctrl, q, forces = a["packed"], a["ctrl"], a["q"], a["forces"]
            rows = []
            for kind, j in selected:
                mujoco.mj_setState(b._model, b._data, packed[j-1], engine.io.STATE)
                b._data.ctrl[:] = ctrl[j]
                mujoco.mj_step(b._model, b._data)
                sample, manifold = sensors.snap(b)
                for expected, actual in ((q[j], sample["q"]), (qvel[j], sample["qvel"]), (forces[j], sample["force_N"])):
                    np.testing.assert_allclose(expected, actual, rtol=0, atol=1e-9)
                rows.append({"phase": kind, "step": int(steps[j]), "contacts": manifold,
                             "com": sample["world_com"].tolist(), "R": sample["rotation"][10].tolist(),
                             "center": sample["centers"][10].tolist(), "forces_N": forces[j].tolist()})
            mode = {"rows": rows, "geom_names": sensors.names, "mass": float(b._model.body_mass[sensors.objectbody])}
        finally:
            b.shutdown()
        backtrack = None
        if len(lift):
            z = a["tcp"][np.r_[lift[0]-1, lift], 2]
            backtrack = float(np.max(np.maximum.accumulate(z) - z))
        method = all(v <= (1 if k in ("GRASP", "RELEASE") else 8) for k,v in elapsed.items())
        physical = bool(result["eligible"] and method and stable and
                        min(result["terminal_grasp_force_N"] or [0]) >= 2 and backtrack <= .001)
        study.write(out, {
            "case": case, "candidate": cid, "native_result_sha256": study.sha(source/"result.json"),
            "series_sha256": study.sha(source/"series.npz"), "force_replay": mode,
            "full_physics_except_static_wrench": physical, "stable_at_least_240": stable, "action_s": elapsed,
            "stable_50mm_for_120": result["last_120_bilateral_over_50mm"],
            "max_backtracking_m": backtrack, "lateral_peak_m": result["lift_peak_lateral_m"],
            "first_native_failure": result["terminal_error"], "forbidden_steps": result["actual_structure_contact_steps"],
            "closed_normals_N": result["terminal_grasp_force_N"],
            "lift_min_gain_last_120_m": result["lift_120_min_gain_m"],
        })
        a.close()


def wrench(root, phase):
    solver = study.load("qualified_friction_wrench", study.OLDER.parent / "round-g1-skill-handoff-20261125/handoff-physics-contact-wrench.py")
    dest = root / study.RAW
    for case, cid in pairs(root, phase):
        source = dest / "physical-reader" / case / cid / "physical.json"
        output = source.with_name("wrench.json")
        if output.is_file():
            continue
        p = study.read(source)
        raw = p["force_replay"]
        values = {}
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=solver.OptimizeWarning, message="Unrecognized options detected.*")
            for row in raw["rows"]:
                solved = solver.frame(row["contacts"], np.array(row["com"]), np.array(row["R"]),
                                      np.array(row["center"]), raw["geom_names"], raw["mass"])
                values[row["phase"]] = {
                    "weights": solved["gravity_scale_from_measured_normals"],
                    "gravity_torque_Nm": solved["gravity_torque_about_measured_patch_centroid_Nm"],
                    "normal_N": solved["force_N"].tolist(), "patches": solved["patch_point_counts"].tolist(),
                    "span_m": solved["patch_xz_span_m"].tolist(),
                }
        passed = bool(p["full_physics_except_static_wrench"] and values.get("GRASP", {}).get("weights", 0) > 1)
        study.write(output, {"case": case, "candidate": cid, "true_mechanical_pass": passed,
                             "raw_sha256": study.sha(source), "wrenches": values})


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--root", required=True, type=Path)
    a.add_argument("--phase", choices=("center-fit", "tangent-fit", "blindM", "blindO"), required=True)
    a.add_argument("--mode", choices=("capture", "optics", "physics", "wrench"), required=True)
    args = a.parse_args()
    {"capture": camera_exposures, "optics": optics, "physics": physical_raw, "wrench": wrench}[args.mode](args.root.resolve(), args.phase)
