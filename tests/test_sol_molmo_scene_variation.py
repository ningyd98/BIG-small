"""Component pose variation must reach physics without granting native authority."""

import importlib
import math
from pathlib import Path

import numpy as np
import pytest

FAMILY = "side_y_plus_id7_75mm_component_v1"


def scene_api():
    return importlib.import_module("cloud_edge_robot_arm.research.sol_molmo_scenarios")


def test_seeded_component_conditions_are_distinct_reproducible_and_bounded():
    api = scene_api()
    rows = [api.sample_component_scene(seed, "development") for seed in range(43001, 43041)]
    assert rows == [api.sample_component_scene(seed, "development") for seed in range(43001, 43041)]
    assert len({tuple(row["object_position_m"]) for row in rows}) == 40
    assert {row["condition"] for row in rows} == {"VISIBLE_POSE", "ARM_OCCLUSION_STRESS"}
    for row in rows:
        x, y, z = row["object_position_m"]
        assert 0.35 <= x <= 0.52 and -0.45 <= y <= 0.08 and z == 0.035
        assert -0.35 <= row["object_yaw_rad"] <= 0.35


def test_held_out_namespace_changes_actual_pose_not_just_split_label():
    api = scene_api()
    development = api.sample_component_scene(43001, "development")
    held_out = api.sample_component_scene(43001, "held-out")
    assert development["object_position_m"] != held_out["object_position_m"]


@pytest.mark.parametrize("split", ["", "holdout", None, 1])
def test_unknown_component_split_is_rejected(split):
    with pytest.raises(ValueError):
        scene_api().sample_component_scene(43001, split)


@pytest.mark.parametrize("change", ["position", "yaw", "seed", "extra"])
def test_resealed_or_invalid_scene_specification_cannot_select_arbitrary_physics(change):
    api = scene_api()
    scene = api.sample_component_scene(43001, "development")
    if change == "position":
        scene["object_position_m"] = [1000.0, 0.0, 0.035]
    elif change == "yaw":
        scene["object_yaw_rad"] = float("nan")
    elif change == "seed":
        scene["seed"] = 43002
    else:
        scene["extra"] = True
    with pytest.raises(ValueError, match="scene"):
        api.physical_component_scenario(43001, scene)


def test_scene_assignment_declares_varied_pose_and_retains_original_fixed_default():
    entry = importlib.import_module("cloud_edge_robot_arm.research.sol_molmo_single_episode")
    fixed = entry.scene_assignment(43001, FAMILY)
    varied = entry.scene_assignment(43001, FAMILY, scene_split="development")
    assert fixed["scene_sampling"] == "FIXED_REGISTERED_SCENE"
    assert fixed["independent_random_scene"] is False
    assert varied["scene_sampling"] == "SEEDED_COMPONENT_POSE_V1"
    assert varied["component_scene"]["split"] == "development"
    assert varied["model_path"] == fixed["model_path"]
    assert varied["component_scene"]["object_position_m"] != [0.45, 0.0, 0.035]


def test_component_scene_cannot_enter_formal_execution(tmp_path):
    entry = importlib.import_module("cloud_edge_robot_arm.research.sol_molmo_single_episode")
    output = tmp_path / "formal"
    with pytest.raises(ValueError, match="component"):
        entry.run_single_episode(output=output, mode="execute", scene_split="development")
    assert not output.exists()


def test_mujoco_reset_applies_object_yaw_instead_of_discarding_orientation():
    from cloud_edge_robot_arm.simulation.config import SimulatorConfig
    from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig
    from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend

    backend = MuJoCoPhysicsBackend()
    asset = Path(__file__).resolve().parents[1] / "assets/robots/franka_panda/scene.xml"
    try:
        backend.initialize(SimulatorConfig(model_path=str(asset), domain_randomization=False))
        backend.reset(
            PhysicalScenarioConfig("S01_NORMAL_STATIC", 43001, object_yaw_rad=math.pi / 2)
        )
        orientation = backend._data.xquat[backend._model.body("object").id]
        assert np.asarray(orientation) == pytest.approx([2**-0.5, 0.0, 0.0, 2**-0.5])
    finally:
        backend.shutdown()
