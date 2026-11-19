# P0 组件 worker 异常证据

GPT-6.2 Astra 计划基点为 `b3fc6213aad819e2cc46a77a972de242d195a065`。GPT-6.2 Sol 实施前复核 7 个输入与 `plan.md` 的 SHA256，均与 `plan.json` 一致。1803 冻结原件仍为 `ValueError`、`step-01 MOVE_ABOVE` 在 `INITIALIZING`、已执行动作 0。该次原始栈已丢失。本轮软件注入的栈独立保存。

## RED 与实施

- `pytest-red.txt` 保留 4 个预期 `KeyError: 'exception'`。通过真实单场景入口与 SQLite worker 覆盖规划安全停止、首次采集加后置采集双故障、外层初始化故障、视觉伺服初始化故障。原有终态、成本和停机关联断言先通过。
- 在 `run_component_episode` 现有异常处理及 `component/episode.json` 写入链路中记录 `exception`，后续失败记录于 `secondary_exceptions`。阶段随初始化、规划、PRE、视觉伺服初始化、控制器、POST、末端稳定及收尾更新。已取得的步号和技能随动作阶段记录。
- traceback 从原始异常帧读取文件位置、函数和行号。仓内 `src`/`tests` 使用相对路径，其余帧使用模块名。安全消息由异常类型与已知完整文本匹配，其他消息使用 `[redacted]`。诊断采集失败时继续原有停止和写入链路。入口参数校验、原文件创建顺序、外层 worker 既有错误码和 `backend.shutdown()` 行为沿用现有逻辑。新增字段适用于进入现有 episode 持久化范围的异常。

## 验证结果

- `MUJOCO_GL=egl ../../../.venv/bin/python -m pytest -q tests/test_sol_molmo_component_safety.py tests/test_sol_molmo_worker_integration.py` 通过 35 项。首次定向合跑未在进程启动前设置 EGL，MuJoCo 在 `Renderer.__init__` 以 134 退出，随后按真实软件前置设置 EGL 后复验通过。`pytest-first-abort-redacted.txt` 保存脱敏运行输出，原始字节保存在工作树 `cache/local-verification/20261119-worker-docs/pytest-first-abort.local.log`，SHA256 `2dd3dbe5cd1b1959a41b7014287cc10de7b8bb56ee1629eb07563153add0fa8e`。
- `archive-validation.json` 从 8 份真实 worker 软件夹具的已落盘 episode 读出终态、物理结果、计数、脱敏诊断和原件 SHA256。初始化及双故障夹具在任何请求前停止，云与定位计数均为 0。伺服初始化夹具经 1 个 HTTP 协议替身响应和 4 次 RGB 点位夹具调用后停止，保留 `step-01` 和 `MOVE_ABOVE`。真实供应商请求、原生神经网络生成、物理硬件派发合计均为 0。
- 核对 `safe_stop → shutdown` 调用次序、单独 after 失败与双故障首因优先、常规和伺服正控，以及 `ComponentStopped` 的原停止理由。测试包含自定义 `__str__` 会抛错的异常，路径与凭据 sentinel 在新存档中均缺席。
- 定向 Ruff 与 `git diff --check` 通过。1803 冻结证据 SHA256 复核通过。真实组件批次与正式研究资格仍由各自验收证据决定。
