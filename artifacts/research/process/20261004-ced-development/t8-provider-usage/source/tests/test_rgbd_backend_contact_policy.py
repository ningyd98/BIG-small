"""Real table support stays legal; collisions with distractors do not."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend


def _model_xml_with_distractor(position: str) -> str:
    tree = ET.fromstring(Path("assets/robots/franka_panda/scene.xml").read_text())
    world = tree.find("worldbody")
    assert world is not None
    body = ET.SubElement(world, "body", name="dataset_distractor_0", pos=position)
    ET.SubElement(body, "freejoint", name="dataset_distractor_0_free")
    ET.SubElement(
        body, "geom", name="dataset_distractor_0_geom", type="box",
        size="0.035 0.035 0.035", mass="0.08", contype="1", conaffinity="1",
    )
    return ET.tostring(tree, encoding="unicode")


def test_real_mujoco_table_support_of_dataset_distractor_is_not_collision() -> None:
    backend = MuJoCoPhysicsBackend()
    try:
        backend.initialize(
            SimulatorConfig(model_path="assets/robots/franka_panda/scene.xml"),
            model_xml=_model_xml_with_distractor("0.60 0.15 0.043"),
        )
        backend.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=31))
        backend.step(steps=20)
        contacts = backend.get_contacts()
        support = [
            contact for contact in contacts
            if {contact.geom1, contact.geom2} == {"table", "dataset_distractor_0_geom"}
        ]
        assert support, "the actual MuJoCo distractor must touch the table"
        assert all(not contact.illegal for contact in support)
        assert not any(contact.illegal for contact in contacts)
        from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot

        assert not MuJoCoSkillRobot(backend).get_state().collision_detected
    finally:
        backend.shutdown()


def test_real_mujoco_object_distractor_collision_remains_illegal() -> None:
    backend = MuJoCoPhysicsBackend()
    try:
        backend.initialize(
            SimulatorConfig(model_path="assets/robots/franka_panda/scene.xml"),
            model_xml=_model_xml_with_distractor("0.45 0 0.035"),
        )
        backend.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=31))
        backend.step()
        collisions = [
            contact for contact in backend.get_contacts()
            if {contact.geom1, contact.geom2}
            == {"object_geom", "dataset_distractor_0_geom"}
        ]
        assert collisions, "the actual MuJoCo movable boxes must overlap"
        assert all(contact.illegal for contact in collisions)
    finally:
        backend.shutdown()


@pytest.mark.parametrize(
    "geom1,geom2,expected,illegal",
    [
        ("left_finger_geom", "object_geom", True, False),
        ("object_geom", "right_finger_geom", True, False),
        ("table", "object_geom", False, False),
        ("table", "dataset_distractor_0_geom", False, False),
        ("dataset_distractor_1_geom", "table", False, False),
        ("table", "dataset_distractor_2_geom", False, False),
        ("hand", "dataset_distractor_0_geom", False, True),
        ("left_finger_geom", "dataset_distractor_0_geom", False, True),
        ("object_geom", "dataset_distractor_0_geom", False, True),
        ("table", "unknown_geom", False, True),
    ],
)
def test_contact_pair_classification_is_exact(
    geom1: str, geom2: str, expected: bool, illegal: bool
) -> None:
    from cloud_edge_robot_arm.simulation.mujoco.backend import _classify_contact_pair

    assert _classify_contact_pair(geom1, geom2) == (expected, illegal)
