# V3 离线安全边界与运行环境补充计划

规划模型：`gpt-6-astra`。状态：**PLAN_ONLY_NOT_IMPLEMENTED**。本轮扩展上一阶段计划，原计划及其补充字节保持不变。本轮没有修复代码、执行测试、启动仿真或模型。

## 已核实的失败

`/tmp/bigsmall-v4-execution/offline-all-01.log`：1 failed、41 passed、1 deselected。POST 期待 PRE→EXECUTE→POST，实际 calls 为空。三例 PRE、POST、HARD 原始 episode 均已完整复制到 evidence/failed-faults/。

三例均在 planning-stage-01 返回 `FROZEN_POINT_INPUT_MISMATCH`，terminal reason 为 `COMPONENT_INITIAL_PLANNING_REJECTED`，point/cloud=0/0，执行0，safety_checks为空。因此 PRE/HARD 的原“零执行”断言是假通过，不能证明门禁有效。POST 尚有被遮蔽的字段错误：生产输出是 `marker_frames`，测试读取 `frames`。

三个默认沙箱故障样本 before RGB SHA均为 `ba49d16b639b2281a83b8dfb79d876b817b5c0aa41b6ea2f65da5cc79b1ba7c0`；原 V3 与成功 first-case-02 均为 `9ab94dd324217955be622aee20d802a13b41247e76294bad975b2993950f2915`。深度也不同：失败 `078d726944f8f5bf4c9db8e3a01b4856eba93aa3e755169ba3edd82cd030b3f0`，历史及成功 `83ab1980a700e50381fbe5429e19ed31c4f5b15af3a649ac99043afc02320713`。三例与历史 intrinsics、camera_to_world、calibration_version、sim_time_s 等元数据相同。

first-case-02 结果独立确认成功8动作、4次冻结point、1次冻结cloud、无网络尝试。其审批提升执行由父任务报告；结果文件本身不证明权限来源。EGL设备、驱动/库可见性或pytest导入初始化顺序差异仍是**假设**；无GL厂商/设备对照，不能写成已证 NVIDIA 原因。旧64项测试通过不证明真实冻结输入匹配。

## 限定修改

只加强新增 `tests/test_sol_molmo_offline_regression.py` 的安全故障测试。必要时可在原计划内新增 offline module/CLI 加只读运行receipt；不修改绑定逻辑、生产loop、controller、physics、evaluator、AST白名单、相机、MSAA、noise、seed及任何容差。

所有故障用例先断言真实两阶段规划通过、point=4/cloud=1、零真实模型load/generation/request、网络尝试为空。记录注入命中数，检查真实 SafetyShield verdict 原本通过后再注入拒绝。严禁用其他规划错误的零执行冒充门禁。

| 边界 | 必须命中与终止 | 禁止继续 |
|---|---|---|
| PRE | PRE恰1，唯一拒绝check，`SAFETY_SHIELD_PRE_REJECTED_OR_LIMITED` | EXECUTE/POST均0，actions空、执行0 |
| HARD | 首动作前hard-state注入恰1，`INJECTED_HARD_STATE`，规划及pre-00帧已完成 | PRE/EXECUTE/POST均0，actions/checks空、执行0 |
| POST | PRE→EXECUTE→POST各1；同一contract及resolved step；`SAFETY_SHIELD_POST_REJECTED_OR_LIMITED` | 执行恰1，无settle、post-00、后续pre动作、terminal-stability；finally after允许 |

POST 帧断言纠正为 `marker_frames`。公共断言必须明确 worker FAILED、component_success=false、diagnostic_complete=false，精确终止原因为上表之一。增加早期规划失败负对照，使本轮三份原失败证据全部无法满足门禁验收。测试小helper可复用断言，但不建立第二套执行器，不mock整个planner/backend。

## 运行前置与顺序

先复核 inputs.json SHA、源码pin、配置版本2与完整configuration hash及可选scene补充仍适用。共享venv的editable源会指向原主树，因此在解释器启动前显式PYTHONPATH=隔离树/src:隔离树，并assert每个生产模块真实路径和SHA。使用现有headless MuJoCo/EGL与cv2.aruco，启动前 `MUJOCO_GL=egl`、`PYTHONDONTWRITEBYTECODE=1`，禁pytest缓存，输出唯一新/tmp目录。

先保存 RED：旧三份规划失败都应被新严格断言拒绝。再只运行原三个 fault node，可由父任务按授权向工具申请 require_escalated；这不授权网络或真实模型，NetworkDenyGuard保持启用。如果审核拒绝不得绕过。如果提升后仍不匹配，保留失败并停止受影响27批次，收集证据交下一轮Astra；不调整图像、深度、渲染参数或hash匹配。

建议新进程命令（这是未来复跑命令；原日志没有记录完整原argv）：

```sh
PYTHONDONTWRITEBYTECODE=1 MUJOCO_GL=egl \
PYTHONPATH=/home/ningyd/.codex/worktrees/v4-marker-ambiguity/BIGsmall/src:/home/ningyd/.codex/worktrees/v4-marker-ambiguity/BIGsmall \
BIGSMALL_V3_REGRESSION_ROOT=/home/ningyd/Documents/Codex/2026-11-14/x20-gpu-nvidia-smi-nvml-gpu/outputs/next-round-repair-40-20261115-v3 \
/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python -m pytest -p no:cacheprovider \
--basetemp=/tmp/bigsmall-offline-safety-green-01 \
 'tests/test_sol_molmo_offline_regression.py::test_actual_worker_stops_at_injected_safety_boundary[PRE]' \
 'tests/test_sol_molmo_offline_regression.py::test_actual_worker_stops_at_injected_safety_boundary[POST]' \
 'tests/test_sol_molmo_offline_regression.py::test_actual_worker_stops_at_injected_safety_boundary[HARD]' -q
```

cwd为 `/home/ningyd/.codex/worktrees/v4-marker-ambiguity/BIGsmall`。路径已存在时选择新编号，不能清理原失败。若仅参数范围不影响故障条件，可将三个node分别新进程运行并逐一保存日志。

receipt记录允许列表环境（MUJOCO_GL、PYOPENGL_PLATFORM、MUJOCO_EGL_DEVICE_ID、EGL_DEVICE_ID、LIBGL_ALWAYS_SOFTWARE；缺值记null）、executable/cwd/sys.path/argv、依赖版本/来源、source SHA、实际工具权限审核结果引用。禁止倾倒全env或读取凭据。GL信息仅可只读已有context，不能为receipt另建renderer/context或改变设备；拿不到就标unknown。审批上下文由外部报告绑定，不能让进程凭空声称自己在某沙箱。

三例达到真实门禁后，原27逐例以实际已匹配的相同执行环境启动新进程；每例仍须严格验证四份point输入与完整cloud请求，环境标签及首例成功不替代逐例验证。任何失败保留，分母27、预期27/27不变。独立review与已有微小RGB/query/phase/cloud改动拒绝测试也须通过。

## 验收与冻结

不新增真实Sol/Molmo率、付费/网络调用或硬件；不修改0.1mm/39mm标准。589帧冻结审计、软件故障测试、27离线新闭环分别报告。此前全项目600秒超时及5个未命名F仍为未完成，不被本轮通过覆盖。原始失败、first-case-02、历史V3、原计划及source snapshots不覆盖。输入或范围变化须先重新核对；出现新计划外失败暂停相关修复，再交Astra。

所有输入绝对路径、字节数、SHA256与不可覆盖副本见 inputs.json；包内全部文件由 SHA256SUMS 绑定。
