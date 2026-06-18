"""MuJoCo 仿真包，封装本地物理后端和只在仿真内执行的控制接口。"""

from __future__ import annotations

from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend

__all__ = ["MuJoCoPhysicsBackend"]
