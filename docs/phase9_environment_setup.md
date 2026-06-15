# Phase 9 Environment Setup

Core Python setup:

```bash
python -m pip install -e '.[dev,sim-mujoco,sim-analysis]'
python scripts/verify_phase9_env.py
python scripts/verify_phase9_mujoco.py
```

ROS 2 / MoveIt 2 require a system installation of ROS 2 Jazzy, `colcon`, `rosdep`, and MoveIt 2 packages. The repository does not run `sudo` automatically.

Isaac Sim must run in its official Python/standalone app environment. Set `ISAAC_SIM_ROOT` and run:

```bash
python scripts/phase9/check_isaac_sim.py
python scripts/verify_phase9_isaac.py
```

Do not install Isaac private dependencies into the BIG-small core virtual environment.
