# T15a 研究运行器与记录契约局部报告

状态：**SOFTWARE_REVIEW_PASSED**。前两轮独立审查的持久化和阶段重标问题已修复，`fix-round-2-review.md` 对释放的软件范围独立复查PASS：55 tests、Ruff与12来源散列匹配。本报告不关闭 T15b/T15c，不验收 INITIAL、FINAL、功效先导或正式研究。边缘模型选择后置。此步骤未运行 GPU、渲染、真实模型、网络调用或物理机器人。

## 交付和来源

实现计划保留的 `EpisodeAssignment`、`EpisodeRecord`、`PowerDecision` 位置参数，以及 `build_assignments(protocol, methods)`、`run_assignment(assignment, protocol)`、`choose_formal_n(...)`。新增 keyword-only 扩展用于完整来源绑定，不从散列字符串合成正式场景：`build_assignments(..., scene_pool=完整原始候选行)`；`run_assignment(..., software_adapter=显式MOCK夹具)`。后者不能登记物理成功。`run_gate_replay` 复用 T10 唯一门控，不传入独立标签。

全部 12 个新增文件的初始不存在状态记录于 `baseline-manifest.json`，最终源代码/config/test 逐文件散列见 `source-hashes.json`，精确副本见 `source/`，独立审查包为 `review-package.diff`。不修改 protocol、pilot、freezer、backend、vision、runtime、events 或共享文档；不提交、不推送、不统一暂存。

## 具体行为

- 分配前检查 FINAL 内容散列、INITIAL 链接、所有方法/来源 hash 和完整 formal 池散列。完整池必须有 2400 个唯一场景/来源组/assignment，每层 200 个。仅按原始每层前 N/12 个选择，N 只能是 600/1200/1800/2400，各方法每层 50/100/150/200 个。
- 每个场景配对完整场景 JSON、物理 seed、扰动 JSON、网络日程和网络内容 hash。方法顺序依协议/组散列随机但固定，不因用户提供方法顺序改变配对。正式网络参数保持固定设计的 RTT、loss、20% jitter 和 10 Mbit/s。
- `EpisodeRecord` 保留原字段和每个分配身份；轨迹引用带 schema_version/content_hash/path，并可核验实际文件字节。记录 JSON 断点读取重新计算完整 hash。成本/耗时/物理量的非有限或负值拒绝。正式在线验证条目必须包含版本、未修改的原始判定、来源引用和 canonical content_hash；来源声明时实际核验文件字节。旧裸字典只能是 source_verified=false 的诊断，不能声明正式来源。
- 当前真实运行适配器尚未集成，默认 `run_assignment` 必定返回 BLOCKED，三个阶段 NOT_EXECUTED、0动作、0模型请求、0physics step。失败/BLOCKED/TIMEOUT/STOP/FALLBACK 全部使用 Tcap；未验收恢复统一 60 秒。
- 软件夹具必须显式 MOCK；任何模拟的完成都会在运行入口清除 success/physical_success/task_success，保留 MOCK 来源和完整 Tcap。不把软件夹具输出计作物理成功。
- 基础设施重跑须读取并 hash 核验 `incident.v1` 事故资料，保留原记录 hash；仅允许注册的 renderer/backend 崩溃或捕获存储损坏类别。任务失败不是理由。必须提供完整预先声明的方法集合，保留相同 scene/seed/schedule 的完整配对；模块只返回授权元数据，不自动重试。
- 正式 CLI 保存全部 assignments 和 append-only records。`--resume` 核对原分配和每条记录散列，已记录的 BLOCKED 不删除/覆盖；发现变更时 NOT_RUN/exit3，保持原记录。阈值、池和 N 不能由 config 覆盖。
- G3 软件回放按每个机会的固定时刻、标定和在线事实处理，保留顺序、候选 hash 和所有 VALID/INVALID/UNKNOWN。正式 G3 来源验收尚未集成，CLI 返回 NOT_RUN；只有显式 `--software-fixture` 能输出 SOFTWARE_ONLY/MOCK 回放，不计物理成功。
- 三个消融只关闭 uncertainty_gate、completion_age_gate 或 local_repair 之一，SafetyShield 和其他输入保留。config 是设计元数据，不代表实际方法已冻结或启用。

## 功效计算与边界

纯数值接口必须恰好输入 120 个布尔配对成功和安全结果。只使用配对不一致率 q，不使用先导成功/安全差值方向推断有利效果。设计固定为真效应 0、单侧总体 α=.05、5 个预注册主假设，保守设计 α/5=.01、目标功效 .8；成功非劣边界 -.03、安全非劣边界 +.01。

对 q>0，条件代入的正态设计功效为 `Phi(margin * sqrt(N/q) - z_(1-.01))`；这是固定零效应、方差 q 的规划近似，不是已实现/验收的配对 score 正式检验，也不保证真实未知 q 下的功效。q=0 不增设任意方差下限：非劣零假设边界的全一致概率至多 `(1-margin)^N`；在明确假设 q=0 的替代下，只有此概率≤.01 时条件功效记1，否则记0。两项均≥.8 时选最小候选 N，否则 `selected_n=None`、报告需要超过2400。无法按正式 p 值追加样本。

精确单侧 95% Clopper–Pearson 先导不一致率上界另外报告；不将 0/120 当作真实概率为0，也不擅自把该上界改成另一个样本选择规则。`PowerDecision.source_accepted=False`。来源 wrapper 核对完整120、power split、互斥组、方法版本和来源 hash，但这些元数据不足以独立验收物理先导；真实来源 verifier、完整原始轨迹和方法冻结仍是 FINAL 前置。

核算示例：安全 q=1/120、N600，`.01*sqrt(72000)-2.326347874=.356933699`，条件功效 `.6394292795`；N1200 条件功效约 `.929`，所以与低不一致的成功指标共同选择1200。最早一次测试中的 `.5030309` 手算期待值错误，改成独立核算结果，生产公式未改；旧日志 `green-initial.log` 保留该 1 失败/35通过记录。

## 验证

测试按 TDD 使用新增行为缺失的失败证据。初始 `red.log`：36 failed/exit1（缺新增生产模块）。CLI/记录反序列化 `red-cli.log`：3 failed/exit1（缺入口/接口）。网络同ID内容漂移、漏掉完整配对方法的 `red-bindings.log`：2 failed/exit1。全部失败日志保留。

最终独立命令与退出码：

| 检查 | 命令范围 | 结果 |
|---|---|---|
| 新任务覆盖 | `.venv/bin/python -m pytest -q tests/test_research_assignments.py tests/test_research_runner.py tests/test_research_power.py` | 46 passed，9.34s，exit0；green.log |
| 安全相关回归 | `test_research_protocol.py test_research_provenance.py test_research_cost_ledger.py test_fixed_opportunity_replay.py test_visual_evidence_contract.py` | 71 passed，2.55s，exit0；regression.log |
| Ruff | 本次9个 Python 文件 | All checks passed，exit0；ruff.log |
| mypy | 本次6个生产/CLI源文件，`--follow-imports=silent` | no issues，exit0；mypy.log；既有 unused-overrides 注记 |

未运行全套测试：根代理限定 CPU 相关范围，避免既有测试不受控触发真实模型/渲染；历史全套未完成的失败由主阶段报告保留，不将本模块检查扩展为全仓通过。46与71是不同指定文件集，不与其他模块累计成全仓总数。补充 `red-physical-acceptance.log` 记录仅声明 PHYSICS 的假成功被误接受的反例（1 failed）；修复后 accepted_task_success 始终为 false。`red-verification-envelope.log` 记录未绑定在线判定/篡改判定的2个反例，最终全部通过。

## 给后续来源验收器的具体数据契约

- `EpisodeRecord.to_payload()` 输出原位置字段 `assignment,outcome,provenance,costs,duration_penalized_s,infrastructure_incident_id,decision_trace_refs,verification_records,recovery_trace_refs,provider_versions` 和 keyword-only `run_status,source_verified,schema_version`，另附完整 `content_hash`。`episode_record_from_payload` 重算此 hash。schema_version=`ced.episode-record.v1`。
- `assignment` 保留7个原字段，附 `scene_payload_json,perturbation_json,network_schedule_json,pool_hash,protocol_hash`；scene JSON 是完整 SceneSpec，network JSON 是完整 NetworkSchedule。group/seed与scene对应，schedule_id必须是其余network字段的canonical hash。
- `provenance` 复用 `RunProvenance`：`run_id` 必须等于 assignment_id；`scene_group_id` 必须等于 group_id；`split_role` 当前 formal；`source_tree_hash,model_snapshot_hash,observation_hashes,physics_steps,evidence_kind,blocked_reason,stages,task_success,cohort,ground_truth_exposed_online` 均保持原类型。每个 StageEvidence 包含 `stage,status,source_hashes,reason`。这些键不是物理真值证明，独立来源验收仍必须重算。
- `ArtifactReference` 是 `{schema_version,content_hash,path}`，content_hash是原始文件字节 SHA256。`verify(root)` 可以限制在证据根内；文件不存在、越出指定证据根或hash不同均拒绝。引用类型用于decision/recovery/source证据，不猜测尚未实现的T13类型。
- `verification_records` 的来源绑定条目格式为 `{schema_version:'ced.verification-record.v1',record:原始在线判定字典,source_refs:[ArtifactReference字典],content_hash}`。content_hash是前三个键的canonical hash。`make_verification_record(record,source_refs)` 提供无改写封装；source_refs不得为空。条目和provider版本映射被递归冻结，外部修改不改变记录。旧裸判定可保留仅作诊断；source_verified=true时拒绝旧裸判定。
- `source_verified` **只表示上述结构/实际文件hash检查，不表示物理结果重算通过**。`structurally_complete_success` 只检查结构、在线声明和provenance声明是否齐全。`accepted_task_success` 当前**恒为false**；任何metadata/hash/REAL/PHYSICS声明都不能让该属性变成true。T16/实际整合必须独立读取原始physics与capture证据、重算终局，才能在其可信结果层登记真实接受成功，不能用这两个结构标志绕过。
- `provider_versions` 是角色/provider版本映射，不用旧单model_snapshot_hash表示全部云/边/端。真实整合需要绑定冻结的cloud/edge/device身份、runtime与sourcehash，当前软件记录不生成这些版本或验收结论。

## 开放前置

1. 此模块已实现软件记录/分配/回放/功效边界，但尚待独立审查。未出现真实 method/power/formal 阶段，不宣称 T15a 研究验收或全项目完成。
2. 当前构造器可核验轨迹/验证引用文件 hash，这些仅是结构门槛，不能替代独立重算 physics 原始轨迹。`accepted_task_success` 恒为false；实际来源验证器整合前不接受任何记录的声明式物理成功。正式入口没有开放真实适配器。
3. 事故类别/诊断为 hash 绑定的事故报告，正式重跑仍须独立审查其原始基础设施损坏证据；本模块不伪造事故、不执行重跑。
4. 完整协议证据验收、方法/runtime 接入、真实120功效先导、来源复核、FINAL发布、真实正式/G3/G4以及正式配对 score 检验均由后续整合阶段完成。本次 config 和功效结果绝不替代这些门槛。

## 独立审查修复轮 1

`review.md` 的首次独立审查指出两个 P2 问题：有效重新散列的 BLOCKED 记录可把 Tcap120 惩罚改成.001；未知 EpisodeRecord 格式可被读入。第一次完整审查及验证日志保留，根代理确认修复契约后执行本轮。

- `EpisodeRecord` 构造和加载都强制 schema=`ced.episode-record.v1`；缺失/未知持久化schema拒绝。
- 新增 keyword-only `frozen_tcap_s`，绑定正式记录的冻结截止。绑定到 formal 协议的记录必须包含此值，合法范围/步长与 ProtocolSpec 一致。当前尚无独立物理验收器，所有未接受记录包括元数据声称成功，持久化惩罚仍为完整 frozen_tcap_s；真实原始 elapsed_s 不变。
- `validate_episode_record(record, protocol)` 检查 FINAL内容hash、assignment.protocol_hash/pool_hash/完整scene绑定、已冻结method，以及记录 deadline/penalty必须与 protocol.spec.tcap_s 一致。声明式 source_verified/PHYSICS 不能缩短惩罚。
- 正式保存用 `record.to_payload(protocol=protocol)`；正式读入用 `episode_record_from_payload(payload, protocol=protocol)`。无协议不能读写正式记录。旧未绑定7字段分配仅可作诊断，不能进入formal resume。
- loader 先检查 raw payload content_hash，再检查构造语义和冻结协议。既有未重新散列的篡改依然报告hash错误；重新散列的无效惩罚/截止仍被语义检查拒绝。BLOCKED+success 或 SUCCESS+未成功等矛盾状态也拒绝。
- CLI resume 在加入 completed 集合前调用该边界，所有拒绝都 NOT_RUN/exit3，原记录字节完整保留。实际运行适配器仍未开放，不新增任何物理成功验收。

回归覆盖包括：构造拒绝未知schema、不能省略正式deadline/缩短惩罚、重新散列的600秒deadline与真实120秒协议不一致、CLI恢复分别拒绝未重新散列的损坏/重新散列的惩罚/未知schema/截止变更。`fix-round-1-red.log` 保留3失败；首轮green中额外发现MOCK成功状态清除后状态标签未同步，修复为显式软件失败并保留原始耗时；日志不删除。

最新验证：`fix-round-1-green.log` **52 passed，24.16s，exit0**；`fix-round-1-ruff.log` 全部通过exit0；`fix-round-1-mypy.log` 6个源文件无问题exit0（同既有配置注记）。71个相关回归首轮已通过；该修复只修改新增持久化/runner入口及其CPU覆盖，不重复真实模型或全套。

`fix-round-1-baseline/` 保存首次释放的12个来源文件和旧manifest。`fix-round-1-review-package.diff` 仅表示本轮变更；`source-hashes.json`/`source/` 为修复后当前完整12文件快照，`review-package.diff` 为从初始不存在状态到当前完整实现。复查前不将该修复标为独立审查通过。

## 独立审查修复轮 2

复查再次指出正式记录可把 `provenance.split_role` 改为selection并移除deadline，导致保存/读取绕过条件检查。根因是把记录自行声明的阶段当作正式准入依据。本轮修复将正式身份绑定到 immutable assignment.protocol_hash：存在该绑定时来源阶段必须为formal，必须有正确frozen_tcap_s；声明selection不能免除检查。

只要调用者提供FrozenProtocol，`to_payload` 和 `episode_record_from_payload` **无条件**调用 `validate_episode_record`，不再根据来源阶段分支跳过。绑定记录无协议依然拒绝；无绑定旧诊断不能在提供正式协议时冒充正式记录。CLI固定manifest的assignment身份比较与这一边界共同保留。

`fix-round-2-red.log` 的两个回归先失败：构造同一正式assignment的selection/.001/None记录；重新散列后通过带协议loader读取同一记录。另增加CLI重新散列phase变更用例，与此前四种篡改一起拒绝为NOT_RUN/exit3且不改变原记录字节。

最新 `fix-round-2-green.log` **55 passed**；`fix-round-2-ruff.log` 全部通过exit0；`fix-round-2-mypy.log` 6源文件无问题exit0。原始首次/修复1日志和审查报告保留。`fix-round-2-baseline/` 保存修复1释放的12文件和manifest；`fix-round-2-review-package.diff` 为增量修复，新完整快照由current source-hashes/source/提供。真实运行/source验收能力仍未启用，accepted_task_success恒false。
