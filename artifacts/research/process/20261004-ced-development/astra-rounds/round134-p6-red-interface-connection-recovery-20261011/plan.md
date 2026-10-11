# R134 — RED 接口证据与 acquisition 清理恢复

实际模型：gpt-6-astra；规划者 /root/astra_status_plan；2026-10-11。状态：冻结待 ROOT 复核激活。单一实施者仍为 /root/p6_stage_a_sol replacement GPT-6.1-sol。此规划阶段仅读取文本、JSON、XML 和字节哈希，未执行产品、AST、import、compile、collect、static、pytest、数据库 probe 或 Git。

## 原始结果与分类

R127 原 RED23 真实一次 exit 1：19 failure、4 pass、0 error、0 skip，27.02 秒。原 stdout、空 stderr、JUnit、invocation、result 和完整 stopped-red 冻结保持不变；本 JSON 的 inputs 保存完整绝对路径、bytes 和 SHA256。ROOT 与作者当前账本均 red used 1 / remaining 0，不能沿用 R131 的旧零耗用描述。

独立阅读三项异常的完整 failure text、相关冻结源码、models 类型声明，并解析原 JUnit 核对数量：
- restart[recovery_service] 与 restart[manual_retry] 已走完旧未完成 attempt 终止、禁止重发、原 acquisition 保持、foreign-live UNKNOWN、legacy UTC 恢复断言；在测试第 582 行 current.model_dump(mode="json") 才失败。它们仍是 FAIL，不能记 PASS。
- 第 708、754 行是同一实际 SimulationJobRecord dataclass 的潜伏序列化错误；G1 修复后会到达。models.py 明确内部记录是 frozen dataclass，API 响应才是 Pydantic。三处都需有界修复。
- acquire_ack_lost 在真实 COMMIT 后关闭 SQLite connection，最终在 public repo.list_attempts 读取时抛 ProgrammingError；不能记为计划内权限断言 RED，也不能认定只是 fixture 问题。

其余 16 项是原 G1–G4 的行为断言/DID NOT RAISE RED；四项 PASS 为 orphan[committed]、actual_main_and_thread_heartbeat_producers、confirmation_lost、reassigned。PASS 只说明这些本次用例通过，不替代最终新语义验证。唯一 warning 为依赖 DeprecationWarning，未见其证明线程泄漏，不修依赖。

## 独立根因与精确新增修复

### S — 测试证据序列化（仅原测试文件）

三处 model_dump 误把 frozen dataclass 当 Pydantic。使用已存在的 dataclasses.asdict 或等价真实字段结构转换；datetime 用明确 ISO 文本、Enum 用 value，保留 None、数字、布尔、字典/序列结构。job 与 before/recovered attempt 证据应保留可检查的字段对象，不能把整个记录 repr/default=str 冒充结构化证据。允许同一局部辅助转换服务这三处，不为生产模型添加 model_dump/兼容别名，不改 models.py/P5，也不扩展节点或弱化任何行为断言。修正后的 evidence 必须可用 stdlib JSON 读回，job_id/status/attempt 与实际记录一致，attempt 的 ended_at/result 对照真实前后快照；相应证据在原节点中产生，不另跑 serializer probe。

### C — 已提交失确认后的异常安全退出（原 G2 精确补点）

冻结 sqlite_repository.py 的 _acquire_operational 在 finally 第 1345 行先读 conn.in_transaction。连接已真实关闭，此属性抛 sqlite3.ProgrammingError，跳过 _close_view 及 TLS connection/nonce/commit 清零。_connect 第 1560 行优先返回这个非空 stale connection，导致 list_attempts 的真实异常。故障链由源码和原执行 traceback 共同支持，不是新增 probe 的结论。

限定改进 _acquire_operational 的退出清理，及同根因直接相邻的 _operational_transaction/_connect 退出路径：
- 无论事务属性读取、rollback、view invalidation/close 是否抛错，最外层 finally 都必须撤销此次真实事务的 TLS connection/nonce/commit 与 R127 私有 owner registration；不得清掉他人事务，也不得复活 authority。
- 对已关闭 SQLite 连接无法 rollback 的 cleanup 情况作明确处理，不能让次级 cleanup 异常掩盖原 commit/ack 失败。_connect 的异常 rollback 也只能在此意义上有界处理；不得增加 reconnect/retry、静默复用新连接或把陈旧注册变成正向授权。
- _operational_transaction 当前已捕 sqlite3.Error，但 close-view 后仍应有无条件 owner/TLS 注销层。这里是同一退出保障要求；没有宣称本次 raw 已观察到 _close_view 自身抛错。
- 与原 R127 G2 的 worker finally 接续：acquire 没有成功返回 lease 时仍按真实 session/job 身份终止已提交任务/lease；bind 失 ack 与初始 heartbeat 失败仍关闭真实 open attempt，durable COMMITTED/REVOKED/TERMINATED 旧 epoch 仍安全终止。仅清空 TLS 不能代替数据库终态。其余 G1/G3/G4 仍按原计划实施，不能因本轮调整而跳过或拖给 B/C。

### F — 保持故障 fixture 的真实性

_CommitCloseConnection.execute 先实际 COMMIT、after_commit 再 close，faults 保证一次，connections 的 active 分支反映真实 TLS。保留这条故障，不改成假 ack 或提前清 TLS。允许把 monkeypatch 的生命周期明确包在真实 poll 执行范围内，退出后恢复原 _connect/queue hook；恢复 hook 不能清 TLS，且恢复前必须记录/断言实际 TLS 和 owner 注销。public repo.list_attempts/get_job 必须仍经真实 repository API 成功读出终态，不能改成 direct SQLite 来躲过问题。_rows 可继续作为独立旁证。

在该既有节点中核证：fault 恰好一次；真实已提交 ACQUIRED 行存在；session 不可用且关闭；broker/app clock 各在原 owner thread 关闭；无残留事务 owner/TLS；原 public 读取成功；job 非 LEASED/STARTING/RUNNING/FINALIZING，lease released，durable phase REVOKED/TERMINATED，已有 attempts 全部终止，retry 不重发。资源连接必须 finally.close，线程/队列按原合同结束；不用新权限 mock、token bypass、手工 registry 清理或放宽异常接受。

## 范围、顺序和预算

原 R127 六条 owned paths 是全部产品范围；本轮新原因仅影响测试和 sqlite_repository，worker/recovery 的语义修复仍来自原 G2。禁止改 protected P5/OC1/backend/event/native、模型、旧 plans/proofs/raw/失败记录。当前六源与 stopped-red sources 字节全同；52 protected pins 全匹配。78 个有限输入 pins 见 JSON；1241-entry source-index 仅作为已保存清单 pin，本规划不声称逐个复核整棵 case-evidence，也不外追 symlink。

1. ROOT 核对本计划、78 pins、六源/52 protected、两当前 ledger 和原 RED23 后激活同一作者。先保留修改前六源/差异和新的 R134 metadata ledger。R135 只恢复规划保存，不能代替此产品激活。
2. 测试先完成 S/F 的局部改动与原断言保留；已有真实 RED 足以支撑 C/G2，无需再跑 RED23。按原 R127 G1–G4 完成生产修复，加入 C 的精确异常安全清理点。
3. 作者冻结新六源、文本差异、fixture/lifecycle tally、writer/SQL/owner 映射和 S/C 对照。原 R127 尚未使用的 formatter、scope_proof、ruff 各一次按原 exact argv/顺序执行；新 R127 proof 必须覆盖新语义及 C，不能编辑旧 R113/R125/R126 已通过证明冒充适用。出现新失败则停并另交 Astra。
4. ROOT 实读新 source/fixture/proof，明确释放本轮 recovery3 单次额度。新增命令的 exact argv/env/cwd/output 在 JSON；三个节点为 restart 的两个变体及 acquire_ack_lost，预期 3 PASS/0 failure/error/skip/xfail、exit 0。这是异常恢复验证，不是第二次 RED23。至多三个既有实际 poll_once 生命周期及两个原 legacy SQL recovery fixture；不得循环重试、扩节点或多启 worker。若文本 tally 与此不符先停，不能自行提高。
5. ROOT 核验 recovery3 的原始输出、JUnit、真实资源/数据库终态与 JSON 结构，再按 R127 原门禁释放四终门：原 format_check → mypy → GREEN20 → R127 new_GREEN19。四终门在另行释放前仍 held，各沿用 0/1 原额度、原 argv/路径；新_GREEN19 中原 G1 节点必须实际走到修正的两个证据写入点。不得补跑 full39、OC1、P5、75、RED、import_sort 或原 whole-proof。
6. 单次新 targeted 失败或新根因保存后再交实际 Astra。作者与 ROOT ledger 如实消费，不重置旧命令。生成 R134 implementation/result、step-report、原差异及 source freeze，ROOT 有界 input-check/activation/ledger/validation/phase 附记；不覆盖原工具输出或旧阶段正文来隐藏失败。

## 规划工具失败（独立元数据边界）

规划展示工具 18dc99 在 PASS 的 null failure_attributes 上 .get 导致只读展示失败；无需再用，禁止修复/重跑。保存工具 90c536 因嵌套 heredoc 分隔符在解析阶段失败，没有执行 mkdir/write。实际 Astra R135 计划已先落盘，才以结构化 apply_patch 保存本轮计划及可得原件。证据保存在完整绝对目录：
/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round135-p6-astra-plan-save-recovery-20261011/original-evidence/
两失败不得算作 acquisition 根因或产品 RED；18dc99 无事前独立 stdout/stderr 原流，片段不得称完整 raw。

## 实际前置与验收

运行只用项目 .venv/bin/python、原环境 PYTHONDONTWRITEBYTECODE=1 / PYTHONPATH=src:.，原 cwd；首次命令前确认 targeted evidence/basetemp 不存在，不删除旧证据来腾位置。逐命令真实保存 argv/cwd/env、独立 stdout/stderr、exit、开始结束时间和 SHA/JUnit；actual/native/paid/model/GPU/Git 额度 0。原 legacy UTC veto 必须保留；软件通过后仍只可申请 Stage A LEASE_FOUNDATION_WITH_LEGACY_UTC_VETO 的独立审查，B/C/D/native/actual/formal 均未因此完成。计划保存本身不证明任何修复已通过。

所有后续交接必须完整绝对路径加 SHA，不猜目录。

