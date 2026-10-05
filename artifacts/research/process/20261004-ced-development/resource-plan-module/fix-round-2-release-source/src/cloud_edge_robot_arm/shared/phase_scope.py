"""Phase 范围辅助工具，避免验收脚本误触不属于当前阶段的能力。"""

from __future__ import annotations

ASYNC_RUNTIME = "asyncio"
DETERMINISTIC_TEST_ADAPTER = "MockRobotAdapter"
PHYSICS_SIMULATOR = "MuJoCo"
MODEL_INTEGRATION_ENABLED = False
REAL_ROBOT_INTEGRATION_ENABLED = False
MQTT_INTEGRATION_ENABLED = False
