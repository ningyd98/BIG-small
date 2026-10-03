# 阶段进度

截至 2026-10-04，P1 的 T1/T2 与 P2 的 T6a/T3/T4/T5 已完成各自限定范围的验收。T5 新协议20例离线教师为7成功、12失败、1安全违规；T3 的 Qwen3-VL 4B 经协议和 RGB-D 几何优化后，固定 S01 双图探针 4/4 通过、冻结包只读复核为 `VERIFIED`，见[本轮验收](../../../artifacts/research/process/20261003-t3-small-model-optimization/acceptance.md)。T3 不含物理执行或任意场景泛化验收；T7 已实施并为 `DONE`，最终454项回归及30个源文件Ruff/mypy已通过；T8/T17a为`READY`。六阶段是实际工作分组，依赖满足时允许跨组穿插，不能把表格顺序视为日程或完成声明。详细依赖和验收见[执行计划 §2—3](../../superpowers/plans/2026-10-03-rgbd-evidence-research-roadmap.md)。

| 阶段 | 覆盖任务 | 出口证据 | 当前状态 |
|---|---|---|---|
| P1 来源与观测 | T1、T2 | 来源契约、历史边界、同步 RGB/depth/mask、标定与采集会话；分别记录 SOFTWARE 和 REAL_CAPTURE | T1 `DONE`；T2 `DONE` |
| P2 基础真实闭环 | T6a、T3、T4、T5、T7、T8 | 数据/真实VLM/物理技能；同episode新帧、三值验证与有界路由、独立评价；20场景闭环、120先导及初次冻结 | T6a/T3/T4/T5 `DONE`；T3仅固定S01与当前资产的限定几何门槛，无物理执行；T7 `DONE`，v2 开发 smoke 通过独立复算，最终454项回归通过；T8 `READY` |
| P3 方法与公平基线 | T6b、T9、T10、T11、T12 | 有预算才做10000组；校准风险、决策提交复核、公平事件与B0/B1/B2、候选/provider契约、完整成本账本 | `TODO` |
| P4 恢复与正式协议准备 | T13、T15a、T16a、T17a、T15b | 验证后解决/预算持久化、候选/ACK/启动协调、局部修复/B4、统计工具与界面；独立120先导和最终hash | `TODO` |
| P5 正式评测与结果 | T15c、T16b、T17b | 冻结后 N 场景主比较与消融、固定机会回放、200 故障、区间判定和结果界面 | `TODO` |
| P6 复现与可选扩展 | T18；T14（可选） | 原始记录重建、独立审查和交付；G5 扩展单独冻结，未做时记 `NOT_RUN` | `TODO` |

跨组依赖：T6a 先定义 `SceneSpec`，T5 消费；T8 先接成本账本，T12 复用；T15a 在 T8/T10 后即可与 T11—T13 并行，T16a 随后可做；T17a 在 T6a/T7 后即可做。T15b 必须等待 T13/T15a/T16a；T15c→T16b 严格串行。T17b 的真实结果验收等待 T16b。T14、Isaac 和缓存扩展不阻塞核心 MuJoCo 结论。

闭环修订（2026-10-03）：T7 先定义在线条件、基础事件和有界验证路由，不等待 T12/T13；T11 复用事件，T12 先实现规则/成本 provider，T13 再接入完整恢复。Jev/其他判断模型在 T12/T13 后按独立配置做可选影子/配对实验，不阻塞主方法冻结。该次只修订路线和验收，未改变当时任务状态；后续 T6a 实施另行登记。

阶段状态仅用 `TODO / READY / IN_PROGRESS / BLOCKED / DONE`。`DONE` 必须同时具备所要求的软件验证和对应真实运行证据；模型或渲染不可用时，相关真实验收保持 `BLOCKED`。下一次更新应填写每个已处理任务的实际改动、命令与结果、原始产物、阻塞原因和下一就绪任务，参见[执行日志](execution_log.md)。

P1 验收：来源审计 15 个反例/行为测试、阶段合并 88 项回归、定向 Ruff/mypy 均通过；实际采集 320×240，同一状态三 pass，100 桌面点最大高度误差 2.728 mm，正常及异常退出释放资源。见[机器可读报告](../../../artifacts/research/process/20261003-phase1/phase1-report.json)和[独立审查](../../../artifacts/research/process/20261003-phase1/task-2-review.md)。

T6a 验收：124 项数据测试、123 项既有路径回归、定向 Ruff/mypy（18 文件）及[独立代码审查](../../../artifacts/research/process/20261003-t6a/final-review.md)通过。100/1000个独立组分别为35正/65负、301正/699负，划分为80/5/5/10、800/50/50/100；两批validate/export/replay均通过，见[最终验收](../../../artifacts/research/process/20261003-t6a/acceptance.json)。1000组CLI墙钟1332.669秒，显存采样观测峰值155MiB。T4/T5后续已验收，见[控制器v2](../../../artifacts/research/process/20261003-t4-physical-skills-v2/README.md)与[教师20例](../../../artifacts/research/process/20261003-t5-teacher-accepted/acceptance.md)。T6b的10000组仍为TODO且未运行，等待T8资源预算；T3固定S01门槛现已通过，T7为DONE且已完成开发smoke复算，T8已READY，尚未实施。

T3独立开发扩展另列：两批合计29/32符合各自判据，23/24有目标定位、6/8目标缺失明确拒绝；两条缺失幻觉被几何校验阻断，一条有目标误拒绝，三条均0步契约。32个唯一scene/RGB且无error/missing/duplicate，`all_cases_pass=false`；不调阈值、不算物理成功，失败仍需在T7处理。详见[本轮验收](../../../artifacts/research/process/20261003-t3-small-model-optimization/acceptance.md)。


## 2026-10-04 T7 收尾进展

T7 当前为 `DONE`：共享 backend/episode、新帧、统一三值条件、SafetyShield 前后检查、预算 2/0/3/120、默认 RGBD/VISUAL_PLANNING、真实 VISION_CLOSED_LOOP 与独立 DATASET_GENERATION 已实现。v2 同20 assignments全部保留，2正常成功/18失败/0blocked/0falsecompletion，正常2/12、全分配10%；[独立复算](../../../artifacts/research/process/20261003-t7-visual-closed-loop/smoke-20-v2-validation.json)覆盖34,353样本、154帧、52动作并返回valid/accepted=true。v1全失败、34份源码快照及22,147样本/105帧/33动作保留；diagnostic-03另有在线与物理成功。

模型在[T7新目录](../../../artifacts/research/process/20261003-t7-visual-closed-loop/model-probe/)重探4/4后冻结；历史T3/T5来源不作现行source freeze，T5其余11份源码和物理判据未变、12份历史来源已归档。95 runtime/277 prerequisite是阶段回归数，最终合并为454 passed；最终454项回归、真实worker复查和独立审查均已通过。T8/T17a为READY，T6b保持TODO，10000组和真实硬件未运行，无commit/push。这是当前MuJoCo直立有色方块的开发smoke，不是正式G1。


**T7 最终验收（2026-10-04）：DONE。** 最终 EGL 回归454 passed、1项已有依赖警告，30个源文件Ruff/mypy通过；独立runtime审查无开放P1/P2。真实worker复查1次模型调用、4动作后因抬升保持不足如实FAILED，归档无错误且终态一致。20场景仍为2成功/18失败，未扩大分母；非正式G1。T8/T17a为READY（未实施），T6b为TODO。详见[完整验收](../../../artifacts/research/process/20261003-t7-visual-closed-loop/acceptance.md)。
