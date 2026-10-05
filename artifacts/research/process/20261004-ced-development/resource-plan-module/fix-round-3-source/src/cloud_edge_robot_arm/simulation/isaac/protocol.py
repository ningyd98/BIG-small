"""Isaac 通信协议模型，限制前端或服务只能发送受控仿真消息。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ISAAC_PROTOCOL_VERSION = "bigsmall-isaac-jsonl-v1"
REQUIRED_CAPABILITIES = frozenset(
    {
        "joint_state",
        "tcp_pose",
        "rgb_camera",
        "depth_camera",
        "contacts",
        "follow_joint_trajectory",
    }
)


@dataclass(frozen=True)
class IsaacCommand:
    command_type: str
    payload: dict[str, object]
    command_seq: int

    def to_jsonable(self) -> dict[str, object]:
        return {
            "command_type": self.command_type,
            "payload": self.payload,
            "command_seq": self.command_seq,
        }


@dataclass(frozen=True)
class IsaacStatus:
    status: str
    sim_time_s: float
    message: str


@dataclass(frozen=True)
class IsaacHandshake:
    backend: Literal["isaac_sim"]
    runtime: Literal["isaac_standalone"]
    status: str
    sim_time_s: float
    ros_time_s: float
    sensor_timestamp_s: float
    message: str
    capabilities: frozenset[str]

    def to_status(self) -> IsaacStatus:
        return IsaacStatus(status=self.status, sim_time_s=self.sim_time_s, message=self.message)
