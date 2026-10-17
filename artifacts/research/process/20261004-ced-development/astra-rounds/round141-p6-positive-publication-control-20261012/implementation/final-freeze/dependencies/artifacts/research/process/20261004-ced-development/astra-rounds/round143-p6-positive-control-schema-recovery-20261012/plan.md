# R143：新增 positive control 的 fixture/API/schema 映射修正

实际规划模型 **gpt-6-astra**，规划者 /root/astra_status_plan，2026-10-12。冻结待 ROOT 激活；本计划不是产品修改授权。

作者仅追加了 R141 的一个测试，静态自审发现四处映射问题。该测试从未运行，没有 traceback/exit 或预算消费。原始 finding、78040B 草稿、append-only.diff、两账本和索引保持原样；JSON 保存全部 89 个绝对路径及 SHA256/bytes。实际已对照 77 项，零漂移；原模块 65231B 前缀完全相同，五生产和 53 保护输入不变。

## 独立核实与限定修复

- **D1 已支持。** asdict(VisualEpisodeOutcome) verification_records remains tuple, while draft compares []。Assert exact empty tuple in original/controlled dataclass dictionaries and preserve equality of every non-injected field. Keep generated result JSON verification_records == [] as JSON array; no global coercion or weakening.
- **D2 已支持。** OperationalWindowOwner has no owner.thread_id。Obtain real app_clock=owner.clock while live; use app_export['domain']['owner_thread_id'] and actual app_clock.domain.owner_thread_id (and existing genuine startup coordinate if needed), bind to session.main_thread/threading.get_ident. Record real broker domain separately, no synthetic coordinates, no treating exported identity as authority.
- **D3 已支持。** Two post-finally owner.clock accesses call live guard after revoke。Retain the exact real live app_clock in references during check, then read that retained handle's _closed for closing assertion and sidecar after _exercise. No getter after revoke, no new clock/origin/token, no swallowing exception or removing closure evidence.
- **D4 已支持。** job/runtime_job JSON lack worker_id,lease_id,completed_at,artifact_paths。Compare the actual generated job schema (job_id,run_id,backend,scenario_id,control_mode,seed,status,attempt,timeout_seconds,source_commit,source_tree_hash and three hardware safety fields) directly against real current DB job and expected false/false/[] safety values. Do not call production _job_artifact to construct a self-confirming oracle. Preserve real DB/attempt/lease/operational-row identity, completed_at/released_at/ended_at, artifact map containment, all generated attempts/leases/status transitions and file hashes. Missing JSON keys must not be invented or bypassed with .get defaults.

完整新增函数已逐项核对 VisualEpisodeOutcome、持久化 dataclass、owner/session、结果与 task semantics、attempts/leases/transition/event、consistency/file_hashes。除 D1–D4 外没有发现有依据的额外同因缺陷。R144 唯一授权文本读取实际 chunk4453ec exit0，确认 events._conn 是真实 SQLite 连接，close 直接关闭同一连接；保留现有关闭断言，不将该文字事实称运行通过。

唯一产品区可编辑位置：/home/ningyd/文档/ChatGPT/BIGsmall/tests/test_operational_runtime_closure.py 内新增函数 test_normal_success_publication_uses_real_operational_authority。原 39 节点、模块前缀/import/helper 一律不改，总 40 节点不变。D3 的 reference tuple 与 sidecar 两处同步属于同因修复；D4 必须映射实际 schema 而非删掉终态/身份核验。不得改五生产、factory、P5、任何 protected 文件；不得添加通用兼容 API、默认值掩盖缺字段、直接 SQL 写成功或 mock 权限/发布/一致性。

## 证据必须保持

保持六项 CPU 注入 flags：success=true、status=SUCCESS、online_reported_complete=true、physical_success=true、failure_reason=null、terminal_reason=null。原 outcome 其余所有字段不变，物理量/动作/model calls/observation count 继续零。调用真实 factory episode 一次，真实 worker→task semantics→guarded SQL/broker→最终 publication；during RUNNING/open attempt/unreleased lease 与 final SUCCEEDED/ended attempt/released lease、同 epoch COMMITTED TERMINAL 全链身份关联不变。job/runtime_job、result、attempts、leases、transitions、events、consistency 必须由原 worker 生成，文件路径 containment 与逐文件 SHA 重算不弱化。

sidecar 明示 CPU_CONTROLLED_OUTCOME_NOT_PHYSICS_EVIDENCE、controlled_flags_injected=true、native_physics_validated=false。注入 physical_success flag 不是物理验证。真实 backend/raw/session/clock/events/thread cleanup 断言仍保留，无额外 probe。保持 Stage A legacy UTC veto；不扩大 B/C/D/P5。

## 实施、验证与预算

1. ROOT 全文读本计划并复核 inputs/两账/前缀，写 R143 activation；同一 sole replacement author 才可仅修新增函数，另存 corrected draft/diff/D1–D4 mapping report。
2. 回原 R141 流程准备 scope-proof.py 与 runner。ROOT 必须全文读 corrected function、实际 proof 和 runner；不得猜路径或缺依赖 pin 后直接执行。
3. 仅继承 R141 原四个各 0/1 命令，argv/cwd/env/证据目录在本 JSON 原样列明：test_formatter → scope_proof → test_ruff；真实输出经 ROOT 审阅后，单节点 positive_control 才可释放。一次 poll/episode 上限不变。
4. 原四终门 format_check → mypy → GREEN20 → new_GREEN19 继续 held；真正 positive 证据及 ROOT final source/fixture/proof review 后才沿原精确命令释放。原 RED23、R127 static、R139 static 与 recovery3 已耗，不重置、不重跑；无 full40/旧回归/额外 AST/probe/Git/actual 额度。

手工修正前后原 65231B 前缀必须 byte-exact；formatter 后由原 R141 单次 proof 核原 AST/comments/constants、39 节点不变、唯一新增函数总 40、五生产及 53protected。不另授 AST 或语法检查。所有未来执行分别真实捕获 argv/cwd/env/stdout/stderr/exit/JUnit；任何计划外问题保留后另交实际 Astra，不临时 patch 重跑。

本轮允许保存 input-check/root-activation/executor-brief/implementation/validation/step-report/phase-summary-addendum；R141 原元数据路径按既有计划继续。旧原件与旧计划不改。R142 optional-reader disposition 独立；本规划中的猜 event 文件失败经 R144 单独保存可得原命令和捕获缺口，并激活一次正确精确读；不吞掉失败，不把 metadata disposition 冒充测试通过。

验收先限于草稿映射与 scope 正确。后来 CPU positive 通过也仅证明注入 flags 下的软件发布链，不能替代 native/真实/正式研究证据，也不提前宣称 Stage A 完成。

