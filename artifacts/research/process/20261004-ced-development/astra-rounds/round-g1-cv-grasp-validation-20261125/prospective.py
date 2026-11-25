"""Register new development placements and capture isolated step-zero observations."""

import argparse
from pathlib import Path

import numpy as np
from scripts.graduation.perception_io import pinned, read, sha, write

ROUND = Path(__file__).resolve().parent
PLAN_SHA = "596158c29f9d43573a92c2be22a5b9db55e5d8b21f08cc8382e65e3d8b7ffb1a"
GENERATION = "5c09e38b82e09a8c52de407bee97775aca8b8a48b4d14a3bfc387ffd626fa212"
OLD = Path("experiments/results/g1-visibility-pose-repair-20261124")
FROZEN = OLD / "builds" / GENERATION / "runtime-source"
PRIVATE = Path("experiments/results/g1-cv-grasp-validation-20261125/prospective")
TEMPLATE = OLD / "batches/train-radial30-contact-d02-02/d02/allocation.json"


def ensure_new_placements(rows, historical):
    centers, seeds, identifiers = set(), set(), set()

    def collect(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in ("id", "visual_id", "slot") and isinstance(child, str):
                    identifiers.add(child)
                collect(child)
        elif isinstance(value, list):
            if len(value) in (3, 4) and all(type(x) in (float, int) for x in value):
                centers.add(tuple(value[:3]))
            for child in value:
                collect(child)
        elif type(value) is int:
            seeds.add(value)

    for document in historical:
        collect(document)
    for row in rows:
        center = tuple(row["reset_fixture_center_m"])
        if center in centers or row["seed"] in seeds or row["id"] in identifiers:
            raise ValueError("reused placement, seed or slot")
        centers.add(center)
        seeds.add(row["seed"])
        identifiers.add(row["id"])


def register(plan):
    from scripts.graduation.g1_visibility_selection import history_documents

    for name, digest in plan["inputs_sha256"].items():
        if sha(Path(name)) != digest:
            raise ValueError(f"changed plan input {name}")
    archived = sorted((OLD / "batches").glob("*/[de]*/allocation.json"))
    rows = plan["new_development_placements"]
    ensure_new_placements(rows, [*history_documents(), *(read(p)["case"] for p in archived)])
    PRIVATE.mkdir(exist_ok=False, parents=True)
    receipt = dict(
        batch=plan["matrix"]["new_dev_batch"],
        scope="development zero-step diagnostics",
        frames_per_slot=1,
        slots=rows,
        plan_sha256=PLAN_SHA,
        parent_generation=GENERATION,
        capture_source_sha256=sha(Path(__file__)),
        historical_allocations=[str(p) for p in archived],
        formal_runs=0,
        physical_attempts=0,
    )
    write(PRIVATE / "registration.json", receipt)
    write(ROUND / "prospective-registration.public.json", receipt)


def measured_robot(backend, frame):
    import mujoco

    joints = backend.get_joint_state()
    model, data = backend._model, backend._data
    scratch = mujoco.MjData(model)
    for name, value in zip(joints.names, joints.positions, strict=True):
        scratch.joint(name).qpos[0] = value
    mujoco.mj_kinematics(model, scratch)
    tcp = backend.get_tcp_pose()
    xyz = [tcp.x, tcp.y, tcp.z]
    site = scratch.site("tcp")
    np.testing.assert_allclose(xyz, site.xpos, atol=1e-9, rtol=0)
    rotation = np.empty(4)
    mujoco.mju_mat2Quat(rotation, site.xmat)
    # These are the two simulated slide encoders read by MuJoCoSkillRobot.get_state.
    fingers = [
        float(data.joint(name).qpos[0]) for name in ("finger_left_joint", "finger_right_joint")
    ]
    assert joints.sim_time_s == frame.sim_time_s == backend.get_sim_time()
    return dict(
        frame_id=frame.frame_id,
        checksum=frame.checksum_sha256,
        sim_time_s=joints.sim_time_s,
        joint_positions_rad=joints.positions,
        joint_velocities_rad_s=joints.velocities,
        tcp_position_m=xyz,
        tcp_quaternion_wxyz=rotation.tolist(),
        finger_positions_m=fingers,
        source="seven measured robot joints, TCP forward kinematics, two finger slide encoders",
    )


def capture(plan):
    from scripts.graduation import dynamic_vision as native
    from scripts.graduation.g1_dual_probe import config
    from scripts.graduation.g1_dual_trials import bind_scenario_mass, mass_properties
    from scripts.graduation.g1_formal_runtime import bind_scene
    from scripts.graduation.g1_formal_trials import identities
    from scripts.graduation.g1_visibility_trials import device

    assert Path(native.__file__).resolve().is_relative_to(FROZEN.resolve())
    lock = pinned(FROZEN / "runtime-build.json", GENERATION)
    for name, digest in lock["runtime_files_sha256"].items():
        if sha(FROZEN / name) != digest:
            raise ValueError(f"frozen runtime file differs {name}")
    receipt = pinned(
        PRIVATE / "registration.json", sha(ROUND / "prospective-registration.public.json")
    )
    assert receipt["capture_source_sha256"] == sha(Path(__file__))
    assert receipt["slots"] == plan["new_development_placements"]
    template = pinned(TEMPLATE, plan["inputs_sha256"][str(TEMPLATE)])
    geometry = template["geometry"]
    asset = FROZEN / geometry["asset_path"]
    assert sha(asset) == template["asset_sha256"] == plan["inputs_sha256"][str(asset)]
    blind = PRIVATE / "blind"
    blind.mkdir(exist_ok=True)
    geometry_file = blind / "geometry.json"
    if not geometry_file.exists():
        write(geometry_file, geometry)
    assert read(geometry_file) == geometry
    captures = []
    with device(OLD.resolve()):
        for slot, token in zip(receipt["slots"], ("A", "B"), strict=True):
            scene = "g1-cv-selection-" + token.lower() + "-20261125"
            raw = PRIVATE / slot["id"]
            raw.mkdir()
            output = blind / token
            output.mkdir()
            allocation = dict(
                baseline=plan["baseline"],
                component_catalog_sha256=template["component_catalog_sha256"],
                intent_descriptor={"type": "read-only development camera and robot measurement"},
                case={
                    **identities(scene),
                    "visual_id": scene,
                    "visual_seed": slot["seed"],
                    "scene_id": scene,
                    "release": "g1-cv-static-20261125",
                },
            )
            write(raw / "diagnostic-allocation.json", allocation)
            owner = native.Owner(raw, allocation, sha(raw / "diagnostic-allocation.json"))
            backend = native.MuJoCoPhysicsBackend()
            ok = False
            try:
                with bind_scene(scene):
                    backend.initialize(config({"geometry": geometry}, slot["seed"]))
                    compiled = mass_properties(backend._model)
                    x, y, z = slot["reset_fixture_center_m"]
                    scenario = native.PhysicalScenarioConfig(
                        scenario_id=scene,
                        seed=slot["seed"],
                        object_pose=native.Pose(x=x, y=y, z=z),
                        object_yaw_rad=slot["yaw_rad"],
                    )
                    scenario = bind_scenario_mass(
                        scenario, template["case"]["physical_object_mass_kg"], compiled["mass_kg"]
                    )
                    backend.reset(scenario)
                    assert mass_properties(backend._model) == compiled
                    robot = native.MuJoCoSkillRobot(backend)
                    owner.current()
                    native.check_component_hard_state(backend, robot)
                    frame = native.observation_from_sensor_frame(
                        backend.capture_sensor_frame(), source="mujoco_camera", png_compress_level=1
                    )
                    native.validate_camera(frame, geometry)
                    assert frame.scene_id == scene and frame.episode_id and frame.sim_time_s == 0
                    proprio = measured_robot(backend, frame)
                    owner.current()
                    native.check_component_hard_state(backend, robot)
                    assert backend.total_physics_steps == 0 and not backend.command_records
                    write(output / "frame.json", frame.model_dump(mode="json"))
                    write(output / "proprio.json", proprio)
                    ok = True
            finally:
                final = owner.close(ok)
                backend.shutdown()
                write(raw / "job-close.json", final)
            captures.append(
                dict(
                    slot=slot["id"],
                    token=token,
                    frame_id=frame.frame_id,
                    episode=frame.episode_id,
                    checksum=frame.checksum_sha256,
                    captured_at=frame.captured_at.isoformat(),
                    physics_steps=0,
                    commands=0,
                    job_id=final["job_id"],
                    lease_released=final["lease_released"],
                    compiled_reset_mass_kg=compiled["mass_kg"],
                    frame_sha256=sha(output / "frame.json"),
                    proprio_sha256=sha(output / "proprio.json"),
                )
            )
    assert (
        len({r["episode"] for r in captures})
        == len({r["frame_id"] for r in captures})
        == len(captures)
        == 2
    )
    result = dict(
        registration_sha256=sha(PRIVATE / "registration.json"),
        runtime_source_sha256=GENERATION,
        asset_sha256=sha(asset),
        geometry_sha256=sha(geometry_file),
        captures=captures,
        physics_steps=0,
        motion_commands=0,
        slots_dispatched=0,
        use="step-zero sensor qualification; no physical grasp attempts",
    )
    write(PRIVATE / "capture.json", result)
    write(ROUND / "prospective-capture.public.json", result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["register", "capture"])
    args = parser.parse_args()
    plan = pinned(ROUND / "plan.json", PLAN_SHA)
    if sha(ROUND / "plan.md") != plan["plan_md_sha256"]:
        raise ValueError("plan text changed")
    if args.mode == "register":
        register(plan)
    else:
        capture(plan)
