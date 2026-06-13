# Shared Workspace

Shared Phase 0/1 constants live in `src/cloud_edge_robot_arm/shared`.

Frozen Phase 0/1 route:

- Async runtime: Python `asyncio`
- Deterministic tests: `MockRobotAdapter`
- Physics simulation target: MuJoCo
- Cloud model calls: disabled
- MQTT: disabled
- Real robot control: disabled
