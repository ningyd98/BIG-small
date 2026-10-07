# R07 recovery wall-Rcap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task; retain the user's existing execution arrangement and independent-review requirement. Steps use checkbox syntax. 本次仅生成计划，不启动实施或 actual；执行中出现新问题，按用户新增规则先交 Astra 制定下一轮修改计划。

**Goal:** 给新的 R07 开发来源增加真实 fault-start→terminal 操作计数原件、60 秒保守成功准入和超时停止检查，保留旧 1/200 原件与 canonical ledger；正式研究计时仍待 OC1/OC4 验收。

**Architecture:** 在现有 producer 中增加单应用、单进程的实际计数 owner 与 receipt，复用可传播异常的 actuator/physics hooks，并给现有 T5 增加一个可选检查回调。v3 明确接续已审 v2→v1，继续引用原六 payload 和原 allocations；不重建池、不引入通用计时服务或新执行器。

**Tech Stack:** 现有 Python/Linux、`time.clock_gettime_ns`、现有 CLI SIGALRM、MuJoCo/T5 passive hooks、JSON/JSONL 与现有 fsync 原件写入。

**Spec:** `docs/superpowers/plans/2026-10-05-operational-clock-repair-supplement.md` 的 D/S、suspend、deadline 合同；`docs/superpowers/plans/2026-10-05-astra-repair-plan.md` 的 R7 和原研究阈值。输入全 SHA/bytes 固定在相邻 `plan.json`，本计划不是实施/独审/实测证明。

## Global Constraints

- Rcap=60 秒、原 operation wall=1800 秒、原 3260 rows/200 recovery、seed2026100507、六 payload、现有 simulation Rcap 和统计门保持。新 D deadline 等值拒绝，来自计时补充的保守边界，不是提高/降低研究阈值。
- D 是冻结平台真实操作计数；S 是同 backend/episode 的 simulation time/physics step。fault motion、0.005 秒 gap、抬升/保持/稳定继续用 S；实际恢复 wall 用 D。D 不写入 UTC 字段，不声称 monotonic=UTC 或具有通用 SI 校准精度。
- 原 v1 protocol hash `66570b912ba08e0924e4cbe31098be9df7f1f02ed43548b131f65b2695ded724`；当前已审 v2 hash `4944004b4804cf2b9f403be1981b6ca1228889b53a6c434f39b60f50a2515db8`。这是内容协议 hash，不与 generation.json 文件 SHA 混用。
- 原 recovery-0001/attempt-1 保持 PROVEN 与全部旧字节；它只有整个进程 GNU wall17.45秒的保守上界，不能回填本轮 receipt。已消费首组及 PROVEN 后 attempt2 禁止；本轮规划/实施/冻结/独审均不运行 recovery-0002，不增加 actual 分母。
- actual/provider/renderer/physics/decoder/网络在本次规划均为0；只新写本目录 plan.md/json。后续源码范围严格见下；旧原件、Stage/Git及正式门不属本轮实施任务。

## Review Focus

1. D 超60而S低于60，以及 terminal 恰60：必须拒绝 wall 成功；Task1/2 边界测试。
2. render/动作在两个检查点间阻塞或 suspend：恢复后的第一个检查拒绝，不能把 alarm 或回调声称成硬实时中断保证；Task2 阻塞/计数跃迁测试。
3. 伪造 owner、fork/重启/boot/episode 漂移、倒退和缺 receipt：拒绝，不能换计数起点；Task1 生命周期测试。
4. 当前 operation observer 吞异常：不得把该只读 hook 当停止守卫；Task2 用真实 T5 接口及可传播 actuator hook 验证 dispatch/下一 mj_step 为0。
5. v3 只认直接 predecessor 导致丢失 v1 ledger，或缺终态被当未消费：保留 canonical 1/199/200 与所有失败；Task3 迁移测试。

## 已定位的问题与范围

`GenerationBudget.check`（当前641–665行）用 `time.monotonic` 检查从 producer 创建算起的1800秒，却仅用 `sim_time_s-fault_start_s` 检查60秒。`_run_physical`（708–856行）在注入前只保存S起点；terminal没有D原件。`execute_recovery_once`（859–952行）最后只检查 S elapsed−injection_start≤60，再写PROVEN。17项旧CPU/独审没有关闭D缺口。

`backend.observe_actuator_steps` 的异常传播且发生在 mj_step 前，但在 `_apply_control` 后；它可阻止下一物理步，不能宣称阻止了所有前置命令。`observe_operation_boundaries` 的 `_emit_operation_source`（306–355行）捕获 BaseException 并仅记 failure，所以不得拿它抛异常实现 guard，更不能改变既有 R03 observer 合同。现有 T5 的 `execute()` 在 action 前和 `_capture()` 前没有可调用 budget hook，因此最小范围需要额外触及 teacher.py，而不是只修改 producer 的一个 now。

后续允许修改仅四份：

| 文件 | 精确责任/当前定位 |
| --- | --- |
| `src/cloud_edge_robot_arm/research/protocol_generation.py` | 381–585迁移/来源校验；641–706计数与alarm；708–952 fault/检查/terminal/结果准入 |
| `src/cloud_edge_robot_arm/datasets/rgbd/teacher.py` | `run_teacher_episode` 90–100可选参数，145–190首次capture及execute内四个边界；不改动作recipe或评价阈值 |
| `scripts/generate_rgbd_protocol_evidence.py` | 仅迁移CLI帮助/必要路由及开发scope输出；默认仍PREFLIGHT_ONLY |
| `tests/test_protocol_generation_sources.py` | 最小RED/GREEN、现有真实接口CPU接线及v3迁移测试；更新被影响的mock签名 |

`backend.py`、`protocol_evidence.py`、configs、原协议/actual均只读。不得为了通过新计划改旧接受函数、重造控制器、在线恢复器、外部UTC或OC1全域框架。新实施产物另用 `artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/`；与本计划目录分开。

### Task 1：最小真实计数 owner、括号和生命周期（仅SOFTWARE）

**Interfaces:** 在 producer 内实现私有 `_RecoveryWallOwner`，生产入口 `_open_recovery_wall_owner(plan: dict, output: Path, *, renderer_lease: object) -> _RecoveryWallOwner`。它只能由真实已持有的 renderer context 创建/持有，绑定 canonical allocation 文件SHA、当前 protocol hash、assignment/attempt、应用启动nonce、PID/进程启动身份、boot id及随后绑定的 backend实例/episode；nonce/PID/hash/分辨率单独都不是授权。CPU可用私有测试工厂注入脚本化整数读数，production CLI没有caller clock/domain/seconds参数。

- [ ] RED：新增 `test_recovery_wall_integer_deadline_boundaries`，D起点100ns时，D终点60_000_000_099ns可通过，60_000_000_100ns及+1ns拒绝；S=1秒不影响D拒绝。重复start不刷新；跨域、负/倒退、bool代int、缺pair/逆序拒绝。
- [ ] RED：新增 `test_recovery_wall_owner_lifecycle_fail_closed`，参数覆盖 foreign/copied live handle、PID/boot/episode变化、缺Linux BOOTTIME、计数读取异常；不创建backend、不注入fault、不换用monotonic兜底。owner绑定检查是活对象/实际进程关系，离线receipt只供复核，不能重新授权执行。
- [ ] GREEN：owner实现 `begin_fault(*, backend: object, episode_id: str, step: int, sim_time_s: float) -> None`、`end_fault_injection(*, step: int, sim_time_s: float) -> None`、`check(kind: str, *, step: int, sim_time_s: float) -> None`、`finish(*, step: int, sim_time_s: float, failure: str | None) -> dict`。D整数ns；只读真实 `clock_gettime_ns(CLOCK_BOOTTIME)`。启动记录OS/kernel/Python实现、clock id、boot/time namespace身份、计数能力；不支持或身份不稳定则fail-closed。
- [ ] 冻结scope为 `r07.recovery-wall.development.v1`，显式 `clock_semantics=LINUX_BOOTTIME_INCLUDES_SUSPEND`，要求实施时保存该平台本地权威语义出处及实现能力证据。若平台语义证据取不到，只能CPU通过，actual前置不满足。CLOCK_BOOTTIME包含suspend的合同不等于已做真实suspend实验；实际suspend/resume和restart证据仍是OC1/OC3门。
- [ ] GREEN：fault下界b−在真正inject之前读取并持久化BEGIN，设置不可延后的deadline=b−+60_000_000_000；inject返回再读b+、核对原TARGET_MOTION_STARTED的episode/step/S形成实际事件括号。若注入异常或缺事件，保留BEGIN，不能补成成功。每次当前括号[n−,n+]先身份/顺序校验，再用n+≥deadline拒绝，年龄上界(n+−b−)/1e9；不以midpoint、clamp、模拟倍率或UTC读数修正。
- [ ] GREEN/测试：D在S不前进时增加、模拟suspend计数跃迁、UTC跳变不影响D；restart/fork/episode变化拒绝。无法保证hypervisor/host pause计数语义的环境不得宣称完整wall已验收；本scope不支持跨机、外部期限或任意恢复进程续跑。

### Task 2：把guard接到真实fault、动作/采集、step和terminal（开发实际wall保护）

**Interfaces:** T5新增唯一可选参数 `execution_checkpoint: Callable[[str], None] | None = None`，四个kind固定为 `BEFORE_CAPTURE/AFTER_CAPTURE/BEFORE_ACTION/AFTER_ACTION`，默认None保持旧调用行为。producer传闭包调用同一owner.check；`GenerationBudget`保留现有S/byte/disk检查，增加对同一D owner的调用，禁止每次重建owner。

- [ ] RED：`test_recovery_wall_true_teacher_checkpoints_stop_dispatch` 在CPU中调用真实 `run_teacher_episode`，只stub硬件/render；在BEFORE_ACTION到deadline断言action调用0、BEFORE_CAPTURE到deadline断言capture调用0；AFTER_ACTION超时保留已发生动作原件并禁止下一动作，AFTER_CAPTURE超时保留已发生采集身份并禁止下一动作。不能只复制guard公式或用完全替代teacher的mock证明接线。
- [ ] GREEN：T5首次及每次后续 `_capture` 前后、`action()` 前及真实结果/action_observer记录后加对应检查。CPU测试钉住真实事件先保存再AFTER拒绝；任何已经发生的效果不从日志删除，不通过抛异常丢掉完整action记录。原actuator/physics回调保留实际快照并调用guard；`record`同step去重的早return前也先check，防止最后一次render后重复snapshot绕过截止。
- [ ] RED/GREEN：`test_recovery_wall_step_and_terminal_enforce_cap` 用真实producer接线、假的backend及D序列覆盖：ACTUATOR_PRE到截止则下一mj_step0；物理步返回超时保留这一步并禁止下一步；fault阶段同样受guard；S仍低于60但教师返回D超60不能PROVEN。post-action已发生事实保留，超时状态不能被后续正常return覆盖。
- [ ] 在同一outer1800秒alarm中实现私有可收紧timer句柄：由operation原起点产生固定deadline，fault开始后只取 `min(operation_deadline, fault_deadline)` 剩余量重新arm，绝不嵌套调用现有wall_deadline而覆盖/延长1800截止。`test_recovery_wall_alarm_tightens_without_reset` 检查60截止固定、晚调用仅缩短、异常后恢复原handler/禁用timer；保留当前已占用timer/非main thread拒绝。
- [ ] 显式限定alarm是最佳努力唤醒：Python signal可能延迟到C render/physics返回，ITIMER_REAL不作为suspend证据。D比较负责准入；在不可中断调用期间可能实际超过60秒，恢复后第一检查记FAILED/timeout，不能宣称所有运行均在60秒内被硬终止。若要求硬实时终止界，当前方案不合格，留在独立后续任务，不添加未经验证watchdog框架。
- [ ] 写新 `wall-start.json`、`raw-wall-checks.jsonl`、`wall-terminal.json`，分别保存启动owner/实际fault括号、按序检查的D/S/step/kind/身份及失败、终态。沿现有StepSpool新开独立小型journal，回调不做重型IO；BEGIN须在inject前fsync，正常结束close/fsync并验证无缺尾。writer错误、缺记录、缺fault end、无terminal、cross-domain/重启均不可wall通过，原allocation及已写prefix不回滚。
- [ ] terminal定义为真实T5返回（含最后动作、capture、独立评价）后、producer确认结束的观察括号；它是物理完成的保守上界，不能用最后一条S时间换算。清理/原件汇编/离线重算成本另记operation_end D，不回填为更早terminal；不声称文件发布在60秒内。成功必须同时有原 `_recovery` 的物理proof和完整D终态检查，D值未知或≥60一律拒绝wall成功。发生异常时记录FAILED/INCOMPLETE，超时终态允许>60但绝不记wall_pass。
- [ ] 实现 `verify_recovery_wall_receipt(output: Path, plan: dict) -> dict`：独立从上述原件、fault/action/physical-terminal及canonical allocation重算owner/因果/序列/固定deadline，检查首尾及摘要hash覆盖；调用者提供的diagnostics/summary不得替代。`execute_recovery_once`取得物理proof后再调用该reader，v3只在两者通过时PROVEN；另报 `wall_scope=DEVELOPMENT`、`formal_wall_accepted=false`、`g4_measured=false`。旧v1结果不能被reader回填或降级重写。
- [ ] RED/GREEN：`test_recovery_wall_receipt_missing_or_tampered_is_not_proven` 覆盖缺BEGIN/END/terminal、缩短起点/延后deadline、boot/step/episode错配、缺journal尾、writer error、summary forged、异常前已有动作；必须保留失败分母、无重试，不能仅补metadata后通过。

### Task 3：显式v2→v3迁移，共享旧账本，限定验证与独审

**Interfaces:** 延用 `prepare_successor_generation(predecessor, output, *, expected_predecessor_hash)`；v1→v2既有行为保留，新增只允许已审v2→v3的分支（`ced.recovery-generation.v3`）。不做任意深度/任意祖先图。`_generation_inputs`检查v3→v2→v1三节点，返回原v1 input_directory和allocations；`preflight_generation`允许hash集合仅三节点已验证内容hash。

- [ ] RED：`test_wall_v3_preserves_v2_v1_canonical_ledger` 从CPU旧失败fixture构造v1/v2/v3，钉住6payload/3260/200/seed、shared original allocations、1/199/200、无v3本地池/账本。并用只读真实第一组pins确认旧PROVEN与原18文件身份保留，拒绝first attempt1及attempt2；不能在真实ledger写测试allocation。
- [ ] RED：`test_wall_v3_rejects_ancestry_and_receipt_drift` 覆盖错v2 expected hash、错v1祖先、copied directory、payload/archive/old evidence漂移、未知ledger hash、ordinal gap和缺前次terminal；未完成allocation一直消费，不能被重建协议变回未执行。旧v1/v2当前源漂移继续拒绝。
- [ ] GREEN：新v3 header增添明确origin/直接predecessor信息、三节点受验hash、D/S/time_scope合同和新runtime source/archive pins；旧六payload含budgets.json原字节仍引用，不改rcap/wall值。保留v2 predecessor副本/档案及v1证据pins；验证旧归档自身SHA而非要求旧源码等于新runtime。不得用“放宽source drift”获得迁移；新生产只由新v3的当前source/environment匹配授权。
- [ ] 只新建 `producer/recovery-wall/protocol/`，真实v2作为predecessor、固定expected hash；本步骤纯CPU freeze/default preflight，actual_calls=0。继续用现有CLI `--prepare --successor-of ... --expected-predecessor-hash ...`，CLI默认PREFLIGHT_ONLY；对0002仅只读preflight，不传execute-once。
- [ ] RED→GREEN命令统一 `PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider --basetemp=/tmp/bigsmall-r07-wall-tests tests/test_protocol_generation_sources.py -k 'recovery_wall or wall_v3'`；新增测试必须先有真实RED输出再实现，测试全部为CPU，native initialize设fail sentinel。GREEN后只回归已有 `successor or actual_reset_elapsed or budget_uses_fault_start or execute_preserves_allocation or wrong_review_pin or actual_path_wires or wall_deadline` 受影响集合一次，测试数实报、不把作者/独审相加。
- [ ] Ruff/format只查上述4文件；mypy只查3 source文件。不顺手格式化teacher其余现存代码；若当前基线本身有style失败，保存已存在失败并仅修本轮影响项，不宣称全文件通过。
- [ ] 作者freeze：限定四源码before/after SHA、RED/GREEN/static命令与exit、v3 header/archive/source/环境pins、旧v1/v2+原首组18pins不变、canonical账本计数和actual_calls0。新建report.md/json/source-hashes.json/日志；不复写旧review或本计划。
- [ ] 独审只审一次静止owned切片，重跑上述受影响CPU及一个独立D超时/真实teacher前dispatch反例，核查observer异常不会误当guard、收紧alarm/terminal范围、v3完整祖先/账本。结论最多PASS_SCOPED_SOFTWARE；发现问题按用户规则先取得下一轮Astra计划，不自发actual/修到扩大范围。

## 一次actual前置与OC门的分离

**现在可以完成：** 上述四文件软件、开发专用真实D reader、fault-start原件/每步及动作检查、开发terminal校验、v3迁移、CPU/static/独审。它们不等待外部UTC、Max、九组校准；但计数实现/平台/suspend合同证据、live owner、完整日志和独审不能省。

**一次未来开发actual的前置：** root在独审通过后核对v3固定hash/source/environment、可用BOOTTIME与boot/time namespace/进程身份、原1/199/200及首组18pins、唯一未消费预注册assignment的新输出、renderer全局串行、磁盘/byte预算、无活动alarm、四个T5边界真实接线。之后单独列明一次开发actual的assignment/output/费用/失败保留；只有root进入后续执行切片才可运行。本计划以及本轮实施/独审不执行run0002，也不重试0001。无论结果，独立重算物理proof+D receipts；失败先保全，再Astra下一轮计划，无隐式重跑。

**仍未完成的正式门：** OC1冻结且验收operational reader/authority/数学与真实平台生命周期语义；OC2真实startup/RESET/capture来源；OC3所有消费者/预算/lease闭包与真实restart/suspend证据；OC4主方法/B0—B5共同域/完整wall成本和fault-Rcap。R07这条局部开发owner不得冒充上述全部完成。R4/R5独立九组、完整未来D/S horizon、B0资格→INITIAL→METHOD→另120功效→FINAL、全200/固定机会与原G4/统计门继续原顺序。

原首组17.45秒上界保留，不能导出后199组wall合规。若未来正式协议决定旧首组缺所需D receipt，只能另写兼容性/不可用判定并保留分母，不能补造receipt、重标原PROVEN或重跑第一组以覆盖原记录。所有本轮新报告维持formal_accepted=false、g4_measured=false、真实硬件NOT_STARTED、S3/S4 LOCKED。

## 本次计划校验与交付

本次仅本地只读定位/读取和新建plan.md/json，未运行pytest/static/actual或网络，未修改源码/原件/Stage/Git。十四项固定输入SHA在写入前再次核对。计划已自查：D/S、deadline等值、真实owner/生命周期、不可中断调用局限、terminal/记录保全、三代协议与共享账本、最小RED/GREEN、独审及一次actual前置分别有任务覆盖。用户指定的Astra规划角色来自root派单；运行时具体模型身份没有独立验证，不将角色名当作模型身份实证。
