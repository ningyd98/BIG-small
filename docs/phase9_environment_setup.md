# Phase 9 环境准备

Phase 9 和 Phase 9.1 把三类运行环境分开：

- 核心 Python：BIG-small 源码、测试、MuJoCo 核心验证和实验工具。
- ROS 2 工作区：`/opt/ros/jazzy` 加上 `ros2_ws/install`，只在 ROS 和 MoveIt 验证时 source。
- Isaac Sim 运行时：由 `ISAAC_SIM_ROOT` 指定的官方 Isaac Sim Python/standalone app。

不要把 Isaac Sim 私有依赖装进 BIG-small 的核心 Python 环境。

## 核心 Python

```bash
# 命令说明：按本文上下文运行该验证或环境命令，默认不连接真实机械臂。
python -m pip install -e '.[dev,sim-mujoco,sim-analysis]'
python scripts/verify_phase9_env.py
python scripts/verify_phase9_mujoco.py
```

## ROS 2 Jazzy 和 MoveIt 2

安装脚本默认 dry-run，并且会写审计计划，不会用 `sudo`：

```bash
# 命令说明：按本文上下文运行该验证或环境命令，默认不连接真实机械臂。
scripts/phase9/install_ros2_jazzy.sh --artifact-dir artifacts/phase9_1/install
```

在 Ubuntu 24.04 上并且明确允许 sudo 时：

```bash
# 命令说明：按本文上下文运行该验证或环境命令，默认不连接真实机械臂。
scripts/phase9/install_ros2_jazzy.sh --execute --yes --artifact-dir artifacts/phase9_1/install
source /opt/ros/jazzy/setup.bash
scripts/phase9/build_ros2_workspace.sh
python scripts/verify_phase9_1_ros2_integration.py
python scripts/verify_phase9_1_moveit_safety.py
```

安装内容包括 ROS 2 Jazzy desktop、`ros-dev-tools`、`colcon`、`rosdep`、MoveIt 2、Panda MoveIt 资源、robot state publisher、TF2 和 Fast DDS RMW 支持。

## Vulkan 运行时

Isaac Sim 兼容性需要可用的 Vulkan 运行时和 `vulkaninfo`：

```bash
# 命令说明：按本文上下文运行该验证或环境命令，默认不连接真实机械臂。
scripts/phase9/install_vulkan_runtime.sh --artifact-dir artifacts/phase9_1/install
scripts/phase9/install_vulkan_runtime.sh --execute --yes --artifact-dir artifacts/phase9_1/install
```

执行模式会安装 `vulkan-tools` 和 Mesa Vulkan ICD 包。NVIDIA 驱动安装仍然取决于主机，由操作员或镜像构建者处理。

## Isaac Sim

Isaac Sim 必须运行在官方 Python/standalone app 环境中。设置 `ISAAC_SIM_ROOT` 后运行：

```bash
# 命令说明：按本文上下文运行该验证或环境命令，默认不连接真实机械臂。
ARTIFACT_DIR=artifacts/phase9_1/install python scripts/phase9/check_isaac_sim.py
python scripts/verify_phase9_1_isaac_smoke.py
```

如果验证器报告 `BLOCKED_BY_ENV`，那不是 Isaac 验证通过。
