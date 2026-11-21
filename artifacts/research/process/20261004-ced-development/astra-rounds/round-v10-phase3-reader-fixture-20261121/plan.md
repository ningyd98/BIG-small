# Astra Phase 3 reader fixture 补充计划

本计划由 `gpt-6-astra` 根据本轮新失败与独立审查生成；只规划，不修改生产/测试代码，不运行正式仿真、不提交或推送。基线 HEAD 仍为 `fc6520c04011cd211c4d4c2888f9e3b8fb8cf598`；输入是当前未提交 Phase 3 候选，不是 fc6520c0 原始文件，实施前按下列 SHA256 逐项复核。

## 问题与原始证据

新增 `_Audit.horizons()` 八动作 v10 软件时间图测试两种参数均未到读回断言，即在 `tests/test_native_full_horizon_originals.py:327` 的 `canonical(asdict(result))` 失败：`TypeError: Object of type ActionResult is not JSON serializable`。原始日志未改写，2 failed / 9 deselected；其安全标题、SHA256、字节数及失败节点见 plan.json。

`StepExecutionResult` 是 dataclass，但其嵌套 ActionResult 是 Pydantic 对象，timestamp 是 datetime；asdict 不把它们转换为 JSON 基元。现有 `native_calibration_collection.detached()` 已递归处理 dataclass、Pydantic model 的 JSON 模式与 datetime。因此是新增夹具使用错序列化入口，不应修改 canonical、生产模型或 reader 的严格要求来让夹具通过。

另经当前实现复核，`_v2_receipt` 外层 step_id 仅要求非空；嵌套 controller.step_id 已与实际 step 比较，线上 owned receipt 另有身份核对。新接通 v10 离线调用仍应直接拒绝外层 step_id 错配。这是主计划明确的原件身份负控范围；只在 RationalCompletionHorizonV2 分支增加相等检查，保持 v9/V1 行为。

主任务报告本轮主要门禁 156 passed，广域 33 个旧 SQLite 失败在 fc 基线与候选同样复现；本补充计划不将该报告冒充本补充改动后的结果，必须重跑受到本轮改动影响的测试。

## 限定实施步骤

1. 保留原始两项失败日志与当前输入 hash。复核失败仍是新增夹具 JSON 编码，不把后续新的 reader 失败归到相同根因。
2. 在 `tests/test_native_full_horizon_originals.py` 导入现有 detached，将该新增夹具的序列化改为 `canonical(detached(result)).decode()`。保留 ActionResult 和 timestamp 的真实类型，保留真实字段集合、窗口/尾步/末帧及负控，不改成手拼简化 JSON，不屏蔽 audit.horizons。
3. 运行该参数化测试，预期 False 分支真实执行八动作 horizons 并在绝对 12960 步结束；True 分支必须因不一致 LIFT physics_steps 抛出预期 `controller_lift_hold_incomplete`。仅 JSON 不再失败还不算通过。
4. 在 `tests/test_native_horizon_execution.py` 的真实 V2 receipt/strict decoder 现有夹具增加定点负控：复制合法回执，仅把外层 step_id 改成另一个非空值，嵌套 controller、传入 step、其他字段全部保持。先验证当前实现错误接受该记录（预期 RED）。合法 V2 回执作为正控。
5. 在 `native_full_horizon_recorder.py` 现有 `isinstance(horizon, RationalCompletionHorizonV2)` 分支内添加 `_v2_same(value['step_id'], step.step_id)`，不向 V1 路径移动、不修改外层 receipt schema、不改其他协议策略。重跑正确/错配 V2、原 V1 夹具，错配必须拒绝，合法结果保持。
6. 运行这两个完整测试文件以及原主要门禁；若仅测试增加，主门禁计数可增长，按实际结果记录。检查受影响文件 compile/ruff，保持主计划中的现有基线诊断口径。对新计划外失败保留原始日志并暂停相关修复，交下一 Astra 轮；不能借当前授权修改其他生产边界。
7. 在主轮步骤报告和阶段总结中追加补充计划、实际 RED/GREEN、软件夹具边界及 reader 局限；保持原失败证据不变。只有主任务整体验证完成才执行原授权的精确路径提交推送；本规划任务不执行 Git 写操作。

## 既有完整读回限制

当前 full admissions reader 的注册路径仍依赖 `registered_pose_evaluated_at` / `registered_pose_verdict` 等 v7 式字段，而 v2 admission 生产输出采用另一组字段；这是主任务独立审查确认的相邻既有读回缺口。已有 `_Audit.horizons()` 软件八动作时间图不等于完整 raw 全阶段验收，也不验证 admissions/物理观测真实性。此轮不补造字段、不改 v2 writer、不扩大 admissions reader 适配；阶段报告须明确完整正式 v10 raw、完整 admissions 读回与研究资格均未验收。若软件链必需触达该路径失败，另留原始证据并另行计划。

## 修改清单与禁止范围

生产仅允许 `src/cloud_edge_robot_arm/research/native_full_horizon_recorder.py` 的 V2 外层 step_id 相等检查。测试仅允许 `tests/test_native_full_horizon_originals.py` 的新增夹具序列化修复和 `tests/test_native_horizon_execution.py` 的定点身份负控。本目录 plan.md/json 与主轮安全报告可追加。不得修改 canonical/detached 实现、ActionResult/StepExecutionResult schema、v9 行为、horizon 公式、raw、冻结原件、完整 admissions reader、墙钟/guard/租约/采图机制或正式运行配置。

## 前置条件与验收边界

运行解释器与 PYTHONPATH 必须指向已验证的交付工作树，复核 HEAD/输入 SHA/当前差异。沿用现有软件后端和八动作夹具，不初始化真实 renderer 或正式采集，不接实机/模型。验收为新增八动作测试正负两分支通过、V2 外层 step_id 错配明确拒绝、合法 V2 和旧 V1/v9 不回归、受影响完整测试与主要门禁实际结果已记录。原始错误日志留存，公开只包含 repo-relative 路径、安全摘要和 SHA256，不含本机路径、私有 raw/数据库/日志内容或凭据。SOFTWARE_ONLY；完整真实运行与正式研究资格仍 UNKNOWN/UNASSESSED。

## 输入 SHA256

- `tests/test_native_full_horizon_originals.py` — `6ae868fd8e8726cd6f3f07d15430192d769e9f4b88c22ef6d98556e701bceab4`
- `tests/test_native_horizon_execution.py` — `dd33ab30df0b42769e5d5ac78f51559bb6aff7c2f56ee2cab5f6b249e3142041`
- `src/cloud_edge_robot_arm/research/native_full_horizon_recorder.py` — `d2fd1bc215dba4c174be69463729dc1dd9550f63adefd2ba4fd3eb40d16dff8c`
- `src/cloud_edge_robot_arm/research/native_full_horizon_originals.py` — `89316d77934d97ed1ee61a3b868c173ecdd47aa32b2e3c0a15b534c27195b8e7`
- `src/cloud_edge_robot_arm/research/native_calibration_collection.py` — `c0abbe8922cee0063208ff4b88cf4a0252bb5c5c667022a36fdb9221ea0485d1`
- `src/cloud_edge_robot_arm/research/native_collection_application.py` — `f1a5e2e555fb4bb2f231497754451f0e21cb5c2f3bb5303f965b7db84f562d2c`
- `src/cloud_edge_robot_arm/simulation/mujoco/native_horizon.py` — `d52d7a612544cbddde4a42ba0a2c1e827db2ed12d80f75b29f952e43cc5d38d3`
- `src/cloud_edge_robot_arm/vision/native_completion_horizon.py` — `7a0337c8a44e1d63188957a421dc10a49f4b80b47719d6e9d5a2d5e1382bf0a3`
- `artifacts/research/process/20261004-ced-development/astra-rounds/round-v10-phase3-20261121/plan.md` — `3e4503a288374e32bb95a063beb2291e42cd230d8bed283b2c11421d55058d0a`
- `artifacts/research/process/20261004-ced-development/astra-rounds/round-v10-phase3-20261121/plan.json` — `c0db3d7e282dde5dde6002b946b543d73a39184173d381f17618f0acf57db6ea`

原始失败日志 SHA256：`f5b47ba2fb3f505260aa866a1a897715734c3b8d5c9654098a9dec12e83f0e1f`，2800 字节，原件私有保留。
