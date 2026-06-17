# Phase 9.2 Isaac 后端

Isaac 后端分成两部分：

- `scripts/phase9/isaac_standalone_app.py`：运行在 Isaac Python 内，负责 `SimulationApp` 生命周期。
- `IsaacSimBackend`：留在核心 Python 中，通过 JSONL 协议通信。

standalone app 支持：

- `--check-imports`：启动 Isaac `SimulationApp` 并报告就绪状态，但不声明验证通过。
- JSONL handshake，以及 `reset_world`、`step`、`follow_joint_trajectory`、`sensor_request`、`emergency_stop`、`shutdown` 命令。
- `--smoke --output artifacts/phase9_2/isaac`：执行真实最小 smoke 序列并写入 artifact。

必需 smoke artifact：

- `isaac_smoke_evidence.json`
- `isaac_verification.json`
- `isaac_commands.log`
- `process_stdout.log`
- `process_stderr.log`
- `stage_metadata.json`
- `robot_state_sample.json`
- `rgb_sample.png`
- `depth_sample.npy`
- `contact_sample.json`

只有真实 Isaac run 完成以下动作时，才允许输出 `ISAAC_SMOKE_VALIDATED`：加载 stage、推进 physics、采样 robot state、RGB、depth 和 contact 数据、完成 reset 与 emergency stop，并留下干净日志。传感器缺失、physics step 为 0、provenance 缺失、日志包含禁止标记，或使用 replay/static runtime evidence，都会产生 `INCOMPLETE`。

普通 CI 测试只覆盖源码和协议契约。真实 runtime 测试必须在 Isaac 兼容 runner 上使用 `pytest -m isaac_runtime`。
