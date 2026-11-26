"""One development scene on the real B0 compile/reset/settle recipe."""

import argparse
import fcntl
import hashlib
import json
import os
from dataclasses import asdict
from pathlib import Path
from time import monotonic_ns
from unittest.mock import patch

import mujoco
import yaml
from OpenGL import GL
from scripts.run_rgbd_pilot import _ced_pools, _frozen_development_exclusions

from cloud_edge_robot_arm.datasets.rgbd.models import DatasetConfig, SceneSpec, content_digest
from cloud_edge_robot_arm.datasets.rgbd.scene_sampler import sample_scene
from cloud_edge_robot_arm.research.pilot_worker import compile_pilot_scene
from cloud_edge_robot_arm.research.protocol import read_excluded_groups
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
from cloud_edge_robot_arm.simulation.mujoco.camera import MuJoCoRGBDCamera
from cloud_edge_robot_arm.vision.capture import (
    MuJoCoCaptureSession,
    observation_from_sensor_frame,
    save_captured_frame,
    save_observation,
)
from cloud_edge_robot_arm.vision.top_grasp import CURRENT_GRASP_PROFILE, matches_calibrated_gripper

HERE = Path(__file__).resolve().parent
ROOT = next(path for path in HERE.parents if (path / ".git").is_file())
PLAN_PATH = HERE / "plan.json"
PLAN = json.loads(PLAN_PATH.read_bytes())
LOCK = ROOT / "experiments/results/g1-visibility-pose-repair-20261124/egl.lock"


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def write(path, value):
    with path.open("x", encoding="utf-8") as f:
        json.dump(value, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")


def verify_sources():
    require(Path.cwd() == ROOT, "run from the frozen project root")
    for name, expected in PLAN["source_sha256"].items():
        require(sha(ROOT / name) == expected, f"changed application source: {name}")
    require(sha(ROOT / PLAN["pool"]) == PLAN["pool_sha256"], "original pool drift")
    require(sha(ROOT / PLAN["config"]) == PLAN["config_sha256"], "original config drift")


def simulator(seed):
    return SimulatorConfig(
        render_rgb=True,
        render_depth=True,
        camera_width=320,
        camera_height=240,
        domain_randomization=False,
        seed=seed,
    )


def old_scene(row):
    base = row.get("base_assignment", row)
    raw = base["scene"]
    scene = SceneSpec.model_validate(raw)
    require(
        base.get("scene_hash") == scene.scene_hash
        and ("scene_hash" not in row or row["scene_hash"] == scene.scene_hash),
        f"changed source scene: {base.get('assignment_id')}",
    )
    return scene


def scenario_json(scenario):
    return asdict(scenario) | {
        "object_pose": scenario.object_pose.model_dump(mode="json"),
        "target_region_pose": scenario.target_region_pose.model_dump(mode="json"),
    }


def register(output):
    verify_sources()
    settings = yaml.safe_load((ROOT / PLAN["config"]).read_bytes())
    pools = _ced_pools(settings)
    require(pools == read(ROOT / PLAN["pool"]), "worker did not load all six original pools")
    previous = [old_scene(row) for rows in pools.values() for row in rows]
    already_used = _frozen_development_exclusions()
    already_used.update(read_excluded_groups([Path(name) for name in settings["exclude_datasets"]]))
    for dirname in settings["exclude_pilots"]:
        rows = read(Path(dirname) / "assignments.json")
        for row in rows["assignments"] if isinstance(rows, dict) else rows:
            prior = row.get("base_assignment", row)
            scene = prior.get("scene")
            if isinstance(scene, dict):
                previous.append(old_scene(row))
            else:
                already_used.add(prior["group_id"])
    groups = already_used | {x.group_id for x in previous}
    hashes = {x.scene_hash for x in previous}
    seeds = {x.seed for x in previous}
    start = PLAN["seed_start"]
    # Exact non-OOD sampler settings from the pinned CED v2 pool builder.
    distribution = DatasetConfig(
        dataset_id="research-pools",
        groups=sum(map(len, pools.values())),
        seed=start,
        target_x=(0.34, 0.43),
        target_y=(-0.07, 0.08),
        half_size=(0.032, 0.037),
        camera_height=(1.4, 1.4),
        camera_x=(0.35, 0.35),
        camera_y=(0.0, 0.0),
        camera_fovy=(45.0, 45.0),
        distractor_count=(0, 0),
        depth_noise_m=(0.0,),
        invalid_depth_fractions=(0.0,),
    )
    skipped = []
    for seed in range(start, start + len(groups) + len(seeds) + 1):
        candidate = sample_scene(distribution, seed)
        collisions = [
            key
            for key, occupied in (
                ("seed", candidate.seed in seeds),
                ("group", candidate.group_id in groups),
                ("scene_hash", candidate.scene_hash in hashes),
            )
            if occupied
        ]
        if not collisions:
            break
        skipped.append({"seed": seed, "collisions": collisions})
    else:
        raise ValueError("no disjoint scene at registered starting seed")
    model, scenario = compile_pilot_scene(candidate, simulator(seed))
    color = candidate.scene_parameters["target"]["color_name"]
    public_input = f"Move the {color} block to the green region."
    failed_xml = ROOT / "cache/research/raw/20261126-b0-static-worker-support-window/compiled.xml"
    require(
        sha(failed_xml) == "342162ee62dd4fbaccf30ee659f3287d5d834465c7487a20101aeb2e3b1500f0"
        and model.encode() == failed_xml.read_bytes(),
        "candidate changed from the original compile",
    )
    registration = {
        "plan_sha256": sha(PLAN_PATH),
        "script_sha256": sha(Path(__file__)),
        "scope": PLAN["development_label"],
        "skipped": skipped,
        "scene": candidate.model_dump(mode="json"),
        "instruction": public_input,
        "target_color": color,
        "scenario": scenario_json(scenario),
        "compiled_xml_sha256": sha(failed_xml),
        "exclusion_groups_sha256": content_digest(sorted(groups)),
        "frozen_pool_sizes": {name: len(rows) for name, rows in pools.items()},
    }
    frozen = json.dumps(registration, indent=2, sort_keys=True, allow_nan=False) + "\n"
    output.mkdir(parents=True, exist_ok=False)
    (output / "compiled.xml").write_text(model)
    (output / "registration.json").write_text(frozen)


def sample_state(physical, backend):
    state = backend._data
    body = backend._model.joint("object_free")
    start = int(body.dofadr[0])
    return {
        "step": physical.physics_step,
        "sim_time_s": physical.sim_time_s,
        "monotonic_ns": monotonic_ns(),
        "object_center_m": physical.object_geom_position_m,
        "object_rotation_row_major": physical.object_geom_rotation_row_major,
        "object_velocity": state.qvel[start : start + 6].tolist(),
        "tcp_position_m": physical.tcp_position_m,
        "robot_qpos": state.qpos[:9].tolist(),
        "ctrl": state.ctrl.tolist(),
        "contacts": list(physical.contact_pairs),
    }


def acquire(output):
    verify_sources()
    require(os.environ["MUJOCO_GL"] == os.environ["PYOPENGL_PLATFORM"] == "egl", "EGL required")
    reg = read(output / "registration.json")
    require(
        reg["plan_sha256"] == sha(PLAN_PATH) and reg["script_sha256"] == sha(Path(__file__)),
        "registration and code differ",
    )
    scene = SceneSpec.model_validate(reg["scene"])
    config = simulator(scene.seed)
    model_xml, scenario = compile_pilot_scene(scene, config)
    require(
        model_xml == (output / "compiled.xml").read_text()
        and scenario_json(scenario) == reg["scenario"],
        "registered compile differs",
    )
    require(config.physics_dt_s == PLAN["native_step_dt_s"], "wrong worker timestep")
    cap = output / "capture"
    backend = MuJoCoPhysicsBackend()
    updates, snapshots, frames = [], [], []
    original_capture = MuJoCoRGBDCamera._capture
    budget = PLAN["registered_window_exposure_steps"]

    def capture_call(camera, data, **kwargs):
        require(len(updates) < len(budget) + 2, "extra exposure")
        result = original_capture(camera, data, **kwargs)
        updates.append(
            {
                "step": backend.total_physics_steps,
                "time_s": float(data.time),
                "include_instances": kwargs["include_instances"],
                "frame_id": result[0].frame_id,
                "captured_at": result[0].captured_at.isoformat(),
                "pass_state_hashes": result[3],
            }
        )
        return result

    class EndOfWindow(Exception):
        pass

    endpoint = EndOfWindow()
    with LOCK.open("rb") as file:
        fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        cap.mkdir(exist_ok=False)
        try:
            with patch.object(MuJoCoRGBDCamera, "_capture", capture_call):
                backend.initialize(config, model_xml=model_xml)
                backend._sensor_noise_std_m = 0.0
                require(
                    backend._model.opt.timestep == PLAN["native_step_dt_s"]
                    and matches_calibrated_gripper(backend._model, CURRENT_GRASP_PROFILE)
                    and float(backend._model.camera("rgbd").fovy[0]) == 45.0,
                    "compiled B0 camera, gripper or timestep differs",
                )
                with MuJoCoCaptureSession(config, backend=backend) as session:
                    backend.reset(scenario)
                    save_observation(
                        observation_from_sensor_frame(
                            backend._sensor_frame, source="mujoco_camera"
                        ),
                        cap / "auto-reset",
                    )
                    renderer = GL.glGetString(GL.GL_RENDERER).decode()
                    require(
                        "NVIDIA GeForce RTX 4070 Ti SUPER" in renderer,
                        "original renderer not available",
                    )
                    backend.step(PLAN["settle_steps"])
                    save_observation(
                        observation_from_sensor_frame(
                            backend._sensor_frame, source="mujoco_camera"
                        ),
                        cap / "auto-settle",
                    )
                    snapshots.append(sample_state(backend.current_physics_observation(), backend))

                    def observe(physical):
                        require(physical.physics_step <= budget[-1], "out of scope physics")
                        snapshots.append(sample_state(physical, backend))

                    try:
                        with (
                            backend.sensor_capture_on_demand(),
                            backend.observe_physics_steps(observe),
                        ):
                            for tick in budget:
                                gap = tick - backend.total_physics_steps
                                if gap:
                                    backend.step(gap)
                                require(
                                    backend.total_physics_steps == tick, "shutter clock shifted"
                                )
                                before = MuJoCoRGBDCamera._physics_state_hash(backend._data)
                                frame = session.capture_with_instances()
                                require(
                                    MuJoCoRGBDCamera._physics_state_hash(backend._data)
                                    == before
                                    == frame.physics_state_hash
                                    and frame.observation.sim_time_s == backend.get_sim_time(),
                                    "capture changed the compiled physics state",
                                )
                                name = f"step-{tick:04d}"
                                save_captured_frame(frame, cap / name)
                                frames.append(
                                    {
                                        "step": tick,
                                        "folder": name,
                                        "sim_time_s": frame.observation.sim_time_s,
                                        "frame_id": frame.observation.frame_id,
                                        "checksum_sha256": frame.observation.checksum_sha256,
                                    }
                                )
                            raise endpoint
                    except EndOfWindow as stopped:
                        require(stopped is endpoint, "unexpected acquisition termination")
                    require(
                        not backend.command_records and backend.total_physics_steps == budget[-1],
                        "control or timing drift",
                    )
                    require(
                        len(updates) == 13 and len(snapshots) == 2401,
                        "wrong exposure/state denominator",
                    )
            status = "COMPLETE"
        except BaseException:
            status = "STOPPED"
            raise
        finally:
            backend.shutdown()
            with (cap / "physical.jsonl").open("x", encoding="utf-8") as out:
                for row in snapshots:
                    out.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
            write(
                cap / "receipt.json",
                {
                    "status": status,
                    "registration_sha256": sha(output / "registration.json"),
                    "renderer": locals().get("renderer"),
                    "mujoco": mujoco.__version__,
                    "frames": frames,
                    "camera_calls": updates,
                    "counts": len(snapshots),
                    "files_sha256": {
                        p.relative_to(cap).as_posix(): sha(p)
                        for p in sorted(cap.rglob("*"))
                        if p.is_file()
                    },
                },
            )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("register", "capture"))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    {"register": register, "capture": acquire}[args.mode](args.output)


if __name__ == "__main__":
    main()
