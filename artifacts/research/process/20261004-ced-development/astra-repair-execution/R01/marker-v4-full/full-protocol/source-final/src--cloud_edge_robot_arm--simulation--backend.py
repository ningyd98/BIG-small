"""仿真后端抽象或具体实现，区分 Mock、MuJoCo、Isaac 和 dry-run。"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from cloud_edge_robot_arm.contracts import Pose
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import (
    ContactSnapshot,
    GripperCommand,
    JointCommand,
    JointStateSnapshot,
    PhysicalFault,
    PhysicalScenarioConfig,
    SensorFrame,
    SimulationStepResult,
)


@runtime_checkable
class SimulatorBackend(Protocol):
    def initialize(self, config: SimulatorConfig) -> None: ...

    def reset(self, scenario: PhysicalScenarioConfig) -> None: ...

    def step(self, steps: int = 1) -> SimulationStepResult: ...

    def shutdown(self) -> None: ...

    def get_sim_time(self) -> float: ...

    def get_joint_state(self) -> JointStateSnapshot: ...

    def get_tcp_pose(self) -> Pose: ...

    def get_contacts(self) -> list[ContactSnapshot]: ...

    def get_sensor_frame(self) -> SensorFrame: ...

    def apply_joint_targets(self, targets: JointCommand) -> None: ...

    def apply_gripper_command(self, command: GripperCommand) -> None: ...

    def emergency_stop(self) -> None: ...

    def inject_fault(self, fault: PhysicalFault) -> None: ...
