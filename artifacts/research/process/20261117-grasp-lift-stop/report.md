# LIFT 异常停止修复与仿真基线复测

固定场景抓放的独立适配器已补齐 LIFT 保持异常停止。源码提交 `41bb33344c0463a979327d0c78e2acd1088b458f`，接续 `4ed5cb50ada7b6b0ca6b3a2fd168aeca637e3cfa`。本轮在 `codex/v4-marker-ambiguity-20261115` 本地交付，公开推送继续暂缓。

保持阶段的普通异常现在先取消待执行目标并急停，再返回 `LIFT_HOLD_FAILED` 和原始原因；故障后的会话不再保留成功终态。取消仍向调用方传播，掉物与竖直路径检查保留原有 hold 行为。详见 [Astra 计划与步骤报告](../20261004-ced-development/astra-rounds/round-lift-hold-exception-stop-20261117/step-report.md) 和 [独立审查](independent-review.md)。

| 检查 | 本轮结果 |
| --- | --- |
| 独立 LIFT 故障注入 | 8 项 RED→GREEN；故障步停止，无后续关节目标 |
| LIFT、物理技能和视觉回归 | 76 passed |
| 冻结源码核验和 Phase 11 | 46 passed；冻结验证器、原 pin 和全局停机断言原样保留 |
| 云候选、复采、几何和最终准入 | 223 passed；seed 43001 新帧准入及 8 步物理成功，对照拒绝保留 |
| 同一固定场景三次完整 worker | 3/3 通过，归档的终帧标记为 OBSERVED |
| 独立物理重算 | 三次均抬升 105.617 mm，持物 3.1875 s，落位稳定 9.4417 s |
| 实测视觉墙钟反馈 | 23.668–37.005 Hz；最慢已接受采样 66.020 ms |
| 连续发送目标 | 每次 1,184 个间隔、4 处交接；最大速度 0.500 rad/s、加速度 1.667 rad/s²（发送目标量） |
| 闭环七项开发长测 | 7/7 通过，253.8–267.0 s/项；原断言及租约行为未修改 |
| UTC 两后端合计 600 s 验收门 | 未通过；新独立诊断与此门分列 |

三项基线调整只涉及检验方式：历史验证测试的正例使用固定兼容源码，当前源码的旧重放仍拒绝；云候选按实际新鲜几何结果验收，保留 REOBSERVE 和独立遮挡等反例；批次归属用例仅隔离无关的后台领取，继续核验真实 API 与 SQLite 的两批 run ID。该批次测试通过不表示生产 dispatcher 的停机行为已改动。[Astra 复测计划](../20261004-ced-development/astra-rounds/round-simulation-baseline-regression-20261117/plan.md) 含原始失败与基线对照。

整库首轮在 `41bb3334` 收集并记账 7,098 个唯一节点：7,010 通过、32 跳过、56 失败，无未记账。55 项因临时目录未满足权限或输出根要求；在同一源码、原断言和独立 `/tmp` 路径复跑全部通过。其余一项为 Phase 12 测试把干净源码误当成实验验收条件：默认 Mock/RGB-D 的 F20 仍正确阻塞，验收证据有缺口。只修正该测试期待，保留生产验证器和正反控制。原分组 [逐节点结论](original-group-regression.json.gz)、[运行回执](evidence/execution/group-receipts.json) 与 [路径复测](evidence/path-preconditions/comparison.json) 分别留存。

Phase 12 追加测试提交 `8a6f7a8e`。干净源码上的原失败节点完整重跑通过；18 条 F20 仍为 RGBD_CAMERA_REQUIRED 阻塞、执行器调用为 0，完整验收状态仍有运行证据缺口。五项快测及两份原件只读断言复核通过。原分组与限定复测去重后，在最终收集的 7,101 个节点中 **7,069 通过、32 跳过、0 未记账**。这是同一生产源码的分组及限定复测结果，涉及两个测试树修订：7,095 个结论来自 `41bb3334`，6 个来自 `8a6f7a8e`；没有单次最终提交全库 JUnit。首轮 56 项失败不从历史移除。[覆盖摘要](regression-coverage-summary.json) · [逐节点及证据来源](regression-coverage.json.gz) · [Phase 12 复测](../20261004-ced-development/astra-rounds/round-phase12-clean-provenance-gap-20261117/step-report.md)。

此前九项未完成均有新开发结果：七项闭环通过，UTC memory 与 SQLite 独立诊断分别用 2,466.62 s、2,468.27 s，通过原断言。两项诊断耗时之和 4,934.89 s，并行诊断不替代正式门。单独的原 600 s 合计门尝试到期，未完成两个节点；该门仍未通过。旧 120 s 非完成和 watchdog 崩溃证据保留。详见 [诊断执行记录](evidence/closure/) 和 [600 s 超时回执](evidence/closure/utc-joint-600s-gate/result.json)。

本轮归档校验重建了 2,313 组配对 RGB-D 帧，并核对安全检查、逐步持物、连续关节指令与源码绑定。[实际运行与回归命令](implementation-receipt.json) · [物理与图像复核](worker-verification.json) · [运行环境](environment.json) · [本地 worker 原始数据清单](worker-raw-manifest.json.gz)。完整本地数据位于 `experiments/results/phase9/grasp-lift-stop-20261117`，worker 原件含 9,873 个常规文件、3 个便利链接和 1.64 GB 文件字节。完整批量数据、运行数据库和模型资产留在本地。

结论限于固定场景 MuJoCo 和模型协议替身。新 seed、真实 Sol/Molmo、真实相机时延、真机、硬实时及正式研究资格尚未验证或授予。[上一轮报告](../20261117-grasp-place-repair/report.md) 与历史原件保持原样。

可将 `41bb3334` 的固定场景用于下一轮 Harness 的仿真示例；UTC 性能门和 Phase 12 运行证据缺口仍需分别处理。
