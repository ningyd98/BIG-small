# Simulation Workspace

Simulation code lives in `src/cloud_edge_robot_arm/simulation`.

Phase 1 includes:

- deterministic `MockRobotAdapter`
- optional `MuJoCoRobotAdapter` dependency guidance

Install MuJoCo support with:

```bash
python -m pip install -e ".[sim]"
```
