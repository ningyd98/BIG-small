# Phase 1 Acceptance

## Status

Phase 1 is complete when the commands below pass without starting Phase 2 work.

## Acceptance Items

| Item | Status | Evidence |
| --- | --- | --- |
| Unified `RobotAdapter` interface | COMPLETE | `src/cloud_edge_robot_arm/edge/robot_adapter.py` |
| Deterministic `MockRobotAdapter` | COMPLETE | `src/cloud_edge_robot_arm/simulation/mock_robot.py` |
| Action duration simulation | COMPLETE | `default_action_duration_ms` |
| Action timeout handling | COMPLETE | `ACTION_TIMEOUT` tests |
| Fault injection suite | COMPLETE | `FaultCode` and `scripts/run_fault_injection_suite.py` |
| Optional MuJoCo adapter | COMPLETE | `src/cloud_edge_robot_arm/simulation/mujoco_adapter.py` |
| MuJoCo install guidance | COMPLETE | `python -m pip install -e ".[sim]"` |
| Fixed pick-place flow | COMPLETE | `src/cloud_edge_robot_arm/edge/fixed_pick_place.py` |
| 20-run deterministic acceptance | COMPLETE | `scripts/run_fixed_pick_place.py --repeat 20` |
| Vision model | BLOCKED | Intentionally out of Phase 1 |
| Cloud planner | BLOCKED | Intentionally out of Phase 1 |
| MQTT | BLOCKED | Intentionally out of Phase 1 |

## Commands

```bash
python scripts/run_fixed_pick_place.py --adapter mock
python scripts/run_fixed_pick_place.py --adapter mock --repeat 20
python scripts/run_fault_injection_suite.py
```
