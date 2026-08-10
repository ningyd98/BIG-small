# macOS 本地开发

`codex/macos-local-dev` 支持在 Apple Silicon Mac 上直接开发 BIG-small 的核心 Python、MuJoCo、Rerun Viewer、FastAPI 和 React Dashboard。首次启动只需要一条命令：

```bash
./scripts/macos/dev.sh
```

第一次运行会创建仓库内的 `.venv`，安装 `dev`、`sim-mujoco`、`sim-analysis`、`sim-observability` Python extras，执行 `npm ci`，初始化本地 SQLite，并验证前后端构建。安装完成后会启动：

- Workbench：`http://127.0.0.1:5173/simulation/workbench`
- FastAPI 文档：`http://127.0.0.1:8000/docs`
- 仿真后端：MuJoCo，macOS 图形后端为 `glfw`

两个服务都只绑定 loopback；按 `Ctrl-C` 会同时回收 FastAPI 与 Vite 子进程。

## 前置条件

- 原生 Apple Silicon Terminal，不能在 Rosetta shell 中运行。
- Homebrew。脚本会在缺少运行时时安装 `python@3.12` 和 `node@22`，但不会自动安装 Homebrew 本身。
- 推荐安装 Xcode Command Line Tools；缺失时执行 `xcode-select --install`。

如果已经通过 pyenv、asdf 或其他方式安装 Python 3.12+ 和 Node 22.12+，脚本会直接复用。也可以用 `BIGSMALL_PYTHON` 指定 Python。

## 分步使用

```bash
# 只查看将执行的安装计划，不改动系统。
./scripts/macos/install.sh --dry-run

# 安装或幂等更新依赖。
./scripts/macos/install.sh

# 只读环境诊断。
./scripts/macos/doctor.sh

# 启动开发服务；可选禁止自动打开浏览器。
./scripts/macos/start.sh --no-open
```

端口可通过参数或 `.env.macos.local` 修改：

```bash
./scripts/macos/start.sh --backend-port 8010 --frontend-port 5180
```

安装脚本仅在 `.env.macos.local` 不存在时从 `.env.macos.example` 创建它，之后不会覆盖本地配置。该文件已被 Git 忽略，不要在其中保存或提交真实控制器地址、operator token 或 API 密钥。

## 平台边界

macOS 本地能力包括 Mock、MuJoCo、MjSpec 动态参数、domain randomization、Sim/Real gap report、Rerun artifact、Dashboard 与多数软件测试。

Isaac Sim/Isaac Lab workstation runtime 要求 Linux/Windows 与 NVIDIA RTX GPU，因此不由此脚本安装；在 macOS 上可以继续编辑和生成 Isaac 对等随机化配置，再到远程 Linux RTX 主机做运行验证。ROS 2 Jazzy/MoveIt 2 的权威运行环境仍是 Ubuntu 24.04，也不会被 macOS 安装脚本伪装为已验收。

所有 macOS 入口保持 `RUNTIME_PROFILE=simulation`，不安装真实机械臂 SDK，不写入真实控制器，也不改变 Level 0+ 现场验收门禁。
