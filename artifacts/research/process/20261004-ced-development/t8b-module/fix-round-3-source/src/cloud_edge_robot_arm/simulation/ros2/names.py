"""ROS2 名称约定，集中管理 topic、frame 和 namespace。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Phase9RosNames:
    clock: str = "/clock"
    joint_states: str = "/bigsmall/joint_states"
    tcp_pose: str = "/bigsmall/tcp_pose"
    robot_state: str = "/bigsmall/robot_state"
    camera_color: str = "/bigsmall/camera/color"
    camera_depth: str = "/bigsmall/camera/depth"
    camera_info: str = "/bigsmall/camera/camera_info"
    contacts: str = "/bigsmall/contacts"
    scene_summary: str = "/bigsmall/scene_summary"
    safety_event: str = "/bigsmall/safety_event"
    fault_event: str = "/bigsmall/fault_event"
    simulation_status: str = "/bigsmall/simulation/status"
    move_to_pose: str = "/bigsmall/move_to_pose"
    follow_joint_trajectory: str = "/bigsmall/follow_joint_trajectory"
    gripper_command: str = "/bigsmall/gripper_command"
    home: str = "/bigsmall/home"
    stop: str = "/bigsmall/stop"
    emergency_stop: str = "/bigsmall/emergency_stop"
    reset_world: str = "/bigsmall/reset_world"
    load_scenario: str = "/bigsmall/load_scenario"
    inject_fault: str = "/bigsmall/inject_fault"
