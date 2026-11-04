# R421 模拟恢复租约与归档一致性 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: 延续R419的 `superpowers:executing-plans`。用户已授权修复；本轮是实际Astra对新证据的限定补充，不再询问执行方式。

**Goal:** 让adapter自建的模拟crashed租约在真实过期后、恢复执行与归档前，通过现有公开API完成严格限界的释放；同时修正未释放租约观测器。

**Architecture:** 保留 main→recovery→duplicate 顺序，在recovery probe的expiry与requeue之间补精确旧owner清理。严格collector与worker归档检查保持；新档案从生成时就一致，旧失败不重写。软件完成、任务成功和研究资格仍分开。

**Tech Stack:** Python、pytest、真实SQLiteSimulationJobRepository公开API、SimulationWorker、ArtifactRecoveryService。

**Spec:** 根AGENTS、R418/R419/R420已授权计划、本轮 `intake/observation.json`。Planner=`gpt-6-astra`。

**状态：PLANNED_NOT_IMPLEMENTED。本规划未测试、未执行SQL、未改产品/测试/Git。**

## Global Constraints

- 修改限 `src/cloud_edge_robot_arm/final_evaluation/adapters/simulation_runtime.py` 与 `tests/test_phase11_adapter_receipt_truthfulness.py`。
- 不改repository/worker/recovery service、归档/collector严格条件、guard、模式、TTL、timeout或原等待1.05秒。
- 不把expired当released，不关新owner租约，不在归档后补写released/consistent，不改旧raw/DB/JUnit/预期来获得通过。
- R420显式关闭修复保留；剩余R419指标与真实legacy正对照仍须完成，不能用BLOCKED路径通过替代。
- R419/R420/R421针对性结果合并一次最终fresh Astra review，不增加helper审查链，不重跑全suite/full5580。

## Review Focus

- 过期只改变job状态，不能证明lease释放：以真实release API和新archive证明（Task1/2）。
- 已替换owner、错job/lease、未过期：零release调用并拒绝继续恢复（Task2负例）。
- 观测器NULL谓词漏计空串：用实际NOT NULL schema的未释放正控制（Task1）。
- 其它probe失败掩盖corruption用例：要求只main无效、recovery/duplicate有效及具体错误（Task3）。
- 归档生成后再清理不能修旧一致性：检查old lease release早于replacement acquire，且独立recovery归档前不运行duplicate（Task1/3）。

---

## 证据结论与选择

现有未损坏native输出 `FAILED/FINALIZATION` 是正确的保守结果：recovery原件里的旧 `phase12-worker-crashed` lease `released_at=""`，`evidence_consistency.lease_released=false/consistent=false`。第一attempt确实INTERRUPTED，第二attempt为BLOCKED_BY_ENV。严格collector发现这些缺口，不应放宽。

源码显示 `expire_leases()` 仅以旧owner/lease/expiry CAS将job转为INTERRUPTED；不会填released_at。RecoveryService负责结束旧attempt和requeue，也没有释放历史legacy租约。恢复worker只释放自己新取得的租约；归档一致性要求所有历史lease释放。adapter手工构造模拟crashed worker并没有真实活跃线程，却漏掉自己创建的旧lease清理。这是可在adapter自身限定修正的生命周期缺口，不意味着通用生产恢复逻辑已被修复。

**新增静态确认：** `_unreleased_lease_count` 查询 `released_at IS NULL`，但实际表是 `released_at TEXT NOT NULL DEFAULT ''`，未释放值为空串。原audit的`unreleased_leases=0`不能证明旧lease已释放；没有证据支持“后续duplicate清理了它”。保留该旧字段原字节，在新报告中明确这项口径错误。R420已测的FD关闭结果不因此失效，但其lease=0结论需新的正确计数复验。

**收据类型语义已核对：** repository `_lease_from_row` 经 `_parse_optional_dt` 把SQL空串或NULL转为Python `None`，真实非空时间转为datetime。因此现有main的 `released_lease_count = sum(released_at is not None)` 和collector的 `bool(leases) and all(released_at is not None)` 判定正确；worker写archive时又把None写回空串。此次collector确实正确拒绝了未释放的recovery，不能把它改成按expires_at判断。新native断言须联接typed list、archive空串/非空值、main released count和collector lease_released：旧RED旧lease=None/collector=false，新GREEN真实datetime/归档非空且计数一致。把这些断言并入已列原生case，不增加运行次数。根执行者应在新步骤/阶段报告撤回此前由NULL-only计数推导的“lease全部清空”，保留旧audit；FD关闭证据仍单独有效。

**决策：** 在adapter确认旧模拟租约确已过期且仍为原owner后，调用现有 `release_lease(exact_lease_id)`，然后原样执行recovery/replacement worker。保持probe顺序，不改BLOCKED预期，不忽略consistent=false。不通过“后面DB看起来清了”覆盖先前冻结的不一致归档。

## Task 1：独立RED与观测器修正

- [ ] 新增 `test_unreleased_lease_observer_counts_empty_sentinel`：新scratch DB使用实际 `released_at TEXT NOT NULL DEFAULT ''` 形态，2条空串+1条真实释放时间。setup显式close后，观测器应计2且无FD；当前NULL-only实际0为预期语义RED。只查询新测试DB。
- [ ] 新增 `test_recovery_archives_expired_simulated_lease_as_released`：直接用真实repo/Worker执行 `_run_recovery_job`，尚不运行duplicate。先保存返回值、lease/attempt/consistency原件与hash，再断言精确旧lease已释放且早于第二lease acquired、全部lease释放、attempt1 INTERRUPTED/attempt2 BLOCKED、`consistent=true`。当前空串和consistent=false为预期RED。
- [ ] 两case各一次，保留真实phase/exit/JUnit。不得用“helper未定义”的import失败冒充RED；后续helper负例在实现后独立GREEN验证。
- [ ] 只修测试观测器谓词为 `released_at = '' OR released_at IS NULL` 或等价COALESCE，保持finally close。真实NOT NULL schema以空串为准；不加expiry过滤，不只计当前lease。

## Task 2：限定清理自己的已过期模拟旧lease

**接口：** 保留 `_run_recovery_job(repo, context, artifact_root) -> dict[str, Any]` 原签名/键。新增：

`_release_expired_simulated_crash_lease(repo: SQLiteSimulationJobRepository, *, run_id: str, lease: SimulationJobLease, interrupted_jobs: list[str]) -> dict[str, Any]`

`lease`必须为该probe刚创建并捕获的 `phase12-worker-crashed` lease。调用点在 `interrupted = repo.expire_leases()` 返回后、`ArtifactRecoveryService(...).recover_interrupted_jobs()` 之前；不在sleep期间或worker执行期间持锁。

- [ ] 在公开 `repo.publication_guard()` 内fresh读取当前job和该run全部lease；这是多个顺序公开root调用，不开启私有事务、不在另一个public mutation内部注入写入。
- [ ] 核对本次`interrupted_jobs`包含job；job仍INTERRUPTED且run/job/lease/worker与捕获值一致；精确lease行唯一、job/worker/acquired_at一致、released_at仍None；该lease及job的expires_at都非空且不晚于fresh UTC now。检查原captured worker为本probe模拟worker。
- [ ] 任何未过期、已替换/重入队/取消/终态、错身份、已释放等异常都抛出明确RuntimeError，停止后续requeue，不调用release，也不试探释放别的lease。不得更改全局时钟或私有状态以使检查成立。
- [ ] 仅一次调用 `repo.release_lease(lease.lease_id)`；仍在public guard内回读，确认相同lease的released_at非空，job仍原INTERRUPTED/owner身份。真正释放时间由现有API写入，不能用expires_at或回填时间代替。
- [ ] 释放证明加入新recovery receipt的 `simulated_crash_cleanup`：确切job/run/lease/worker、原acquired/expires、expiry确认、前后released_at与身份不变。明确为adapter模拟场景的清理，不是自动生产恢复或任务执行证明。
- [ ] 保留旧 `lease_expired`、recovered_jobs列表、first attempt及转换；然后原样调用recovery、实际worker与collector。不得后写leases.jsonl或consistent字段；新的worker归档生成时即必须一致。
- [ ] 新增 `test_simulated_crash_cleanup_rejects_wrong_or_live_owner[not_expired|not_interrupted|wrong_run|wrong_job|replacement_lease|wrong_worker|already_released]`，使用纯边界fixture断言每个反例release_calls为空并拒绝。真正公开API正对照由原生test证明，不能只靠fixture测试宣称运行恢复。

## Task 3：确认归档、状态与错误归因均真实

- [ ] 正确计数控制及7个helper负例各一次GREEN；独立原生recovery归档case一次GREEN。新archive精确旧lease release时间必须早于replacement lease acquire，全部lease释放、consistent=true，expiry/attempt历史保留。
- [ ] 原 `test_current_rgbd_mock_blocker_propagates_from_native_receipts` 一次GREEN，原BLOCKED期待不改；加强断言三probe `execution_evidence.evidence_valid=true`，recovery真实归档一致。计数用修正谓词，FD在observer前后均空，thread/lease检查同时有效。调用/完成/任务/权威仍false。
- [ ] 原native corruption三case一次复验，并加`consistency_false`第四case：仅在本次新main归档中把consistent置false。必须断言`invalid_probes`仅main、recovery/duplicate有效，以及各自错误：hash→`artifact_hash_manifest_mismatch`，identity→`runtime_job_identity_mismatch`，attempt→`artifact_attempt_mismatch_or_incomplete`，consistent=false→`terminal_consistency_identity_or_status_mismatch`。外层仍FAILED/FINALIZATION。
- [ ] 原三项只断外层FAILED的GREEN保留，但不能单独当特定损坏检测成立：当时recovery也无效。新的隔离断言排除这种掩盖。只改新测试注入文件，绝不动旧原件；原测试身份/attempt攻击重算新fixture hash的机制不扩散到产品。
- [ ] 检查source范围、旧hash、owned cleanup及R420FD关闭未回退；当前17 pure投影PASS证据保留，不把它当原生修复证明。随后继续R419尚未完成指标/legacy正对照，再联合最终fresh Astra review。

## 次数、路径与运行前置

本补充最多 **2个新RED case（1pure/1native）+14个GREEN case（8pure/6native）**，各一次、零自动重试。pure每node120秒、native每node600秒，owned cleanup30秒；这是上限，不是耗时承诺。R419其它剩余任务仍按原计划，精确新证据满足两计划时复用，避免重复跑。

复用冻结R419 run_stage/R413 bounded_stage；每stage一个精确node，独占新目录：

- `R419/validation/r421-red-observer-empty`、`r421-red-recovery-archive`。
- `r421-green-observer-empty`、`r421-green-cleanup-{case}`、`r421-green-recovery-archive`。
- `r421-green-native-blocked`、`r421-green-native-corruption-{case}`。

已存在目录不得删/重用，只能记录新唯一后缀。R421报告引用这些路径。每stage记录当前批准adapter/test新pins，其余原1309范围保持；不以合法修改冒充漂移，也不重新基线化其它文件。绝对项目`.venv/bin/python`、现有依赖、新DB/artifact/basetemp、无共享SIMULATION_RUNTIME_DB、无旧运行SQL/网络/模型/硬件。保留TTL1、sleep1.05、job30秒及worker既定TTL，不改变主机时钟。仅PID+starttime+scope的owned清理，无全局kill或补造JUnit。

## 验收与停止线

验收要求新原生归档产生时已经真实一致，公开API确实释放了精确过期模拟旧lease；未知/已换owner一律拒绝；正确观测器不漏计空串。未损坏默认RGBD+MOCK保持真实BLOCKED，损坏/consistent=false保持FAILED，不恢复SUCCESS或论文资格。

若公开API拒绝安全释放、需要私有SQL/guard越权、归档仍不一致、出现其它未释放lease/FD/时序根因或超时，停止相关修复并由实际Astra另轮规划，不扩大到repo/worker。也不通过改旧BLOCKED预期结束问题。真实LEGACY正常路径尚未执行；它若不能取得完整一致证据，P0仍只能部分收口。

所有R413失败、R419原RED与本次FAILED、R420四FD原audit及新FD证据、旧错误lease计数原字段均保留。新增报告澄清口径，不改原件。本规划仅两文件，实施交付沿用精确路径normal push与三处SHA；DB/raw依旧本地边界，不宣称完整远端复现。

## 输入pins

| 路径 | bytes | SHA256 |
| --- | ---: | --- |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round419-phase11-receipt-truthfulness-20261104/validation/green-projection/result.json` | 403 | `1400a14772ba11740d25f912c0075b64e839ad77f1e8a85e0331d16f05d23ee8` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round419-phase11-receipt-truthfulness-20261104/validation/green-native/result.json` | 399 | `8d99b13d1d3cd8a9be596ad816cdef8bd1c59c90490fe854c9cba858e6b02e75` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round419-phase11-receipt-truthfulness-20261104/validation/green-native/pytest-events.jsonl` | 5056 | `0c6cadacc79de34989386d1fd006ad2f2fc3fc22228c43a28b4bc26e0eca0f8b` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round419-phase11-receipt-truthfulness-20261104/validation/green-native/native-blocked-audit.json` | 567 | `dfb61a845a18b8313af3077cd78ffd653353f54bbf6f703633dd43af755f0fda` |
| `/tmp/bigsmall-r419-green-native/test_current_rgbd_mock_blocker0/output/source_evidence/r419-receipt-proof/phase11_runtime_actual_run.json` | 22763 | `3d7dec81ddac30d89835b58b241ab7f9a87ac2a75aa264e2dc92727c58d87616` |
| `/tmp/bigsmall-r419-green-native/test_current_rgbd_mock_blocker0/output/source_evidence/r419-receipt-proof/phase11_runtime/artifacts/phase11_1/runtime/r419-receipt-proof-recovery/evidence_consistency.json` | 2453 | `5856994ed8412ef5cadb1f0b17f41928ed6aa6922a1a310d83ea068ae59c675b` |
| `/tmp/bigsmall-r419-green-native/test_current_rgbd_mock_blocker0/output/source_evidence/r419-receipt-proof/phase11_runtime/artifacts/phase11_1/runtime/r419-receipt-proof-recovery/leases.jsonl` | 602 | `3a1d9c5ca6919f2ff29b320b052f252c53a7f7f734484b316ed72bb69f58b845` |
| `/tmp/bigsmall-r419-green-native/test_current_rgbd_mock_blocker0/output/source_evidence/r419-receipt-proof/phase11_runtime/artifacts/phase11_1/runtime/r419-receipt-proof-recovery/attempts.jsonl` | 504 | `af83f5416091b4b9d9e088d1f86ab496e3b0101921b7655c911341eb891ae7f0` |
| `src/cloud_edge_robot_arm/final_evaluation/adapters/simulation_runtime.py` | 29883 | `da9c988bf43b3d4a02778f651881dc15a805c07b87cf936eb0dd8b145d1eb23d` |
| `tests/test_phase11_adapter_receipt_truthfulness.py` | 17357 | `c34a5426ec293b8183055fd812330751236b42ed118ae16e3ad133bfa263910c` |
| `AGENTS.md` | 1774 | `8567e10635a650e2619905d6b3a6e0a885812060fecb1cdd4487bbf118593649` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round421-phase11-recovery-archival-lease-consistency-20261104/intake/observation.json` | 14139 | `7a1dc2e0142efe519c658e83ec2725fe138b9fde7eb629d13c5ad88fe2e3e53b` |
| `src/cloud_edge_robot_arm/simulation_runtime/sqlite_repository.py` | 138430 | `6e1ae6471e5d75c195057e1f8e1f90854b1efcfe21f21660bd0a7d75a6d21eb2` |
| `src/cloud_edge_robot_arm/simulation_runtime/recovery.py` | 4575 | `aac4ad5c0a88d051c1b753523cfa71fabd48062f6aaebb5427ab57cdc9cecbea` |
| `src/cloud_edge_robot_arm/simulation_runtime/worker.py` | 94282 | `2eff68be6887b2b5d1b891b57dd522ff7bd420231288047e5fdee57fbca0b974` |
| `src/cloud_edge_robot_arm/simulation_runtime/models.py` | 6802 | `3101d17a9a2faf36ad81dabadbc5b1595805df7c6021f75e66055fa7c40d5e12` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round419-phase11-receipt-truthfulness-20261104/run_stage.py` | 3173 | `fd82af588f9341da6ef93a6a91bbca3dce11de1ea22b01e70244cd116d0aa69b` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round419-phase11-receipt-truthfulness-20261104/preflight/plan-adoption.json` | 1466 | `aa72f317f759014584fd5f202e21c4bd8dc8210f70cbb1210845377fb9bec1a1` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round419-phase11-receipt-truthfulness-20261104/plan.json` | 35801 | `a6b4994721984d52866b668d54c60f160109583eea8153855498dde4453739b8` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round420-phase11-returned-sqlite-fd-lifecycle-20261104/plan.json` | 17860 | `09642f6acfc1711b7ca5b3847ec4b43e57102f5e083933d96a31016d76cf82c3` |

## Self-review

- [x] 过期、释放、重入队、归档四时点分开；原FAILED合理，不靠改期待变绿。
- [x] 核对SQL空串schema并撤回duplicate已清理的无依据推断；旧audit原字节保留。
- [x] 精确captured lease与guard内fresh owner检查，禁止释放新owner/借用权威。
- [x] 正反例覆盖observer漏计、真实归档时序、owner拒绝及corruption隔离；次数/cap/路径明确。
- [x] 仅两计划文件写入，未运行行为/SQL/Git；正常路径及正式研究不夸大。
