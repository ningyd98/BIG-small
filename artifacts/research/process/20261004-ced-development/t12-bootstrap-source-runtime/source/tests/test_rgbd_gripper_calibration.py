"""The repaired gripper has its own calibration; old freezes cannot claim it."""

from __future__ import annotations

import hashlib
from pathlib import Path
from xml.etree import ElementTree

import pytest

from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot
from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession
from cloud_edge_robot_arm.vision.evaluation import ExecutionPolicy
from cloud_edge_robot_arm.vision.execution import _VisualEpisode
from cloud_edge_robot_arm.vision.model_resolver import resolve_visual_planner
from tests.test_rgbd_grasp_scope import _decision, _request
from tests.test_rgbd_model_probe import _passing_report
from tests.test_rgbd_normalized_protocol import _snapshot


def test_repaired_gripper_planner_records_its_own_calibration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _decision(monkeypatch, "red cube")
    planner = resolve_visual_planner(
        _snapshot(image_size=(64, 64), grasp_profile="mujoco_upright_box_v2")
    )
    draft = planner.plan(_request("mujoco_camera"))
    assert draft.observed_scene is not None
    assert draft.observation_evidence["grasp_profile"] == "mujoco_upright_box_v2"
    assert draft.observation_evidence["grasp_calibration_asset_sha256"] == hashlib.sha256(
        Path("assets/robots/franka_panda/scene.xml").read_bytes()
    ).hexdigest()
    assert draft.observation_evidence["resolved_top_grasp_tcp"]["z"] == pytest.approx(1.05)


@pytest.mark.parametrize("profile", ["mujoco_upright_box_v1", "mujoco_upright_box_v2"])
@pytest.mark.parametrize("prepared", [False, True])
def test_visual_episode_requires_the_selected_calibration_asset(
    profile: str, prepared: bool,
) -> None:
    planner = resolve_visual_planner(_snapshot(grasp_profile=profile))
    assert planner.model_snapshot is not None
    policy = ExecutionPolicy(
        instruction="Move the red box", scope="VISION_CLOSED_LOOP",
        model_snapshot_hash=planner.model_snapshot.digest(),
    )
    with MuJoCoCaptureSession(SimulatorConfig(camera_width=64, camera_height=64)) as session:
        if prepared:
            from tests.test_rgbd_teacher_smoke import _fixed_scene

            session.apply_scene(_fixed_scene())
        robot = MuJoCoSkillRobot(session._backend)
        if profile == "mujoco_upright_box_v1":
            with pytest.raises(ValueError, match="asset differs"):
                _VisualEpisode(planner, robot, session, policy)
        else:
            assert _VisualEpisode(planner, robot, session, policy).backend is session._backend


def test_model_freeze_binds_profile_evidence_and_source_asset() -> None:
    from scripts.probe_rgbd_model import can_freeze

    report = _passing_report()
    asset = hashlib.sha256(Path("assets/robots/franka_panda/scene.xml").read_bytes()).hexdigest()
    report["snapshot"]["grasp_profile"] = "mujoco_upright_box_v2"
    for attempt in report["attempts"]:
        attempt["observation_evidence"].update(
            grasp_profile="mujoco_upright_box_v2", grasp_calibration_asset_sha256=asset,
        )
    assert can_freeze(report)
    report["attempts"][0]["observation_evidence"]["grasp_profile"] = "mujoco_upright_box_v1"
    assert not can_freeze(report)


def test_contract_rejects_a_draft_from_another_model_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cloud_edge_robot_arm.vision.execution import grounded_contract

    _decision(monkeypatch, "red cube")
    request = _request("mujoco_camera")
    assert request.observation is not None
    request = request.model_copy(update={
        "observation": request.observation.model_copy(update={"episode_id": "calibration-episode"}),
    })
    old = resolve_visual_planner(
        _snapshot(image_size=(64, 64), grasp_profile="mujoco_upright_box_v1")
    )
    current = _snapshot(image_size=(64, 64), grasp_profile="mujoco_upright_box_v2")
    policy = ExecutionPolicy(instruction="Move the red box", model_snapshot_hash=current.digest())
    with pytest.raises(ValueError, match="snapshot"):
        grounded_contract(old.plan(request), request.observation, policy)
    draft = resolve_visual_planner(current).plan(request)
    assert grounded_contract(draft, request.observation, policy).steps
    draft.observation_evidence["model_snapshot"]["grasp_profile"] = "mujoco_upright_box_v1"
    with pytest.raises(ValueError, match="calibration"):
        grounded_contract(draft, request.observation, policy)


@pytest.mark.parametrize("mutation", [
    "old_centers", "body_rotation", "geom_rotation", "tcp_rotation", "unlimited_joint",
    "joint_reference",
])
def test_visual_episode_rejects_changed_geometry_loaded_with_new_asset_path(
    mutation: str,
) -> None:
    from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig
    from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend

    config = SimulatorConfig(camera_width=64, camera_height=64)
    root = ElementTree.fromstring(Path(config.model_path).read_text())
    if mutation == "old_centers":
        for name, sign in (("left_finger", ""), ("right_finger", "-")):
            element = root.find(f".//body[@name='{name}']")
            assert element is not None
            element.set("pos", f"0.075 {sign}0.04 0")
    else:
        selector = {
            "body_rotation": ".//body[@name='left_finger']",
            "geom_rotation": ".//geom[@name='left_finger_geom']",
            "tcp_rotation": ".//site[@name='tcp']",
            "unlimited_joint": ".//joint[@name='finger_left_joint']",
            "joint_reference": ".//joint[@name='finger_left_joint']",
        }[mutation]
        element = root.find(selector)
        assert element is not None
        if mutation == "unlimited_joint":
            element.set("limited", "false")
        elif mutation == "joint_reference":
            element.set("ref", "0.02")
        else:
            element.set("quat", "0.7071067811865476 0 0.7071067811865476 0")
    xml = ElementTree.tostring(root, encoding="unicode")
    backend = MuJoCoPhysicsBackend()
    backend.initialize(config, model_xml=xml)
    backend.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=31))
    planner = resolve_visual_planner(_snapshot(grasp_profile="mujoco_upright_box_v2"))
    assert planner.model_snapshot is not None
    policy = ExecutionPolicy(instruction="Move the red box",
                             model_snapshot_hash=planner.model_snapshot.digest())
    try:
        with MuJoCoCaptureSession(config, backend=backend) as capture:
            with pytest.raises(ValueError, match="geometry"):
                _VisualEpisode(planner, MuJoCoSkillRobot(backend), capture, policy)
        assert backend.total_physics_steps == 0
    finally:
        backend.shutdown()


def test_scene_summary_rejects_mixed_calibration_versions() -> None:
    from scripts.evaluate_rgbd_model_scenes import build_assignments, summarize_results

    from tests.test_rgbd_model_scene_eval import _record

    assignments = build_assignments()
    records = [_record(case) for case in assignments["cases"]]
    model_path = Path("assets/robots/franka_panda/scene.xml")
    asset_hash = hashlib.sha256(model_path.read_bytes()).hexdigest()
    for record in records:
        record["attempt"]["observation_evidence"].update(
            grasp_profile="mujoco_upright_box_v2", grasp_calibration_asset_sha256=asset_hash,
        )
    assert summarize_results(assignments, records)["all_cases_pass"]
    records[0]["attempt"]["observation_evidence"].update(
        grasp_profile="mujoco_upright_box_v1",
        grasp_calibration_asset_sha256=(
            "182fb2bc068ba44de394622f819ae444eb7fbe51df5c5311591a8abb97bf6a08"
        ),
    )
    summary = summarize_results(assignments, records)
    assert not summary["all_cases_pass"]
    assert summary["positive_passed"] == 11
    assert summary["positive_gate_counts"]["calibrated_offset"] == 11
