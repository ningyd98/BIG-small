"""Offline-only scene application, settling and simulator truth capability."""

from __future__ import annotations

import base64
import hashlib
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np

from cloud_edge_robot_arm.datasets.rgbd.models import SceneSpec
from cloud_edge_robot_arm.datasets.rgbd.scene_sampler import COLORS
from cloud_edge_robot_arm.simulation.mujoco.backend import GRIPPER_OPEN_TARGET_M
from cloud_edge_robot_arm.vision.capture import CapturedFrame, MuJoCoCaptureSession
from cloud_edge_robot_arm.vision.observations import RGBDObservation


def _validate_parameters(params: dict[str, Any]) -> None:
    expected = {"target", "distractors", "destination", "camera", "light_intensity",
                "depth_noise_m", "invalid_depth_fraction"}
    if set(params) != expected or len(params["distractors"]) > 3:
        raise ValueError("unsupported scene parameters")
    objects = [params["target"], *params["distractors"]]
    for obj in [*objects, params["destination"]]:
        expected_keys = {"position", "half_size", "rgba"}
        if obj is not params["destination"]:
            expected_keys |= {"color_name", "mass_kg", "friction"}
        if set(obj) != expected_keys:
            raise ValueError("unsupported object parameters")
        for key, length in (("position", 3), ("half_size", 3), ("rgba", 4)):
            values = np.asarray(obj[key], dtype=float)
            if values.shape != (length,) or not np.isfinite(values).all():
                raise ValueError(f"invalid {key} parameters")
        x, y, z = obj["position"]
        hx, hy, hz = obj["half_size"]
        if (min(hx, hy, hz) <= 0 or max(hx, hy, hz) > .15 or
                not -.30 <= x - hx < x + hx <= 1.0 or
                not -.45 <= y - hy < y + hy <= .45 or not hz <= z <= .5):
            raise ValueError("object outside supported table bounds")
        if not all(0 <= c <= 1 for c in obj["rgba"]):
            raise ValueError("invalid RGBA parameters")
    for obj in objects:
        if obj["color_name"] not in {"red", "blue", "yellow"}:
            raise ValueError("unsupported color parameters")
        if not np.allclose(obj["rgba"], COLORS[obj["color_name"]], atol=1e-6):
            raise ValueError("color name must agree with the rendered palette")
        if not 0 < obj["mass_kg"] <= 1 or not 0 < obj["friction"] <= 5:
            raise ValueError("invalid mass/friction parameters")
    camera = params["camera"]
    if set(camera) != {"position", "quaternion", "fovy"}:
        raise ValueError("unsupported camera parameters")
    pos = np.asarray(camera["position"], dtype=float)
    quat = np.asarray(camera["quaternion"], dtype=float)
    if (pos.shape != (3,) or not np.isfinite(pos).all() or not .5 <= pos[2] <= 3 or
            quat.shape != (4,) or not np.isfinite(quat).all() or
            not np.isclose(np.linalg.norm(quat), 1) or not 1 < camera["fovy"] < 179):
        raise ValueError("invalid camera parameters")
    if not 0 <= params["light_intensity"] <= 1:
        raise ValueError("invalid light parameters")
    if not 0 <= params["depth_noise_m"] <= .1 or not 0 <= params["invalid_depth_fraction"] <= 1:
        raise ValueError("invalid depth perturbation parameters")


def _prepare(session: MuJoCoCaptureSession) -> None:
    """Add reusable free-body slots once; all subsequent scenes share this model/renderer."""
    tree = ET.fromstring(Path(session._config.model_path).read_text(encoding="utf-8"))
    world = tree.find("worldbody")
    if world is None:
        raise ValueError("dataset MJCF requires a worldbody")
    for index in range(3):
        body = ET.SubElement(world, "body", name=f"dataset_distractor_{index}",
                             pos=f"{index} 0 -5", gravcomp="1")
        ET.SubElement(body, "freejoint", name=f"dataset_distractor_{index}_free")
        ET.SubElement(body, "geom", name=f"dataset_distractor_{index}_geom", type="box",
                      size="0.045 0.045 0.045", mass="0.08", contype="1", conaffinity="1",
                      rgba="0 0 0 0")
    backend = session._backend
    backend.shutdown()
    backend.initialize(session._config, model_xml=ET.tostring(tree, encoding="unicode"))
    session._dataset_prepared = True


def apply_scene(session: MuJoCoCaptureSession, scene: SceneSpec) -> None:
    params = scene.scene_parameters
    _validate_parameters(params)
    asset_hash = hashlib.sha256(Path(session._config.model_path).read_bytes()).hexdigest()
    if scene.asset_family_hash != asset_hash:
        raise ValueError("scene asset family does not match capture model")
    if not session._dataset_prepared:
        _prepare(session)
    backend = session._backend
    mj, model, data = backend._mujoco, backend._model, backend._data
    assert mj is not None and model is not None and data is not None

    def set_geometry(name: str, obj: dict[str, Any]) -> None:
        geom = model.geom(name)
        size = np.asarray(obj["half_size"])
        geom.size[:] = size
        geom.rgba[:] = obj["rgba"]
        model.geom_rbound[geom.id] = np.linalg.norm(size)
        model.geom_aabb[geom.id] = [0, 0, 0, *size]
        # Each dataset movable body has one centered box. Refresh its collision BVH leaf.
        nodes = np.flatnonzero(model.bvh_nodeid == geom.id)
        for node in nodes:
            model.bvh_aabb[node] = [0, 0, 0, *size]
        if "mass_kg" in obj:
            mass = obj["mass_kg"]
            body_id = int(model.geom_bodyid[geom.id])
            model.body_mass[body_id] = mass
            model.body_inertia[body_id] = mass / 3 * (np.sum(size ** 2) - size ** 2)
            geom.friction[:] = [obj["friction"], .01, .001]

    set_geometry("object_geom", params["target"])
    set_geometry("target_region_geom", params["destination"])
    model.body("target_region").pos[:] = params["destination"]["position"]
    for index in range(3):
        body = model.body(f"dataset_distractor_{index}")
        geom = model.geom(f"dataset_distractor_{index}_geom")
        active = index < len(params["distractors"])
        # Keep compiled body collision masks/BVH valid; unused slots remain below the table.
        model.body_gravcomp[body.id] = 0 if active else 1
        if active:
            set_geometry(f"dataset_distractor_{index}_geom", params["distractors"][index])
        else:
            geom.rgba[:] = [0, 0, 0, 0]
    camera = model.camera("rgbd")
    camera.pos[:] = params["camera"]["position"]
    camera.quat[:] = params["camera"]["quaternion"]
    camera.fovy[:] = params["camera"]["fovy"]
    model.light("rgbd_light").diffuse[:] = params["light_intensity"]
    mj.mj_setConst(model, data)
    mj.mj_resetData(model, data)
    data.qpos[model.joint("joint1").qposadr[0]] = -.8
    backend._target_positions = np.zeros(7)
    backend._target_positions[0] = -.8
    backend._estop_engaged = False
    backend._gripper_open = True
    for finger_name in ("finger_left_joint", "finger_right_joint"):
        finger_id = model.joint(finger_name).id
        data.qpos[model.jnt_qposadr[finger_id]] = 0.04
    data.ctrl[7:9] = GRIPPER_OPEN_TARGET_M
    backend._pending_joint_targets = []
    backend._total_physics_steps = 0
    backend._episode_id = uuid4().hex
    # Capture reads only identity from this scenario; scene geometry was applied above.
    from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig

    backend._scenario = replace(
        PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=scene.seed),
        scenario_id=scene.group_id)
    backend._rng = np.random.default_rng(scene.seed)
    backend._sensor_noise_std_m = 0.0  # Preserve a clean raw frame before offline perturbations.
    for name, obj in [("object", params["target"]), *[
            (f"dataset_distractor_{i}", obj) for i, obj in enumerate(params["distractors"])]]:
        body = model.body(name)
        adr = model.jnt_qposadr[model.body_jntadr[body.id]]
        data.qpos[adr:adr + 3] = obj["position"]
        data.qpos[adr + 3:adr + 7] = [1, 0, 0, 0]
    mj.mj_forward(model, data)
    session._dataset_scene = scene
    session._dataset_settled = False


class OfflineSceneAdapter:
    """Separate ground-truth capability unavailable on the online RGBDObservation type."""

    def __init__(self, session: MuJoCoCaptureSession, *, settle_steps: int = 120) -> None:
        if not 0 <= settle_steps <= 10000:
            raise ValueError("settle_steps outside bounded budget")
        self.session = session
        self.settle_steps = settle_steps

    def capture_ground_truth(self) -> dict[str, Any]:
        session = self.session
        scene = session._dataset_scene
        if not session._open or scene is None:
            raise RuntimeError("apply an offline scene before requesting ground truth")
        backend = session._backend
        model, data = backend._model, backend._data
        assert model is not None and data is not None
        params = scene.scene_parameters
        objects = [(1, "target", "object", "object_geom"), *[
            (i + 2, "distractor", f"dataset_distractor_{i}", f"dataset_distractor_{i}_geom")
            for i in range(len(params["distractors"]))],
            (5, "destination", "target_region", "target_region_geom")]
        instances = []
        speeds = []
        angular_speeds = []
        for semantic_id, role, body_name, geom_name in objects:
            body, geom = model.body(body_name), model.geom(geom_name)
            pos = data.geom_xpos[geom.id]
            size = geom.size
            if role != "destination":
                joint = model.body_jntadr[body.id]
                dof = model.jnt_dofadr[joint]
                speeds.append(float(np.linalg.norm(data.qvel[dof:dof + 3])))
                angular_speeds.append(float(np.linalg.norm(data.qvel[dof + 3:dof + 6])))
                extents = np.abs(data.geom_xmat[geom.id].reshape(3, 3)) @ size
                if (abs(pos[2] - extents[2]) > .002 or
                        not -.30 <= pos[0] - extents[0] < pos[0] + extents[0] <= 1 or
                        not -.45 <= pos[1] - extents[1] < pos[1] + extents[1] <= .45):
                    raise ValueError("object is not settled on table or outside table bounds")
            instances.append({"semantic_id": semantic_id, "role": role, "geom_ids": [geom.id],
                              "position": pos.tolist(), "half_size": size.tolist()})
        max_speed = max(speeds, default=0.)
        max_angular_speed = max(angular_speeds, default=0.)
        penetration = max((max(0., -float(c.dist)) for c in data.contact[:data.ncon]), default=0.)
        if max_speed > .02 or max_angular_speed > .1 or penetration > .002:
            raise ValueError("scene is not settled or has excessive penetration")
        return {"instances": instances, "target_color_name": params["target"]["color_name"],
                "settling": {"steps": self.settle_steps, "sim_time_s": float(data.time),
                             "max_linear_speed_m_s": max_speed,
                             "max_angular_speed_rad_s": max_angular_speed,
                             "max_penetration_m": penetration}}

    def capture(self) -> tuple[CapturedFrame, dict[str, Any]]:
        session = self.session
        if not session._open or session._dataset_scene is None:
            raise RuntimeError("apply an offline scene before capture")
        if not session._dataset_settled:
            if self.settle_steps:
                session._backend.step(self.settle_steps)
            session._dataset_settled = True
        truth = self.capture_ground_truth()
        raw = session.capture_with_instances()
        params = session._dataset_scene.scene_parameters
        noise, invalid = params["depth_noise_m"], params["invalid_depth_fraction"]
        if not noise and not invalid:
            return raw, truth
        observation = raw.observation
        depths = np.frombuffer(base64.b64decode(observation.depth_float32_base64),
                               dtype="<f4").copy()
        valid = depths > 0
        rng = np.random.default_rng(session._dataset_scene.seed ^ 0xD3E7)
        if noise:
            depths[valid] += rng.normal(0, noise, int(valid.sum())).astype("<f4")
        depths[~valid | (depths <= 0) | (rng.random(len(depths)) < invalid)] = 0
        values = observation.model_dump()
        mask = (depths > 0).astype("u1").tobytes()
        values.update(depth_float32_base64=base64.b64encode(depths.tobytes()).decode(),
                      valid_mask_base64=base64.b64encode(mask).decode(),
                      checksum_sha256="")
        frame = replace(raw, observation=RGBDObservation.model_validate(values))
        truth["_raw_captured_frame"] = raw
        return frame, truth
