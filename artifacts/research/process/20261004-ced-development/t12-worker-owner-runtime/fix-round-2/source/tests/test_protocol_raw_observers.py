"""Passive evidence hooks read actual commands/actuators without creating an executor."""

from dataclasses import FrozenInstanceError

import pytest

from cloud_edge_robot_arm.simulation.models import GripperCommand, JointCommand
from tests.test_rgbd_step_observer import backend as _backend_fixture


@pytest.fixture(name="backend")
def raw_backend():
    yield from _backend_fixture.__wrapped__()


def test_command_records_bind_actual_episode_step_and_requested_target(backend):
    backend.apply_joint_targets(JointCommand(positions=[3.0] * 7))
    backend.apply_gripper_command(GripperCommand(open=False))
    commands = backend.command_records
    assert [row["command_seq"] for row in commands] == [1, 2]
    assert all(
        row["episode_id"] == backend.current_physics_observation().episode_id
        and row["physics_step"] == 0
        for row in commands
    )
    assert commands[0]["target_positions_rad"] == [3.0] * 7
    assert commands[0]["applied_target_positions_rad"] == [2.8] * 7
    assert commands[1]["target_open"] is False
    commands[0]["target_positions_rad"][0] = -99
    assert backend.command_records[0]["target_positions_rad"] == [3.0] * 7


def test_actuator_observer_reads_pre_step_values_and_cannot_mutate(backend):
    actual = []
    model, data = backend._model, backend._data

    def observe(row):
        actual.append(row)
        assert row.physics_step == backend.total_physics_steps + 1
        assert row.sim_time_s == backend.get_sim_time()
        assert row.pre_joint_positions_rad == pytest.approx(data.qpos[:7])
        assert row.pre_gravity_bias_nm == pytest.approx(data.qfrc_bias[:7])
        assert row.control_rad == pytest.approx(data.ctrl[:7])
        assert row.finger_control_targets_m == pytest.approx(data.ctrl[7:9])
        assert row.actuator_gains == pytest.approx(model.actuator_gainprm[:7, 0])
        with pytest.raises(RuntimeError, match="observer callback"):
            backend.apply_joint_targets(JointCommand(positions=[0.0] * 7))
        with pytest.raises(FrozenInstanceError):
            row.physics_step = 99

    with backend.observe_actuator_steps(observe):
        backend.step(steps=3)
    backend.step(steps=1)
    assert [row.physics_step for row in actual] == [1, 2, 3]


def test_passive_step_and_actuator_observers_coexist_and_cleanup(backend):
    controls, observations = [], []
    with (
        backend.observe_actuator_steps(controls.append),
        backend.observe_physics_steps(observations.append),
    ):
        backend.step(steps=2)
    assert [row.physics_step for row in controls] == [row.physics_step for row in observations]
    assert all(
        post.sim_time_s > pre.sim_time_s for pre, post in zip(controls, observations, strict=True)
    )
    with pytest.raises(RuntimeError, match="raw observer failure"):
        with backend.observe_actuator_steps(
            lambda row: (_ for _ in ()).throw(RuntimeError("raw observer failure"))
        ):
            backend.step()
    backend.step()
    assert backend.total_physics_steps == 3


def test_teacher_passive_hooks_cover_real_steps_and_exact_command_ranges():
    from cloud_edge_robot_arm.datasets.rgbd.teacher import EpisodeRecorder, run_teacher_episode
    from cloud_edge_robot_arm.simulation.config import SimulatorConfig
    from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot
    from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession
    from tests.test_rgbd_teacher_smoke import _fixed_scene

    observed, actions, controls = [], [], []
    with MuJoCoCaptureSession(SimulatorConfig(camera_width=64, camera_height=64)) as session:
        scene = _fixed_scene()
        session.apply_scene(scene)
        physical = session._backend
        with physical.observe_actuator_steps(controls.append):
            outcome = run_teacher_episode(
                scene,
                MuJoCoSkillRobot(physical),
                EpisodeRecorder(),
                case="NO_CONTACT",
                settle_steps=3,
                physical_observer=observed.append,
                action_observer=actions.append,
            )
        assert not outcome.success
        assert [row.physics_step for row in observed] == list(
            range(physical.total_physics_steps + 1)
        )
        assert [row.physics_step for row in controls] == list(
            range(1, physical.total_physics_steps + 1)
        )
        assert len(actions) == 1
        event = actions[0]
        assert event["episode_id"] == observed[0].episode_id
        assert event["start_step"] == 3 and event["end_step"] == observed[-1].physics_step
        commands = physical.command_records
        selected = [
            row
            for row in commands
            if event["command_seq_start"] <= row["command_seq"] < event["command_seq_end"]
        ]
        assert selected
        assert event["result"]["success"] is False
        assert event["result"]["action_type"] == "GRASP"


def test_actuator_observer_is_cleared_by_episode_reset(backend):
    from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig

    calls = []
    with backend.observe_actuator_steps(calls.append):
        backend.step()
        backend.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=43))
        backend.step()
    assert len(calls) == 1


def test_nested_teacher_cannot_clear_an_outer_read_only_guard(backend):
    from cloud_edge_robot_arm.datasets.rgbd.models import SceneSpec
    from cloud_edge_robot_arm.datasets.rgbd.teacher import EpisodeRecorder, run_teacher_episode
    from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot
    from tests.test_rgbd_teacher_smoke import _fixed_scene

    source = _fixed_scene()
    # This source matches the currently reset episode and model. The callback
    # must reject before reading/mutating the backend regardless of that match.
    scene = SceneSpec.model_construct(
        **{
            **source.model_dump(),
            "group_id": backend._scenario.scenario_id,
        }
    )

    def observe(_snapshot):
        with pytest.raises(RuntimeError):
            run_teacher_episode(
                scene,
                MuJoCoSkillRobot(backend),
                EpisodeRecorder(),
                physical_observer=lambda row: None,
            )
        assert backend._in_observer_callback is True
        with pytest.raises(RuntimeError, match="observer callback"):
            backend.apply_joint_targets(JointCommand(positions=[0.0] * 7))

    with backend.observe_physics_steps(observe):
        backend.step()
