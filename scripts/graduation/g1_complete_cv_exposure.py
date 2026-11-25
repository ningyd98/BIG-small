"""Compare the optical FK reference with archived RGB-D using native command replay."""

import argparse
import gzip
import json
from pathlib import Path

from scripts.graduation.g1_clearance_mount_replay_brake import initialize
from scripts.graduation.g1_complete_cv_calibrate import axial, digest, write
from scripts.graduation.g1_complete_cv_clearance import LocalClearance, camera_encoder_pose
from scripts.graduation.g1_visibility_trials import device
from scripts.graduation.g1_visibility_vision import measure_frame

from cloud_edge_robot_arm.simulation.models import JointCommand
from cloud_edge_robot_arm.simulation.mujoco.skill_robot import _DOWNWARD
from cloud_edge_robot_arm.vision.observations import RGBDObservation


def read(path):
    return json.loads(path.read_bytes())


def run(private, compiled, cal, batch):
    geometry = json.loads(gzip.decompress(compiled.read_bytes()))["geometry"]
    xml = Path(geometry["asset_path"])
    rr = {}
    with device(Path("experiments/results/g1-visibility-pose-repair-20261124")):
        for sub in sorted(batch.glob("*/instance")):
            ev = read(sub / "local-clearance.json")
            index = read(sub / "pixel-index.json")["frames"]
            states = read(sub / "offline-truth.json")["samples"]
            commands = {}
            for cmd in read(sub / "backend-commands.json"):
                commands.setdefault(cmd["physics_step"], []).append(cmd)
            b = initialize(xml, states[0])
            monitor = LocalClearance(
                geometry,
                xml,
                cal,
                calibration_sha256=digest(cal / "manifest.json"),
                isolated_scene=True,
            )
            rows = []
            try:
                for rec in ev["rows"]:
                    st = rec["physics_step"]
                    while b.total_physics_steps < st:
                        for op in commands.get(b.total_physics_steps, []):
                            if not op["accepted"]:
                                continue
                            if op["type"] == "joint_target":
                                b.apply_joint_targets(
                                    JointCommand(positions=op["target_positions_rad"])
                                )
                            elif op["type"] == "hold_current_joints":
                                b.hold_current_joints()
                            else:
                                raise ValueError("unexpected command in camera replay")
                        b.step()
                    m = rec["robot"]
                    r = camera_encoder_pose(b._model, b._data)
                    original = next(x for x in index if x["frame_id"] == rec["frame_id"])
                    f = RGBDObservation.model_validate_json((sub / original["file"]).read_bytes())
                    marker = measure_frame(f, geometry)
                    replay_res = float(abs(b._data.qpos[:7] - m["joint_positions_rad"]).max())
                    if replay_res > 1e-9 or abs(b.get_sim_time() - f.sim_time_s) > 1e-12:
                        raise ValueError("source encoder state not reproduced")
                    s = monitor.check(
                        f, marker, dict(m, **r), rec["skill"], rec.get("target_xyz"), _DOWNWARD
                    )
                    unknown = rec["evidence"].get("depth", {}).get("unmatched_pixels_uv", [])
                    matches = []
                    if unknown and monitor.robot_raster is not None:
                        reference = monitor.robot_raster
                        physical = reference.project(
                            r["camera_joint_positions_rad"], r["camera_finger_positions_m"]
                        )
                        for u, v in unknown:
                            matches.append(
                                dict(
                                    uv=[u, v],
                                    raw=float(axial(f)[v, u]),
                                    prediction=float(physical[v, u]),
                                )
                            )
                    rows.append(
                        dict(
                            step=st,
                            phase=rec["phase"],
                            q_replay_max_rad=replay_res,
                            optical_encoders=r,
                            source_result=rec["status"],
                            outcome=s,
                            old_pixels=matches,
                        )
                    )
            finally:
                monitor.close()
                b.shutdown()
            rr[sub.parent.name] = rows
    return rr


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for item in ("private", "compiled", "cal", "batch", "out"):
        p.add_argument("--" + item, type=Path, required=True)
    args = p.parse_args()
    result = run(args.private, args.compiled, args.cal, args.batch)
    write(args.out, result)
    for k, v in result.items():
        print(k, v[-1]["source_result"], v[-1]["outcome"]["status"], v[-1]["old_pixels"])
