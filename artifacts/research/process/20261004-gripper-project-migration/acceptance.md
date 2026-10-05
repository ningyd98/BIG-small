# 夹爪修复应用到全项目

2026-10-04，按用户“将修复应用到全项目”授权，现行默认入口已统一使用 `mujoco_upright_box_v2` 资产标定与同一份来源绑定的模型冻结。真实双图探针4/4及默认工作台链路验证通过。在线任务质量仍未达标：20例仅2成功，保留2误完成及3例物理安全违规。

## 改动范围

- [共享默认定义](../../../../src/cloud_edge_robot_arm/vision/defaults.py)统一模型标签、模型配置和当前冻结目录。模型仍为已安装的 `qwen3-vl-candidate:4b-instruct`，Q4_K_M、320×240双图、normalized_1000；未训练或下载新权重。
- 无active profile且无显式模型环境选择时，模型工厂、HTTP/WS工作台与运行worker使用当前共享冻结。显式active profile、显式冻结目录和显式原始provider/model环境选择保留优先级；显式空冻结目录保留原始未标定模式。
- 默认API使用延迟解析器，启动、采集和无模型数据操作不提前加载冻结；真正规划时仍严格验真，冻结缺失或来源漂移不回退。能力接口在解析前报告UNRESOLVED，避免把默认标签当作已选模型。
- Linux启动环境、两份环境示例、探针CLI、离线评估CLI、visual_smoke及两份pilot开发配置改用共享冻结；normalized模型配置改用v2。没有改变场景seed、分层、评分门槛或执行速度，也没有重跑120例pilot。
- S01语义引用使用实际snapshot的grasp_profile及对应资产摘要，标准版本为 `s01-task-semantics-v2`。v1历史标定保留注册，未知/未标定profile返回UNKNOWN；语言白名单与在线、物理、语义的成功合取保持原规则。
- 冻结来源绑定新增defaults、frozen_model、task_semantics；对应独立测试来源清单同步更新。README、闭环说明和当前状态索引说明迁移入口与历史边界。

当前资产SHA-256为 `66a0e27047e530a141259f1d74155d404d71a4d7cae4520f7e0c87140dbe87e2`。物理开爪控制仍统一使用39mm目标、40mm硬限位；旧几何与旧冻结仅代表历史验收时点。

## 实际验证

| 验证 | 结果 | 证据 |
| --- | --- | --- |
| 默认CLI真实双图探针 | 4/4 PASS，本地GPU调用，冻结及来源验真通过 | [日志](model-probe.log)、[当前冻结](model-probe/model-frozen.json)、[验真](model-verify.log) |
| 默认在线smoke | 20预分配全部保留，2成功/18失败，正常2/12，0 blocked，2误完成 | [摘要](smoke-20/summary.json)、[原始日志](smoke.log) |
| 独立物理复算 | valid=true/errors=[]，50,310样本，3例HARD_JOINT_LIMIT | [校验](smoke-validation.json)、[脚本](audit_smoke.py) |
| 实际HTTP工作台→模型工厂→worker | 202提交，1模型调用/8动作，语义引用v2；硬限位违规后FAILED | [校验](workbench-validation.json)、[运行日志](workbench-v2.log)、[运行记录](workbench-v2/run.json) |
| 默认入口、覆盖规则及API/worker相关定向回归 | 63 passed；最后默认入口12 passed | [相关回归](focused-regression.log)、[最后默认回归](defaults-final.log) |
| 大范围后端回归 | 首轮715项：702 passed、13 failed；13项均为来源清单夹具遗漏新增模块 | [完整日志](backend-regression.log) |
| 来源清单修正后的相关复测 | 52 passed，覆盖全部13个失败项及最终默认入口 | [复测](source-binding-retest.log) |
| 前端 | 12文件30测试通过，typecheck/build/lint通过 | [测试](frontend-tests.log)、[构建](frontend-build.log)、[lint](frontend-lint.log) |
| 静态检查 | 定向Ruff、9个生产/脚本文件范围内mypy、启动脚本bash语法及差异检查通过 | [Ruff](ruff.log)、[mypy](mypy.log) |
| 独立迁移审查 | 无开放Critical/Important/Minor | [审查](review.md) |

回归批次互有重叠，不相加为独立测试总数。首轮大回归的13个失败来自 `tests/test_rgbd_model_probe.py` 独立来源清单仍只有旧模块，生产验真已包括新增模块；修正夹具后覆盖这些失败的52项全部通过。依赖警告为已有Starlette/anyio弃用提示。全包mypy的两个已知无关错误未纳入本次范围内通过声明。

smoke_passed=true仅表示弱开发门“全20例保留、至少1正常成功、至少1失败、无环境阻塞”。它不表示在线质量通过。物理复算的3例硬限位违规均完整保留，两例在线报告完成但最终合取失败，登记为误完成。目标缺失4例中仍有2例执行动作；无误完成不能推断无误操作。真实工作台也出现硬限位违规，虽达到抬升、保持、放稳门槛仍失败。本轮未调节控制器或放宽这些判据。

第一次独立工作台验证脚本因直接运行时缺少仓库根目录的scripts包而失败，原[失败日志](workbench.log)保留；验证脚本加入仓库根目录后，在新的workbench-v2目录完成实际运行。这是验证脚本导入修正。

## 历史与证据边界

[原教师修复](../20261004-t5-gripper-fix/acceptance.md)的19/19正常案例及39/40新随机案例保持原结论；本次迁移未改动教师生产链12个绑定来源，原数据审计仍有效。原教师修复模型冻结的来源已因本次迁移发生合法变化，不能作为当前共享源码冻结；其文件与验收内容原样保留，以本目录新冻结为当前入口。

旧v1注册、历史数据manifest、原T7/T8冻结、原验收与已生成pilot结果未覆写。旧开发配置归档在[config-history](config-history/)；当前使用的源码、配置和测试快照及摘要见[source-manifest.json](source-manifest.json)。本工作区包含其他预存开发修改，快照记录当前文件全貌，不意味着本次迁移拥有这些文件的全部差异。已有active profile数据库未修改。

范围为当前MuJoCo资产、默认开发入口与标定身份一致性。教师验证针对60–70mm直立刚性方块；80mm最大控制开口不证明名义50–90mm感知分布均可抓取。在线结果未通过正式G1，不升级T8、T6b全量数据或真实硬件结论；未commit/push。

## 复核与使用

```bash
.venv/bin/python scripts/probe_rgbd_model.py --verify-frozen
.venv/bin/python artifacts/research/process/20261004-gripper-project-migration/audit_smoke.py
```

当前冻结缺失或源码绑定改变时，先用 `MUJOCO_GL=egl .venv/bin/python scripts/probe_rgbd_model.py` 重新生成并验真，再执行默认在线规划。历史证据不可覆写；新smoke/工作台复测需另选输出目录。使用说明见[RGB-D闭环说明](../../../../docs/rgbd_visual_closed_loop.md)。
