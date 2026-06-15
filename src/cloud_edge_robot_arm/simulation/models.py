from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from cloud_edge_robot_arm.contracts import Pose


@dataclass(frozen=True)
class JointStateSnapshot:
    names: list[str]
    positions: list[float]
    velocities: list[float]
    efforts: list[float]
    sim_time_s: float


@dataclass(frozen=True)
class ContactSnapshot:
    geom1: str
    geom2: str
    impulse: float
    position: Pose
    sim_time_s: float
    expected: bool = False
    illegal: bool = False


@dataclass(frozen=True)
class SensorFrame:
    frame_id: str
    sim_time_s: float
    width: int
    height: int
    rgb: bytes | None = None
    depth: tuple[float, ...] = ()
    object_detections: list[dict[str, object]] = field(default_factory=list)
    latency_ms: float = 0.0
    ground_truth_used_for_control: bool = False


@dataclass(frozen=True)
class JointCommand:
    positions: list[float]
    max_velocity: float = 1.0
    timeout_s: float = 5.0


@dataclass(frozen=True)
class GripperCommand:
    open: bool
    force_n: float = 30.0
    timeout_s: float = 1.0


class PhysicalFaultType(StrEnum):
    PAYLOAD_MASS_VARIATION = "PAYLOAD_MASS_VARIATION"
    FRICTION_VARIATION = "FRICTION_VARIATION"
    ACTUATOR_DELAY = "ACTUATOR_DELAY"
    CAMERA_NOISE = "CAMERA_NOISE"
    OBJECT_SLIP = "OBJECT_SLIP"
    EMERGENCY_STOP = "EMERGENCY_STOP"


@dataclass(frozen=True)
class PhysicalFault:
    fault_type: PhysicalFaultType
    parameters: dict[str, float | int | str | bool] = field(default_factory=dict)


@dataclass(frozen=True)
class PhysicalScenarioConfig:
    scenario_id: str
    seed: int
    object_mass_kg: float = 0.08
    friction_coefficient: float = 0.8
    table_height_m: float = 0.0
    object_pose: Pose = field(default_factory=lambda: Pose(x=0.45, y=0.0, z=0.035))
    target_region_pose: Pose = field(default_factory=lambda: Pose(x=0.2, y=0.25, z=0.035))
    max_episode_s: float = 60.0

    @classmethod
    def scenario(cls, scenario_id: str, *, seed: int) -> PhysicalScenarioConfig:
        if scenario_id == "S21_OBJECT_SLIP_AFTER_LIFT":
            return cls(scenario_id=scenario_id, seed=seed, friction_coefficient=0.12)
        if scenario_id == "S16_PAYLOAD_MASS_VARIATION":
            return cls(scenario_id=scenario_id, seed=seed, object_mass_kg=0.22)
        return cls(scenario_id=scenario_id, seed=seed)


@dataclass(frozen=True)
class SimulationStepResult:
    sim_time_s: float
    physics_steps: int
    contacts: list[ContactSnapshot]
    sensor_frame: SensorFrame


@dataclass(frozen=True)
class PhysicalTrialResult:
    scenario_id: str
    seed: int
    randomization_level: str
    result_hash: str
    metrics: dict[str, float | int | str | bool]
