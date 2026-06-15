# Phase 9 Environment Setup

Phase 9 and Phase 9.1 keep three runtime environments separate:

- Core Python: BIG-small source, tests, MuJoCo core validation, and experiment tooling.
- ROS 2 workspace: `/opt/ros/jazzy` plus `ros2_ws/install`, sourced only for ROS and MoveIt validation.
- Isaac Sim runtime: official Isaac Sim Python/standalone app selected by `ISAAC_SIM_ROOT`.

Do not install Isaac Sim private dependencies into the BIG-small core Python environment.

## Core Python

```bash
python -m pip install -e '.[dev,sim-mujoco,sim-analysis]'
python scripts/verify_phase9_env.py
python scripts/verify_phase9_mujoco.py
```

## ROS 2 Jazzy and MoveIt 2

The install script defaults to dry-run and writes an auditable plan without using `sudo`:

```bash
scripts/phase9/install_ros2_jazzy.sh --artifact-dir artifacts/phase9_1/install
```

On Ubuntu 24.04 with explicit sudo permission:

```bash
scripts/phase9/install_ros2_jazzy.sh --execute --yes --artifact-dir artifacts/phase9_1/install
source /opt/ros/jazzy/setup.bash
scripts/phase9/build_ros2_workspace.sh
python scripts/verify_phase9_1_ros2_integration.py
python scripts/verify_phase9_1_moveit_safety.py
```

Installed packages include ROS 2 Jazzy desktop, `ros-dev-tools`, `colcon`, `rosdep`, MoveIt 2, Panda MoveIt resources, robot state publishers, TF2, and Fast DDS RMW support.

## Vulkan Runtime

Isaac Sim compatibility requires a working Vulkan runtime and `vulkaninfo`:

```bash
scripts/phase9/install_vulkan_runtime.sh --artifact-dir artifacts/phase9_1/install
scripts/phase9/install_vulkan_runtime.sh --execute --yes --artifact-dir artifacts/phase9_1/install
```

The execute mode installs `vulkan-tools` and Mesa Vulkan ICD packages. NVIDIA driver installation remains host-specific and must be handled by the operator or image builder.

## Isaac Sim

Isaac Sim must run in its official Python/standalone app environment. Set `ISAAC_SIM_ROOT` and run:

```bash
ARTIFACT_DIR=artifacts/phase9_1/install python scripts/phase9/check_isaac_sim.py
python scripts/verify_phase9_1_isaac_smoke.py
```

If the verifier reports `BLOCKED_BY_ENV`, the result is not an Isaac validation pass.
