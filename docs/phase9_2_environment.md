# Phase 9.2 环境

Phase 9.2 需要兼容 Isaac 的主机：

- Ubuntu 24.04。
- NVIDIA RTX GPU。
- NVIDIA 驱动可见 CUDA。
- `vulkaninfo --summary` 可用。
- Isaac Sim 6.0 官方 standalone runtime 或官方容器。
- 已有 Phase 9.1 运行路径所需的 ROS 2 Jazzy。

运行：

```bash
# 命令说明：按本文上下文运行该验证或环境命令，默认不连接真实机械臂。
python scripts/verify_phase9_2_environment.py --output artifacts/phase9_2/environment
```

验证器会写入：

- `compatibility_report.json`
- `compatibility_report.md`
- `nvidia_smi.txt`
- `vulkan_summary.txt`
- `isaac_compatibility_checker.log`

报告记录 OS、CPU、内存、磁盘、GPU、VRAM/driver 输出、CUDA 可见性、Vulkan 状态、display/EGL 变量、Isaac runtime 模式、Isaac Python 路径、相关容器镜像/摘要，以及 ROS 环境变量。

如果缺少任何必需主机能力，状态为 `BLOCKED_BY_ENV`。这不是通过，也不能当成 Isaac runtime 验证。

## Standalone 模式

```bash
# 命令说明：按本文上下文运行该验证或环境命令，默认不连接真实机械臂。
export ISAAC_RUNTIME_MODE=standalone
export ISAAC_SIM_ROOT=/path/to/isaac-sim-6.0
python scripts/verify_phase9_2_environment.py --output artifacts/phase9_2/environment
```

检查器优先使用 `${ISAAC_SIM_ROOT}/python.sh scripts/phase9/isaac_standalone_app.py --check-imports`。本地 Isaac pip/venv runtime 会退回到 `${ISAAC_SIM_ROOT}/bin/python`。

## 容器模式

```bash
# 命令说明：按本文上下文运行该验证或环境命令，默认不连接真实机械臂。
export ISAAC_RUNTIME_MODE=container
export ISAAC_CONTAINER_IMAGE=nvcr.io/nvidia/isaac-sim:6.0.0
export ISAAC_CONTAINER_DIGEST=sha256:<resolved-digest>
python scripts/verify_phase9_2_environment.py --output artifacts/phase9_2/environment
```

容器模式记录固定镜像和 digest。命令构造会拒绝浮动的 `latest` tag。
