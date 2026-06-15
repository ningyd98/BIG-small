from __future__ import annotations

from cloud_edge_robot_arm.simulation.backend import SimulatorBackend


def test_phase9_simulator_backend_is_protocol() -> None:
    assert getattr(SimulatorBackend, "_is_protocol", False)


def test_phase9_backend_protocol_methods_are_declared() -> None:
    expected = {
        "initialize",
        "reset",
        "step",
        "shutdown",
        "get_sim_time",
        "get_joint_state",
        "get_tcp_pose",
        "get_contacts",
        "get_sensor_frame",
        "apply_joint_targets",
        "apply_gripper_command",
        "emergency_stop",
        "inject_fault",
    }
    assert expected.issubset(set(SimulatorBackend.__dict__))
