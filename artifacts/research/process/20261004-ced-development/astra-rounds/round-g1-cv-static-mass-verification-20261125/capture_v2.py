"""Capture the registered diagnostic images, retaining the original failed reset."""

import argparse
import importlib
import os
import sys
from pathlib import Path

import numpy as np
from scripts.graduation.perception_io import pinned, read, sha, write

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent / "round-g1-cv-grasp-validation-20261125"
sys.path.insert(0, str(PARENT))
first = importlib.import_module("prospective")

SUPP_SHA = "672f070af35acc7bcd7ad8e605cbe69308be737843a01e3a248af0a4566e91b8"
OUT = first.PRIVATE.parent / "capture-v2"
SHAPES = {
    "mass_kg": (),
    "principal_inertia_kg_m2": (3,),
    "body_local_center_of_mass_m": (3,),
    "inertial_quaternion_wxyz": (4,),
}


def compare_properties(before, after):
    if before.keys() != SHAPES.keys() or after.keys() != SHAPES.keys():
        raise ValueError("unregistered rigid-body property keys")
    differences = {}
    for key, shape in SHAPES.items():
        a, b = np.asarray(before[key]), np.asarray(after[key])
        if any(
            x.dtype.kind not in "fiu" or x.shape != shape or not np.isfinite(x).all()
            for x in (a, b)
        ):
            raise ValueError(f"invalid {key}")
        if not np.allclose(a, b, rtol=0, atol=1e-12, equal_nan=False):
            raise ValueError(f"reset changed {key}")
        differences[key] = float(np.max(np.abs(a.astype(float) - b.astype(float))))
    return differences


def register(supp, parent_plan):
    fail_log = HERE / "first-reset.stderr.txt"
    for name, digest in supp["inputs_sha256"].items():
        path = Path(name)
        if path.is_absolute() and path.name == "fresh.log":
            path = fail_log
        if sha(path) != digest:
            raise ValueError(f"changed preserved source {path}")
    before = first.PRIVATE / "registration.json"
    initial = pinned(before, sha(PARENT / "prospective-registration.public.json"))
    assert initial["slots"] == parent_plan["new_development_placements"] and initial[
        "capture_source_sha256"
    ] == sha(Path(first.__file__))
    close = read(first.PRIVATE / "cvdev01/job-close.json")
    assert close["final_job_status"] == "FAILED" and close["lease_released"]
    assert (
        not list((first.PRIVATE / "blind/A").glob("*.json"))
        and not (first.PRIVATE / "cvdev02").exists()
    )
    OUT.mkdir(exist_ok=False, parents=True)
    record = dict(
        parent_registration_sha256=sha(before),
        plan_sha256=first.PLAN_SHA,
        supplement_sha256=SUPP_SHA,
        slots=initial["slots"],
        source_sha256=sha(Path(__file__)),
        previous_failed_job=close["job_id"],
        previous_diagnostic_resets=1,
        previous_exported_frames=0,
    )
    write(OUT / "registration.json", record)
    write(HERE / "registration-v2.public.json", record)


def capture_one(template, slot, token, blind, baseline):
    import mujoco
    from scripts.graduation import dynamic_vision as native
    from scripts.graduation.g1_dual_probe import config
    from scripts.graduation.g1_dual_trials import bind_scenario_mass, mass_properties
    from scripts.graduation.g1_formal_runtime import bind_scene
    from scripts.graduation.g1_formal_trials import identities

    assert Path(native.__file__).resolve().is_relative_to(first.FROZEN.resolve())
    raw = OUT / slot["id"]
    raw.mkdir()
    scene = "g1-cv-select-v2-" + token.lower() + "-20261125"
    fields = dict(
        baseline=baseline,
        component_catalog_sha256=template["component_catalog_sha256"],
        case={
            **identities(scene),
            "visual_id": scene,
            "visual_seed": slot["seed"],
            "scene_id": scene,
            "release": "g1-cv-static-v2",
        },
        intent_descriptor={"type": "development zero-step RGB-D and robot encoders"},
    )
    write(raw / "diagnostic-allocation.json", fields)
    owner = native.Owner(raw, fields, sha(raw / "diagnostic-allocation.json"))
    backend = native.MuJoCoPhysicsBackend()
    ok = False
    try:
        with bind_scene(scene):
            geometry = template["geometry"]
            backend.initialize(config({"geometry": geometry}, slot["seed"]))
            original = mass_properties(backend._model)
            x, y, z = slot["reset_fixture_center_m"]
            scene_cfg = native.PhysicalScenarioConfig(
                scenario_id=scene,
                seed=slot["seed"],
                object_pose=native.Pose(x=x, y=y, z=z),
                object_yaw_rad=slot["yaw_rad"],
            )
            backend.reset(
                bind_scenario_mass(
                    scene_cfg, template["case"]["physical_object_mass_kg"], original["mass_kg"]
                )
            )
            actual = mass_properties(backend._model)
            difference = compare_properties(original, actual)
            robot = native.MuJoCoSkillRobot(backend)
            owner.current()
            native.check_component_hard_state(backend, robot)
            frame = native.observation_from_sensor_frame(
                backend.capture_sensor_frame(), source="mujoco_camera", png_compress_level=1
            )
            native.validate_camera(frame, geometry)
            assert frame.scene_id == scene and frame.episode_id and frame.sim_time_s == 0
            measured = first.measured_robot(backend, frame)
            native.check_component_hard_state(backend, robot)
            owner.current()
            assert not backend.command_records and backend.total_physics_steps == 0
            pending = blind / ("pending-" + token)
            pending.mkdir()
            write(pending / "frame.json", frame.model_dump(mode="json"))
            write(pending / "proprio.json", measured)
            write(
                raw / "reset-properties.json",
                dict(compiled=original, reset=actual, max_abs_delta=difference),
            )
            ok = True
    finally:
        try:
            final = owner.close(ok)
        finally:
            backend.shutdown()
        write(raw / "job-close.json", final)
    assert final["final_job_status"] == "SUCCEEDED" and final["lease_released"]
    output = blind / token
    assert not output.exists()
    pending.rename(output)
    return dict(
        slot=slot["id"],
        token=token,
        frame_id=frame.frame_id,
        episode=frame.episode_id,
        checksum=frame.checksum_sha256,
        captured_at=frame.captured_at.isoformat(),
        physics_steps=0,
        commands=0,
        job=final,
        native_mujoco=mujoco.__version__,
        max_abs_difference=difference,
        frame_sha256=sha(output / "frame.json"),
        proprio_sha256=sha(output / "proprio.json"),
    )


def capture(plan):
    from scripts.graduation.g1_visibility_trials import device

    assert os.environ.get("MUJOCO_GL") == "egl"
    registered = pinned(OUT / "registration.json", sha(HERE / "registration-v2.public.json"))
    assert (
        registered["source_sha256"] == sha(Path(__file__))
        and registered["slots"] == plan["new_development_placements"]
    )
    lock = pinned(first.FROZEN / "runtime-build.json", first.GENERATION)
    if any(
        sha(first.FROZEN / name) != digest for name, digest in lock["runtime_files_sha256"].items()
    ):
        raise ValueError("frozen capture source differs")
    template = pinned(first.TEMPLATE, plan["inputs_sha256"][str(first.TEMPLATE)])
    asset = first.FROZEN / template["geometry"]["asset_path"]
    assert sha(asset) == template["asset_sha256"] == plan["inputs_sha256"][str(asset)]
    blind = OUT / "blind"
    blind.mkdir()
    write(blind / "geometry.json", template["geometry"])
    with device(first.OLD.resolve()):
        rows = [
            capture_one(template, slot, token, blind, plan["baseline"])
            for slot, token in zip(registered["slots"], ("A", "B"), strict=True)
        ]
    assert (
        len({r["frame_id"] for r in rows})
        == len({r["episode"] for r in rows})
        == len({r["job"]["job_id"] for r in rows})
        == 2
    )
    result = dict(
        registration_sha256=sha(OUT / "registration.json"),
        runtime_build_sha256=first.GENERATION,
        geometry_sha256=sha(blind / "geometry.json"),
        xml_sha256=sha(asset),
        captures=rows,
        resets_this_generation=2,
        previous_failed_resets=1,
        total_diagnostic_resets=3,
        physical_steps=0,
        motion_commands=0,
        completed_physical_grasps=0,
        formal_claims=0,
    )
    write(OUT / "capture.json", result)
    write(HERE / "capture-v2.public.json", result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["register", "capture"])
    args = parser.parse_args()
    supplement = pinned(HERE / "plan.json", SUPP_SHA)
    plan = pinned(PARENT / "plan.json", first.PLAN_SHA)
    assert (
        sha(HERE / "plan.md") == supplement["plan_md_sha256"]
        and supplement["parent_plan_sha256"] == first.PLAN_SHA
    )
    if args.mode == "register":
        register(supplement, plan)
    else:
        capture(plan)
