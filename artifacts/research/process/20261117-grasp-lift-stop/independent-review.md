# 独立只读审查：LIFT 保持异常与仿真基线测试

审查日期：2026-11-17。工作树：`/home/ningyd/.codex/worktrees/v4-marker-ambiguity/BIGsmall`。对比基线：`4ed5cb50ada7b6b0ca6b3a2fd168aeca637e3cfa`。

## 结论与问题分级

未发现本次五文件 diff 引入的可复现 P0/P1/P2/P3 缺陷，无阻断项。此结论基于代码审查、两份 Astra 计划和既有原生测试证据核对，不等同于完整 worker 故障注入验证、最终整库 GREEN、真机安全或研究验收。审查没有修改源文件、运行测试/渲染/API/真机、提交或推送；仅在指定 `/tmp` 账本写入本报告。

## LIFT 异常、停止与计步

- 原始 probe 明确是独立无渲染适配器：1821 步 observer 失败后无停止命令，最后目标在1820步，estop=false，session仍为SUCCEEDED，目标/反馈差0.014529058112937115 rad。修复针对这个实际缺口，没有把 worker 外层 safe_stop 视为独立适配器保障。
- `skill_robot.py:181–212` 在运动成功后记录 backend 步计数，try 覆盖 context建立/退出、guard、step、contacts、monitor_hold 与最终TCP测量。`213–225` 保留领域错误的 hold 策略，其它异常先直接 backend.emergency_stop，随后更新终态；非 Exception 的 BaseException 用 bare raise 重抛，未转成普通失败结果。
- `skill_robot.py:226–242` 同时保留原始 reason/exception_type、LIFT_HOLD phase、当前 session 终态，并以 backend counter delta 包含已完成但 observer失败的物理步。`robot_adapter.py:53–72` 将这些 details 同时放入 ActionResult 和 StructuredError。
- `backend.py:1202–1247` 的 stop 清空队列、目标取当前反馈、设置estop并应用控制，不推进物理步。成功分支 `skill_robot.py:244–257` 无 finally stop，保留0.5秒、接触、提升门槛与目标交接。
- 新测试 `test_visual_servo_control.py:178–316` 检查停止步不增加、故障后无joint_target、队列清空、目标等于反馈、普通原始原因、同一BaseException对象与领域代码。原有 `:146` 保持视觉cadence、`:370` 垂直通道、`:437–492` transport/place姿态及连续命令速度/加速度交接测试未被放宽。

## 独立适配器与完整 worker 的契约区别

只读追踪 `edge/runtime/skill_executor.py:114–123`：适配器普通失败直接传递其 error 与 action_result，不执行成功条件。`research/sol_molmo_components.py:972–985` 会归档 controller_result 和返回步，遇失败立即抛 CONTROLLER_FAILURE:LIFT_HOLD_FAILED，因此不会进入后续 post-action settle 或下一动作；`:1008–1012` 的外层 safe_stop 是额外停止。session终态会在`:995–1002`归档。BaseException不被普通Exception层吞掉，适配器已先停止，worker外层finally仍负责证据/关闭。

现有新增故障测试只证明独立适配器局部契约；cloud三场景证明完整worker正常/REOBSERVE路线，但没有在完整worker中注入本次LIFT故障。因此这里仅有静态兼容性结论，不报告完整worker故障路径已动态验收。backend stop 或 snapshot 本身异常属于 Astra 明确排除的下一轮根因，不在本轮结构化返回保证内。

## 三个基线测试调整

- `test_finger_limit_verification.py:143–173` 从固定真实Git对象5e68导出兼容current-side，并用本地对象alternates保留真实52df解析；没有替换BASE_COMMIT、原pin函数、guard AST或verifier成功值。缓存进入/退出均清理。`:222–246`八个损坏例精确匹配对应pin/inventory错误且禁止物理初始化/输出；`:249–258`保留evidence-only范围；`:261–271`单独确认当前真实树仍拒绝旧运行来源漂移。生产verifier及冻结原件未改。
- `test_phase11_1_simulation_runtime.py:845–891` 只在该单项局部禁止后台线程start，仍真实API/SQLite提交；检查不同batch、相同manifest、精确run_ids、两组不交和仓库batch归属。第二次提交之后第一批结果仍等于第一响应run_ids。该测试不再覆盖后台执行，也不能据其通过宣称生产stop竞态修复。
- `test_sol_molmo_cloud_fallback.py:52–56,119–145` 仅将43001旧负例改成已证据支持的成功场景；仍要求物理成功、8动作、一次请求/reservation/native call、UNKNOWN_NOT_GRANTED。新增stage1仅候选、owned refresh、stage2最终admission、fresh id/checksum、同episode/calibration、post-cloud绑定、hardware_dispatch=false。REOBSERVE仍要求0动作。
- 负例边界继续存在且未修改：`test_cloud_vision_fallback.py:224–248`外圈遮挡/原始深度与复用/episode/calibration拒绝；`test_molmo_grounded_planner.py:599,756,824,864,1014`遮挡/深度/过期/复用/绑定等控制。223例账本覆盖这些文件；没有通过删assert或改生产阈值使43001通过。

## 验证证据核对

以下为已存在原生pytest XML/退出码的独立解析；本审查未重跑，也未将它们冒充最终整库快照。

| 账本 | 用例 | failure/error | skip | exit | XML SHA256 |
|---|---:|---:|---:|---:|---|
| `lift-red` | 8 | 8 | 0 | 1 | `4082e2bfa958c02a73316e3ec59a3c768067b6a19a8747a8ebbe3eaec98321ff` |
| `lift-green-final` | 76 | 0 | 0 | 0 | `4e2aa0b58d6131707dc7c27db67e66e21d337f3105e9eac8ffc680af8ba0d20b` |
| `baseline-green` | 46 | 0 | 0 | 0 | `4754aa9bf820310fb254078b71d2f88ad88dd22f8eb6843711e4f65302582a3f` |
| `cloud-green` | 223 | 0 | 0 | 0 | `569b6d7a53886768ff70e2476bf1b2fca71e245f231b433628540dcc12fc942a` |

RED八项分别是step(visual/nonvisual)、feedback(ValueError/RuntimeError)、BaseException(step/sample)、guard(GRASP_LOST/CLEARANCE_PATH_VIOLATION)。GREEN日志为76 passed in 8.85s，baseline为46 passed in 41.03s，cloud为223 passed in32.20s；未观察到skip计为通过。

## 审查输入SHA256

- `src/cloud_edge_robot_arm/simulation/mujoco/skill_robot.py`：`ab0755515ea49b1d27d38ff0022df6ba99a08a8465c0577756278573be397cc0`
- `tests/test_visual_servo_control.py`：`eb57c24b7ceb92bcb48874dbd91dd4446fd209c9aea9dff5c60561ee4ba7e1c4`
- `tests/test_finger_limit_verification.py`：`6fe808485b61645ac7f1dc1f1265af88e6cb7baaec4256602a643504d89a5d6f`
- `tests/test_phase11_1_simulation_runtime.py`：`d736a67436b0dc845f32379004bf46a238a0f5a84a4f099be674fdb575f68d4b`
- `tests/test_sol_molmo_cloud_fallback.py`：`7d134c532650acd92af6bbce51c8cf929e548bedc10ccce833e160aca10ceb20`

计划参考：`artifacts/research/process/20261004-ced-development/astra-rounds/round-lift-hold-exception-stop-20261117/plan.md` 与 `round-simulation-baseline-regression-20261117/plan.md`。本审查未生成新的 Astra 计划，因为未发现需修复的新问题。
