# RGB-D 研究证据清单（P1，2026-10-03）

本清单冻结已有证据的适用范围。来源记录模型见 `src/cloud_edge_robot_arm/research/models.py`；审计入口为 `audit_provenance`。新研究运行须标记 `cohort=NEW_RESEARCH`，逐条记录源码树、场景组与 split、模型快照、RGB-D 观测哈希、物理步数、阶段来源和任务结果。旧证据只能标记 `HISTORICAL`，不得移入新研究的成功率分母。

| 证据 | 当前判定 | 对新研究的作用 |
| --- | --- | --- |
| `artifacts/phase11_1/verification`、Phase 11.1 历史 verifier | `PHASE11_1_SIMULATION_RUNTIME_ACCEPTED`（原口径） | 软件/旧仿真运行时验收；`LEGACY_PIPELINE` fixture 不证明 RGB-D 物理闭环 |
| `artifacts/phase12_2_clean/validation` | 540 条 validation，466 runtime-completed、74 运行前阻塞（原口径） | 保留历史复现，不能转为新物理试验 |
| 干净 `d571e1b0` full 原始实验 | 5,580 行；5,040 runtime-completed、540 blocked-before-runtime；`PHASE12_REJECTED` | 保留历史原始数据和拒绝结论；新物理分母贡献 0 |
| `da299bd9` 独立重分析 | 180 对中 120 对满足旧标量规则，60 对含安全停止；full 仍拒绝 | 仅解释旧统计，不能声称公平跨引擎物理配对 |
| 本轮 P1 新 RGB-D 研究 | 尚无正式运行记录；verifier-gated authoritative thesis run count = **0** | 成功率分母和分子均为 0；待后续阶段产生真实来源记录 |

新试验即使在模型加载、观测或动作前阻塞，也保留在新试验成功率分母；感知、推理、动作三个核心阶段各须显式记录一次。未执行阶段写 `NOT_EXECUTED`，物理步数写 0，不虚构动作。已发生阶段须有 `REAL` 状态和来源哈希，只有 `PHYSICS`、正物理步数、真实模型与观测来源、无阻塞或在线真值泄露、任务确实成功的记录才进入物理成功分子。跨方法使用同一正式场景组可用于配对；同组进入不同 split 是泄露。同一 run ID 的重复输入不扩张分母，并在审计中列出。审计输出包含阶段覆盖、各已发生阶段真实性、泄露数、跨 split 组、阻塞原因与记录问题。

真实机械臂验证仍为 `NOT_STARTED`，最高硬件验收级别为 `NONE`。上述软件或仿真验收均不构成真实硬件运动声明。权威状态以 [`docs/current_authoritative_status.md`](../current_authoritative_status.md) 为准。
