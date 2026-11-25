"""Zero-step native RGB-D fixtures for print, photometry and destination identity controls."""

import argparse
import copy
import fcntl
import gzip
import json
import time
from pathlib import Path
from xml.etree import ElementTree as ET

import cv2
import mujoco
import numpy as np
from OpenGL import GL
from scripts.graduation import g1_dual_asset as asset
from scripts.graduation.dynamic_vision import plain
from scripts.graduation.g1_clearance_mount_optics import restore_observed_state, set_known_cube
from scripts.graduation.g1_clearance_mount_physics import (
    CENTER,
    ROOT,
    digest,
    set_diagnostic_arm,
    write,
)
from scripts.graduation.g1_dual_observer import measure_frame

from cloud_edge_robot_arm.contracts import Pose
from cloud_edge_robot_arm.research.native_collection_grounding import bootstrap_collection_tracker
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot
from cloud_edge_robot_arm.vision.observations import observation_from_sensor_frame
from cloud_edge_robot_arm.vision.servo_region import measure_servo_region

SEVEN = (
    "reset",
    "open-near",
    "bilateral-closed",
    "lift-with-hold",
    "over-region-held",
    "at-region-release-height",
    "at-region-retracted",
)
CASES = {
    "photometry": ["matte-beams", "smaller-print"],
    "qualification": [
        "original",
        "foreign-in-seven",
        "foreign-in-eight",
        "additional-foreign",
        "shifted-region",
        "raised-green-decoy",
        "wrong-region-patch",
        "dark-region",
    ],
    "calibrate": ["original", "soft-illumination", "dim-illumination"],
    "stress": ["shifted-small-foreign", "shifted-large-foreign", "shifted-print-on-wing"],
}


def attrs(vec):
    return " ".join(map(str, vec))


def make_fixture(case, path):
    root = ET.parse(ROOT / asset.ASSET_PATH).getroot()
    obj = root.find("./worldbody/body[@name='object']")
    world = root.find("./worldbody")
    bits = cv2.aruco.generateImageMarker(
        cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50), 17, 6
    )
    if case in ("additional-foreign", "shifted-small-foreign", "shifted-large-foreign"):
        center = {
            "additional-foreign": ".48 .25 .017",
            "shifted-small-foreign": ".55 .20 .019",
            "shifted-large-foreign": ".36 -.24 .019",
        }[case]
        scale = {
            "additional-foreign": 1.0,
            "shifted-small-foreign": 0.80,
            "shifted-large-foreign": 1.30,
        }[case]
        board = ET.SubElement(world, "body", name="diagnostic_foreign", pos=center)
        ET.SubElement(
            board,
            "geom",
            name="diagnostic_foreign_board",
            type="box",
            size=attrs([0.05 * scale, 0.05 * scale, 0.003]),
            rgba=".5 .5 .5 1",
            contype="1",
            conaffinity="3",
        )
        for geom in list(obj):
            if not geom.get("name", "").startswith("g1_dual_id8_"):
                continue
            suffix = geom.get("name")[12:]
            if suffix not in ("quiet",) and not suffix.startswith("r"):
                continue
            new = copy.deepcopy(geom)
            new.set("name", "diagnostic_" + suffix)
            pos = np.fromstring(geom.get("pos"), sep=" ")
            pos -= [0.130, 0.0, 0.032]
            pos[:2] *= scale
            size = np.fromstring(geom.get("size"), sep=" ")
            size[:2] *= scale
            new.set("pos", attrs(pos))
            new.set("size", attrs(size))
            if suffix.startswith("r"):
                r, c = int(suffix[1]), int(suffix[-1])
                new.set("rgba", ".98 .98 .98 1" if bits[r, c] else ".01 .01 .01 1")
            board.append(new)
    if case in ("wrong-region-patch", "raised-green-decoy"):
        layer = ET.SubElement(world, "body", name="diagnostic_patch", pos="2 2 .005")
        if case == "raised-green-decoy":
            ET.SubElement(layer, "geom", type="box", size=".08 .08 .002", rgba=".1 .6 .2 .4")
        else:
            ET.SubElement(layer, "geom", type="box", size=".016 .016 .0001", rgba=".55 .2 .5 1")
    for code, x in ((7, -0.130), (8, 0.130)):
        for geom in list(obj):
            prefix = f"g1_dual_id{code}_"
            name = geom.get("name", "")
            if not name.startswith(prefix):
                continue
            suffix = name.removeprefix(prefix)
            if case == "matte-beams" and suffix in ("crossbar", "upright"):
                geom.set("rgba", ".18 .18 .18 1")
            if suffix.startswith("r"):
                r, c = int(suffix[1]), int(suffix[-1])
                if case == ("foreign-in-seven" if code == 7 else "foreign-in-eight"):
                    geom.set("rgba", ".98 .98 .98 1" if bits[r, c] else ".01 .01 .01 1")
                if case == "smaller-print":
                    pos = np.fromstring(geom.get("pos"), sep=" ")
                    size = np.fromstring(geom.get("size"), sep=" ")
                    pos[:2] = np.array([x, 0]) + 0.90 * (pos[:2] - [x, 0])
                    size[:2] *= 0.90
                    geom.set("pos", attrs(pos))
                    geom.set("size", attrs(size))
                if case == "shifted-print-on-wing" and code == 8:
                    pos = np.fromstring(geom.get("pos"), sep=" ")
                    pos[0] += 0.012
                    geom.set("pos", attrs(pos))
    if case in ("soft-illumination", "dim-illumination"):
        light = root.find("./worldbody/light")
        light.set("diffuse", ".52 .52 .52" if case == "soft-illumination" else ".30 .30 .30")
    path.write_bytes(ET.tostring(root, encoding="utf-8"))


def setup_pose(role, backend, robot, data):
    close = next(i for i, r in enumerate(data) if r["phase"] == "GRASP")
    lift = next(i for i, r in enumerate(data) if r["phase"] == "LIFT")
    states = {
        "open-near": data[close - 1],
        "bilateral-closed": data[lift - 1],
        "lift-with-hold": data[-1],
    }
    if role in states:
        restore_observed_state(backend, states[role])
    if role in SEVEN[4:]:
        z = 0.15 if role == "over-region-held" else 0.035
        set_known_cube(backend._model, backend._data, (0.2, 0.25, z), np.eye(3))
        retracted = role == "at-region-retracted"
        set_diagnostic_arm(
            backend,
            robot,
            (0.2, 0.25, 0.16 if retracted else z + 0.01),
            (0.04, 0.04) if retracted else data[lift - 1]["finger_joints_m"],
        )


def read_frame(backend):
    return observation_from_sensor_frame(
        backend.capture_sensor_frame(), source="mujoco_camera", png_compress_level=1
    )


def capture(case, role, path, source, data, geometry):
    backend = MuJoCoPhysicsBackend()
    try:
        backend.initialize(
            SimulatorConfig(
                model_path=str(source),
                seed=4361,
                physics_dt_s=1 / 240,
                domain_randomization=False,
                render_rgb=True,
                render_depth=True,
            )
        )
        backend.reset(
            PhysicalScenarioConfig(
                scenario_id="S01_NORMAL_STATIC",
                seed=4361,
                object_mass_kg=asset.BODY_MASS_KG,
                object_pose=Pose(x=CENTER[0], y=CENTER[1], z=CENTER[2]),
            )
        )
        reference = observation_from_sensor_frame(
            backend.get_sensor_frame(), source="mujoco_camera"
        )
        try:
            tracker, _ = bootstrap_collection_tracker(reference, geometry)
            bootstrap_reason = None
        except ValueError as exc:
            tracker, bootstrap_reason = None, str(exc)
        model = backend._model
        setup_pose(role, backend, MuJoCoSkillRobot(backend), data)
        if case == "shifted-region":
            model.body("target_region").pos[:2] += [0.12, -0.08]
        if case == "raised-green-decoy":
            model.body("target_region").pos[:2] = [2.0, 2.0]
            model.body("diagnostic_patch").pos[:] = [0.2, 0.25, 0.026]
        if case == "wrong-region-patch":
            model.body("diagnostic_patch").pos[:] = [0.198, 0.268, 0.00415]
        if case == "dark-region":
            model.geom("target_region_geom").rgba[:3] *= 0.72
        mujoco.mj_forward(model, backend._data)
        start = time.perf_counter_ns()
        frame = read_frame(backend)
        measured = measure_frame(frame, geometry)
        region, reason = (
            measure_servo_region(frame, tracker)
            if tracker is not None
            else (None, bootstrap_reason)
        )
        component_ms = (time.perf_counter_ns() - start) / 1e6
        expected_center = backend._data.geom("object_geom").xpos
        expected_tcp = expected_center + backend._data.geom("object_geom").xmat.reshape(3, 3) @ [
            0.0,
            0.0,
            0.010,
        ]
        tcp = (
            np.array([measured["grasp_world_m"][k] for k in "xyz"])
            if isinstance(measured["grasp_world_m"], dict)
            else measured["grasp_world_m"]
        )
        write(path / (role + ".bootstrap.json.gz"), reference.model_dump(mode="json"))
        write(path / (role + ".rgbd.json.gz"), frame.model_dump(mode="json"))
        return dict(
            role=role,
            measured_ids=measured["observed_ids"],
            selected=measured["selected_id"],
            marker_reason=measured["reason"],
            usable=measured["usable"],
            raw_sha256=digest(path / (role + ".rgbd.json.gz")),
            destination_ok=region is not None,
            destination_reason=reason,
            region=plain(
                {
                    k: v
                    for k, v in region.items()
                    if k
                    in (
                        "center",
                        "source",
                        "observed_corner_anchors",
                        "current_coplanar_shaded_pixels",
                    )
                }
            )
            if region
            else None,
            bootstrap_reason=bootstrap_reason,
            marker_tcp_error_mm=1000 * float(np.linalg.norm(np.asarray(tcp) - expected_tcp))
            if tcp is not None
            else None,
            geometry_diagnostics=measured.get("rejected_nonphysical_grids", []),
            camera_and_both_estimators_ms=component_ms,
            renderer=GL.glGetString(GL.GL_RENDERER).decode(),
            actual_physics_steps=backend.total_physics_steps,
        )
    finally:
        backend.shutdown()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=CASES)
    parser.add_argument("out", type=Path)
    parser.add_argument("controls", type=Path)
    parser.add_argument("egl_lock", type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    controls = json.loads(gzip.decompress(args.controls.read_bytes()))
    result = {}
    geometry = asset.geometry_descriptor()
    with args.egl_lock.open("rb") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for name in CASES[args.mode]:
            path = args.out / name
            path.mkdir()
            source = path / "scene.xml"
            make_fixture(name, source)
            roles = SEVEN if name in ("original", "matte-beams", "smaller-print") else ("reset",)
            rows = [capture(name, role, path, source, controls, geometry) for role in roles]
            result[name] = dict(scene_sha256=digest(source), rows=rows)
            print(name, [(r["role"], r["selected"], r["destination_ok"]) for r in rows], flush=True)
    write(args.out / "summary.json", result)


if __name__ == "__main__":
    main()
