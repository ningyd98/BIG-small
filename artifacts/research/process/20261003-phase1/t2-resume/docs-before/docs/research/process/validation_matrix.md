# 验证矩阵

命令取自[执行计划](../../superpowers/plans/2026-10-03-rgbd-evidence-research-roadmap.md)，含待新增测试或 CLI；列在此处不表示当前可运行。`TODO` 表示未取得本轮验收证据；T1 已验收，T2 软件与真实采集均已通过独立审查。软件通过只能证明相应代码契约，真实采集、模型和物理结果须分别出示原始证据。

| 任务 | 关键能力及证据层级 | 主要命令/检查 | 必需原始证据 | 状态 |
|---|---|---|---|---|
| T1 | 历史来源、分母与失败口径；SOFTWARE | `.venv/bin/python -m pytest -q tests/test_research_provenance.py tests/test_phase11_1_simulation_runtime.py` | 审计、回归日志、历史 5580 排除证明 | DONE；15项新单测，合并35项回归，独立复审通过 |
| T2 | 同状态 RGB/depth/mask、标定、session；SOFTWARE + REAL_CAPTURE | `MUJOCO_GL=egl .venv/bin/python -m pytest -q tests/test_rgbd_observations.py tests/test_rgbd_capture_session.py`；Phase9 MuJoCo 回归 | 原始三图、帧/时间/hash、≤5 mm 平面反投影、资源释放 | DONE；三 pass 同状态，100点最大误差2.728 mm，独立审查通过 |
| T3 | 真双图请求、严格解析、模型冻结；SOFTWARE + REAL_VLM | `.venv/bin/python -m pytest -q tests/test_rgbd_planning.py`；待在脚本目录实现 `probe_rgbd_model.py` | 真实请求摘要、权重/配置 hash、延迟/显存 | TODO |
| T4—T5 | actuator/step 抓放；独立评价/教师；SOFTWARE + PHYSICS | `MUJOCO_GL=egl .venv/bin/python -m pytest -q tests/test_rgbd_physical_skills.py tests/test_rgbd_trajectory_dataset.py` | 步数、接触/抬升/稳定、20 episode 正反例及真值隔离 | TODO |
| T6a/b | 数据生产、原子写入、组划分；SOFTWARE + REAL_CAPTURE | `pytest` 的 `test_rgbd_dataset_{labels,integrity,splits,generation,export}.py`；待实现生成/校验 CLI | 100→1000→有预算后10000组 manifest、拒绝项、资源与划分审计 | TODO |
| T7—T8 | 视觉物理闭环、账本、基础先导；REAL_CAPTURE + REAL_VLM + PHYSICS | `pytest` 的 `test_rgbd_{runtime,closed_loop}.py`、`test_research_{protocol,network,pilot,cost_ledger}.py`；待实现 smoke/pilot CLI | 20 闭环、独立 120 先导、全部请求/字节、初次协议 hash | TODO |
| T9—T10 | 校准风险与动作证据/B3；SOFTWARE + 实际来源记录 | `pytest` 的 `test_rgbd_risk_calibration.py test_visual_evidence_contract.py` | 分组隔离、校准图、固定机会 ID/UNKNOWN/误放行原始记录 | TODO |
| T11—T13 | B0/B1/B2、公平事件、联合决策、局部修复/B4；SOFTWARE + PHYSICS | `pytest` 的 `test_runtime_auto_baselines.py test_joint_visual_policy.py test_visual_local_repair.py` | B0 全周期扫描、相同事件与安全边界、成本账本、开发故障轨迹 | TODO |
| T15a、T16a | 分配/功效/统计与分母反例；SOFTWARE | `pytest` 的 `test_research_{assignments,runner,power,statistics,acceptance}.py` | 固定分配、零事件/失败/BLOCKED 反例、区间算法 | TODO |
| T17a/b | 数据与结果界面；SOFTWARE + 实际 E2E | 后端 API 测试；`npm --prefix dashboard run api:generate` 后 typecheck/lint/test/build | 真实 MuJoCo E2E、模型缺失路径；T17b 核对实际结果 | TODO |
| T15b/c、T16b | 最终冻结、正式物理评测、统计；REAL_CAPTURE + REAL_VLM + PHYSICS | 待实现 power/formal/gate-replay/analyze CLI | 独立 120 功效先导、最终 hash、N 全分母、200 故障、区间与负结果 | TODO |
| T18 | 原始记录重建、复现、回归；SOFTWARE + 小批 PHYSICS | 待在脚本目录实现 `reproduce_rgbd_research.py`；ruff/mypy/指定 pytest 与前端检查 | bundle hash、重建一致性、审查记录与限制 | TODO |
| T14（可选） | G5 三采样策略与域外；独立扩展 | 待实现训练 CLI、`test_targeted_rgbd_sampling.py` | 300 域外组×3 seed、同预算及模型 hash；未开展记 NOT_RUN | TODO/可选 |

阶段验收判据：G0 已发生阶段真实路径、泄露和跨集合组重复审计；G1 独立标称层；G2/G2a 对公平 B0；G3 固定机会回放且不冒充物理成功；G4 完整 200 故障；G5 独立扩展。目标数值、区间和统计规则以[研究设计](../../superpowers/specs/2026-10-03-rgbd-evidence-research-design.md)为准。`MOCK`、规划 dry-run、旧 Phase 记录、软件测试均不得填 PHYSICS 分子；硬件列始终 `NOT_STARTED`。
