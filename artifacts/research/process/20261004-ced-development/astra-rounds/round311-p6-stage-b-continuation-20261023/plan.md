# R311：P6B 内部 T2 四个剩余行为节点接续计划

**实际规划模型：gpt-6-astra。状态：仅规划、未执行。**

## 目标与依据

补齐原 R158 T2 七节点中尚无当前接受证据的四节点。R307 的双库4提交失效+4重启+1同owner，以及 R302 的 Memory/SQLite wait 已通过，直接复用；三个微回归不计作 T2 行为节点。R251 GREEN9 覆盖晚绑定竞争、legacy与取消控制，不替代完整36接口 writer及预算节点。R258父GREEN7原结果为FF/600秒终止、无JUnit，不能为后四项补造通过。

R196 T1 有受限软件验收；完整 T2 还需 fresh 审阅，T3不提前启动。当前没有新证据证明应修改产品，因此本轮实施内容是完成必要的T2行为出口；遇新失败后另轮Astra限定修复。

输入HEAD `942d82343e97e53dbbd8b96309a393ca6836a496`，分支 `research/20261004-continuation`；输入SHA、当前源与旧耗用额度、证据映射见 input-observation.json。用户已明确授权“执行本轮必要的定向验证（推荐）”。

## 精确范围与顺序

| 新身份 | 原节点（tests/test_operational_runtime_closure.py） | 场景 |
|---|---|---|
| R311.budget_memory | test_original_budget_debit_not_refilled_by_retry[memory] | 正常提交、真实COMMIT后关闭，实际续租与不回填 |
| R311.budget_sqlite | test_original_budget_debit_not_refilled_by_retry[sqlite] | 同上，真实SQLite event后端 |
| R311.writer_memory | test_b_local_writer_requires_private_scope[memory] | 私有正控制、36公开写入接口拒绝、精确取消 |
| R311.writer_sqlite | test_b_local_writer_requires_private_scope[sqlite] | 同上，真实SQLite event后端 |

每项一次、重试0，child600秒、outer900秒、原cleanup15秒；串行，ROOT接受前一项后才释放下一项。四个新身份与旧SPENT隔离；原六PASS、GREEN7及整仓测试均不重跑。精确argv/env/output已冻结在plan.json。

## 实施与独立复核

- [ ] 同一实际Sol `/root/runtime_repair_sol` 新建R311 compact runner和AUTHOR账本；ROOT绑定实际席位。以已执行过的R302 runner为模板，仅改轮次身份、PLAN_SHA、四个KEYS和文字计数；保留R296原helper。新键均是behavior，必须建立resources、严格保留basetemp，不能进入unit或dual被动插件分支。
- [ ] ROOT一次复核完整差分、源/argv及绑定，创建本轮source-gate/acceptance/ROOT账本；不重建通用门禁，不递归历史审计。产品、fixture、旧runner/plugin及旧账本一字不改。
- [ ] ROOT逐键预留，Sol逐键执行；完整保存真实调用、退出、JUnit、两流、每案例、资源、关闭后的DB/sidecar、前后源pin。完整字段级验收见JSON；budget各2案例，writer各1案例，共预期6个实际poll。
- [ ] ROOT独立检查真实断言完成、资源清理和数据库证据；新失败保留并停止后续相关运行，交实际Astra；不预授权猜修、TTL/等待放宽或断言削弱。

## 出口、下一步与交付

四项通过后，生成 `t2-exit-coverage.json`，将原七节点映射到3个已接受运行及4个新运行，状态仅为 `T2_BEHAVIOR_MATRIX_COMPLETE_REVIEW_PENDING`。R158/R258 fresh T2审阅仍是T3前置；原未耗用12批须真实独立席位绑定，不在本计划冒用旧身份或消费。全P6B、native、标定、T12及正式验收均不提升。

本轮新事实写R311 step-report/phase-summary，历史全局STATE/PHASE保持。历史35DB/90sidecar缺口保留；不以新库抵消。所有已启动运行结算后按明确路径提交推送，并核对三SHA；DB与批量raw沿原边界，超大JSON沿已接受无损压缩交付方式保留原件。无需用户再次批准研发方向。
