"""Read sealed G1 feedback and audit registered coverage without new sensor frames."""
import argparse
import hashlib
import importlib.util
import itertools
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np

HERE = Path(__file__).resolve().parent
PLAN_PATH = HERE / "plan.json"
VIEWS = ("panel-primary", "panel-start")
FINGERS = ("left_finger_geom", "right_finger_geom")
SIGNS = np.array(tuple(itertools.product((0, 1), repeat=3)), dtype=bool)


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def write(path, payload):
    with path.open("x") as stream:
        json.dump(payload, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


def import_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def preflight():
    plan = read(PLAN_PATH)
    subprocess.run(["git", "merge-base", "--is-ancestor", plan["base"], "HEAD"], check=True)
    roots = plan["roots"]
    pinned = {}

    def verify(file, expected):
        require(file.is_file() and file.resolve().is_relative_to(Path.cwd()), f"escaping input {file}")
        require(sha(file) == expected, f"changed input {file}")
        pinned[str(file)] = expected

    for filename, expected in plan["sha256"].items():
        verify(Path(filename.format(**roots)), expected)
    historic = {}
    seen = 0
    for case, setup in plan["cases"].items():
        directory = Path(plan["context_root"].format(**roots) + case)
        for name, digest in zip(plan["case_input_order"], setup["context_sha256"], strict=True):
            verify(directory / name, digest)
        history = read(Path(roots["historic"]) / f"{case}.json")["rows"]
        historic[case] = history
        require(len(history) == setup["read_rows"], f"historical read count differs for {case}")
        instance = directory / "instance"
        index = {row["frame_id"]: row for row in read(instance / "pixel-index.json")["frames"]}
        frame_roles = read(instance / "run.json")["frame_roles"]
        wanted = {"GRASP/PRE", "GRASP/POST", "LIFT/PRE", "LIFT/feedback"}
        roles = [(r["label"], r["frame_id"]) for r in frame_roles if r["label"] in wanted]
        require(roles == [(r["phase"], r["frame"]) for r in history], f"frame roles changed for {case}")
        for row in history:
            data = index[row["frame"]]
            require(data["file_sha256"] == row["native_frame_sha256"]
                    and data["physics_step"] == row["step"], "exposure linkage")
            verify(instance / data["file"], data["file_sha256"])
        seen += len(history)
    require(seen == plan["limits"]["native_archived_reads"], "unplanned archived frames")
    return plan, pinned, historic


def corners(low, high):
    return np.where(SIGNS, high, low)


def coverage(points, camera, depth):
    """Record the original zero-contact-floor rectangle test and stricter validity."""
    tf = np.asarray(camera["camera_to_world"]).reshape(4, 4)
    local = (points - tf[:3, 3]) @ tf[:3, :3]
    z = local[:, 2]
    result = {"near_z_m": float(z.min()), "far_z_m": float(z.max()),
              "original": False, "valid_coverage": False}
    if z.min() <= 0:
        return result | {"reason": "behind_camera"}
    fx, fy, cx, cy = camera["intrinsics"]
    uv = local[:, :2] / z[:, None] * [fx, fy] + [cx, cy]
    low = np.floor(uv.min(axis=0) - 0.5).astype(int)
    high = np.ceil(uv.max(axis=0) + 0.5).astype(int)
    result["roi_xyxy"] = [*low.tolist(), *high.tolist()]
    if (low < 0).any() or (high >= depth.shape[::-1]).any():
        return result | {"reason": "outside_image"}
    roi = depth[low[1]:high[1]+1, low[0]:high[0]+1]
    valid = np.isfinite(roi) & (roi > 0)
    result["invalid_depth_pixels"] = int(np.count_nonzero(~valid))
    result["original"] = bool(roi.min() >= z.max())
    if not valid.all():
        return result | {"reason": "invalid_depth"}
    row, col = np.unravel_index(np.argmin(roi), roi.shape)
    margin = float(roi[row, col] - z.max())
    return result | {
        "min_depth_m": float(roi[row, col]),
        "min_xy": [int(low[0]+col), int(low[1]+row)],
        "margin_m": margin,
        "valid_coverage": margin >= 0,
        "reason": "covered" if margin >= 0 else "return_before_far_corner",
    }


def subdivisions(low, high):
    mid = (low + high) * 0.5
    require(np.all(low < mid) and np.all(mid < high), "degenerate envelope")
    for side in SIGNS:
        yield corners(np.where(side, mid, low), np.where(side, high, mid))


def audit_box(low, high, maps):
    children = list(subdivisions(low, high))
    return {
        name: {
            "whole": coverage(corners(low, high), *maps[name]),
            "children": [coverage(box, *maps[name]) for box in children],
        } for name in VIEWS
    }


def covered_view(audit):
    return next((name for name in VIEWS if all(child["valid_coverage"]
                for child in audit[name]["children"])), None)


def controls():
    cam = {"camera_to_world": np.eye(4).ravel(), "intrinsics": [50,50,32,32]}
    far = np.full((80, 80), 3.0)
    depth = far.copy()
    depth[:, 59:] = 1.6
    lo = np.array([0.5,-0.1,1.0])
    hi = np.array([0.65,0.1,2.0])

    def one_map(layer, low=lo, high=hi):
        return audit_box(low, high, {view:(cam, layer) for view in VIEWS})

    proof = one_map(depth)
    broken = {}
    for kind, value in (("no_return", 0), ("early_return", 0.9), ("infinite", np.inf)):
        bad = depth.copy()
        bad[32, 50] = value
        broken[kind] = covered_view(one_map(bad)) is None
    artificial = {name: {"children": [{"valid_coverage": (i < 4) == (idx == 0)}
                                      for i in range(8)]} for idx,name in enumerate(VIEWS)}
    answers = broken | {
        "full_cover": covered_view(one_map(far)) == "panel-primary",
        "separated_extrema": not proof["panel-primary"]["whole"]["original"]
        and covered_view(proof) == "panel-primary",
        "clipped_roi": covered_view(one_map(far, lo, np.array([4.0,0.1,2.0]))) is None,
        "no_mixed_view_proof": covered_view(artificial) is None,
    }
    require(all(answers.values()), "registered volume controls failed")
    return answers


def acquire(out):
    import cv2
    import mujoco
    from OpenGL import GL

    from cloud_edge_robot_arm.simulation.mujoco.camera import MuJoCoRGBDCamera
    from scripts.graduation import g1_complete_cv_clearance as gate
    from scripts.graduation.g1_visibility_trials import device

    require(mujoco.__version__ == "3.3.7", "expected native MuJoCo 3.3.7")
    plan, inputs, historic = preflight()
    roots = plan["roots"]
    source = Path(roots["rounds"]) / "round-g1-payload-clearance-20261125/payload-cold-frame-check.py"
    reader = import_file("sealed_frame_reader", source)
    marker = import_file("sealed_marker", Path(plan["registered_detector"].format(**roots)))
    reader.measure_frame = marker.measure_frame
    captured, renderers = {}, {}
    render_count = 0
    graphics = read(Path(roots["cv"]) / "calibration-gpu-01/manifest.json")["renderer"]

    class CountRobotProjection(gate.RobotDepthReference):
        def project(self, joints, fingers):
            nonlocal render_count
            require(render_count < plan["limits"]["robot_reference_depth_renders_max"], "render budget")
            render_count += 1
            predicted = super().project(joints, fingers)
            if not renderers:
                renderers.update({
                    "renderer": GL.glGetString(GL.GL_RENDERER).decode(),
                    "vendor": GL.glGetString(GL.GL_VENDOR).decode(),
                    "version": GL.glGetString(GL.GL_VERSION).decode(),
                })
                require(renderers == graphics, "unregistered robot depth renderer")
            return predicted

    class AuditReader(gate.LocalClearance):
        def check(self, frame, *args, **kwargs):
            if frame.frame_id not in captured:
                return super().check(frame, *args, **kwargs)
            payload = self.payload_gate.check
            original_code = payload.__func__.__code__

            def observe(stage, q, f, dq, df, handoff, observed, volume, **options):
                def record(box, pad):
                    accepted = volume(box, pad)
                    called = sys._getframe(1)
                    require(called.f_code is original_code, "unexpected body callback source")
                    state = called.f_locals
                    lo, hi = state["low"], state["high"]
                    row = {
                        "body": box.name, "low_m": lo.tolist(), "high_m": hi.tolist(),
                        "world_vertices_m": state["vertices"][state["j"]].tolist(),
                        "world_pad_m": state["pad"].tolist(), "callback_pad_m": pad.tolist(),
                        "original_callback": accepted,
                    }
                    if box.name in FINGERS:
                        require(np.all(pad == 0), "nonzero finger callback pad")
                        raw_points = box.corners()
                        row["query_corners_m"] = raw_points.tolist()
                        row["views_original"] = {name: coverage(raw_points, *self.maps[name]) for name in VIEWS}
                        require(accepted == any(v["original"] for v in row["views_original"].values()),
                                "finger projection disagrees with original predicate")
                    captured[frame.frame_id].append(row)
                    return accepted

                return payload(stage, q, f, dq, df, handoff, observed, record, **options)

            with patch.object(self.payload_gate, "check", observe):
                return super().check(frame, *args, **kwargs)

    def forbidden(*args, **kwargs):
        raise RuntimeError("registered readback forbids stepping or original camera exposure")

    cv2.setNumThreads(1)
    role_lock = Path("experiments/results/g1-visibility-pose-repair-20261124")
    with device(role_lock), patch.object(gate, "RobotDepthReference", CountRobotProjection), \
            patch.object(mujoco, "mj_step", forbidden), patch.object(mujoco, "mj_step1", forbidden), \
            patch.object(mujoco, "mj_step2", forbidden), patch.object(MuJoCoRGBDCamera, "_capture", forbidden):
        out.mkdir(exist_ok=False, parents=True)
        write(out / "registration.json", {"plan_sha256": sha(PLAN_PATH), "source_sha256": sha(Path(__file__)),
                                           "inputs_sha256": inputs, "version": mujoco.__version__})
        reader.LocalClearance = AuditReader
        for case, setup in plan["cases"].items():
            captured[setup["frame"]] = []
            reader.run(case, out)
            rows = read(out / f"{case}.json")["rows"]
            keys = ("step", "frame", "phase", "native_frame_sha256")
            require([tuple(row[k] for k in keys) for row in rows] ==
                    [tuple(row[k] for k in keys) for row in historic[case]], "wrong resulting role sequence")
        write(out / "enclosures.json", {"by_frame": captured, "robot_only_renders": render_count,
                                        "graphics": renderers, "new_camera_exposures": 0, "steps": 0})
    write(out / "sealed.json", {name: sha(out / name)
                                for name in ("registration.json", "t01.json", "t02.json", "enclosures.json")})


def cpu(out, result_path):
    registered, _, historic = preflight()
    seal = read(out / "sealed.json")
    require(set(seal) == {"registration.json", "t01.json", "t02.json", "enclosures.json"}, "bad seal")
    for name, expected in seal.items():
        require(sha(out / name) == expected, f"invalid evidence seal {name}")
    enclosures = read(out / "enclosures.json")
    report = {"seal_sha256": sha(out / "sealed.json"), "robot_only_renders": enclosures["robot_only_renders"],
              "new_rgbd": 0, "new_integration_steps": 0, "controls": controls(), "cases": {}}
    for case, pick in registered["cases"].items():
        rows = read(out / f"{case}.json")["rows"]
        row = next(r for r in rows if r["frame"] == pick["frame"])
        old = next(r for r in historic[case] if r["frame"] == pick["frame"])
        now, prior = row["current"], old["current"]
        motion = now.get("short_motion", {})
        report["cases"][case] = {
            "rows": len(rows), "frame": pick["frame"], "step": pick["target_step"], "status": now["status"],
            "reason": now["reason"], "historic_reason": prior["reason"], "short_motion": motion,
            "held": now.get("payload_observation", {}).get("relation"),
            "pose_method": (now.get("payload_observation", {}).get("pose") or {}).get("method"),
            "unmatched_near_pixels": now.get("depth", {}).get("unmatched_pixels_uv", []),
            "visited_bodies": [r["body"] for r in enclosures["by_frame"][pick["frame"]]],
        }
    t01, t02 = (report["cases"][case] for case in ("t01", "t02"))
    matched = (
        t01["status"] == "UNKNOWN" and t01["reason"] == "payload_horizon_outside_registered_volume"
        and t01["held"] == "held" and t01["pose_method"] == "id8_opposite_edges"
        and t01["short_motion"].get("limiting_body") == "left_finger_geom"
        and all(abs(t01["short_motion"]["finger_table_lower_m"][side] -
                    historic["t01"][-1]["current"]["short_motion"]["finger_table_lower_m"][side]) <= 1e-9
                for side in FINGERS)
        and t02["status"] == "BLOCKED" and t02["reason"] == "unregistered_near_surface"
        and [171,122] in t02["unmatched_near_pixels"] and not t02["visited_bodies"]
    )
    report["baseline_reproduced"] = matched
    if matched:
        calibration = Path(registered["roots"]["cv"]) / "calibration-gpu-01"
        manifest = read(calibration / "manifest.json")
        maps = {name:(manifest["maps"][name]["camera"], np.load(calibration / manifest["maps"][name]["depth_file"],
                                                        allow_pickle=False)) for name in VIEWS}
        row = next(r for r in enclosures["by_frame"][t01["frame"]] if r["body"] == "left_finger_geom")
        require(not row["original_callback"], "expected original left finger volume veto")
        proof = audit_box(np.asarray(row["low_m"]), np.asarray(row["high_m"]), maps)
        report["candidate"] = {"body": row["body"], "covered_view": covered_view(proof), "views": proof,
                               "low_m": row["low_m"], "high_m": row["high_m"]}
    write(result_path, report)
    return 0 if matched else 2


if __name__ == "__main__":
    os.umask(0o077)
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("mode", choices=("preflight", "acquire", "read"))
    cli.add_argument("output", type=Path, nargs="?")
    cli.add_argument("result", type=Path, nargs="?")
    args = cli.parse_args()
    if args.mode == "preflight":
        _, hashes, _ = preflight()
        print(len(hashes), "verified inputs and", len(controls()), "CPU controls")
    elif args.mode == "acquire":
        acquire(args.output)
    else:
        raise SystemExit(cpu(args.output, args.result))
