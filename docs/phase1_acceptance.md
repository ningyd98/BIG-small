# Phase 1 验收

## 状态

以下命令通过，并且未开始 Phase 2 工作时，Phase 1 视为完成。

## 验收项

| 项目 | 状态 | 证据 |
| --- | --- | --- |
| 统一 `RobotAdapter` 接口 | 完成 | `src/cloud_edge_robot_arm/edge/robot_adapter.py` |
| 确定性 `MockRobotAdapter` | 完成 | `src/cloud_edge_robot_arm/simulation/mock_robot.py` |
| 动作时长模拟 | 完成 | `default_action_duration_ms` |
| 动作超时处理 | 完成 | `ACTION_TIMEOUT` 测试 |
| 故障注入套件 | 完成 | `FaultCode` 和 `scripts/run_fault_injection_suite.py` |
| 可选 MuJoCo adapter | 完成 | `src/cloud_edge_robot_arm/simulation/mujoco_adapter.py` |
| MuJoCo 安装说明 | 完成 | `python -m pip install -e ".[sim]"` |
| 固定抓放流程 | 完成 | `src/cloud_edge_robot_arm/edge/fixed_pick_place.py` |
| 20 次确定性验收 | 完成 | `scripts/run_fixed_pick_place.py --repeat 20` |
| 视觉模型 | 阻塞 | 明确不在 Phase 1 范围内 |
| 云端 planner | 阻塞 | 明确不在 Phase 1 范围内 |
| MQTT | 阻塞 | 明确不在 Phase 1 范围内 |

## 命令

```bash
python scripts/run_fixed_pick_place.py --adapter mock
python scripts/run_fixed_pick_place.py --adapter mock --repeat 20
python scripts/run_fault_injection_suite.py
```
