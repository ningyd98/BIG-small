from __future__ import annotations

import os
from pathlib import Path

from cloud_edge_robot_arm.simulation.isaac.protocol import IsaacStatus


class IsaacSimClient:
    """Independent-process Isaac Sim client guard.

    The core package never imports Isaac private modules. A compatible host runs
    the standalone Isaac app and communicates over ROS 2 or the bridge protocol.
    """

    def check_status(self) -> IsaacStatus:
        root = os.environ.get("ISAAC_SIM_ROOT", "")
        if not root or not Path(root).exists():
            return IsaacStatus(
                status="BLOCKED_BY_ENV",
                sim_time_s=0.0,
                message="ISAAC_SIM_ROOT is unset or missing",
            )
        return IsaacStatus(status="READY_TO_CONNECT", sim_time_s=0.0, message=root)
