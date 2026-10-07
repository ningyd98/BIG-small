# Astra Round66 — RW1 事件与活 backend episode 的来源绑定

状态：PLAN_ONLY_RW1_EVENT_EPISODE_PROVENANCE_NOT_IMPLEMENTED；2 tasks。Task1 尚未实现或通过。

## 问题和原始证据

Round57 RW1 Task1 says END validates original TARGET_MOTION_STARTED episode/step/S, but the actual immutable backend event has physics_step/sim_time_s and no episode_id. Episode belongs to the exact live backend._episode_id. Resolve that plan-interface assumption within the two authorized producer/test paths; do not fabricate an event field or modify backend.

冻结接口收据：`artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/interface-observation/receipt.json`。原 TARGET_MOTION_STARTED 没有 episode_id；backend.reset 设置 _episode_id 并清空 _fault_records；fault_records 返回字典拷贝。此问题属于计划接口假设差异，不是backend错误或失败物理actual。原owned两文件和准备前归档保持，RED0。

## 限定范围与前置条件

只可修改 producer 和 tests/test_protocol_generation_sources.py；新增证据限 `artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/round66/**`。ROOT followup现有RW1 agent内联继续，禁止子spawn。原round57计划和ROOT Task1授权保留，不解锁teacher/backend/OC1/worker、RW2/3、freezev3或actual0002。

OC2 may modify its new operational modules and worker after Round65. ROOT may update six current summaries for Stage61. These active paths are not pinned, not edited, and no global source/docs quietness is asserted.

- ROOT reads this plan and follows up the same existing RW1 implementer inline; no new subagent or spawn retry.
- Before edits, compare bounded plan input pins including original14, two current owned files, their before archives, frozen interface/platform evidence, ROOT authorization and original plan. Record this plan.md/json pins and create exclusive round66 evidence directory; preserve every original report/receipt.
- Verify no other writer owns these two paths; require only that bounded ownership window. OC2 worker/operational development and six ROOT stage docs remain independent and are excluded from pins.
- All exec require_escalated; Python uses .venv/bin/python with PYTHONDONTWRITEBYTECODE=1. Planning/static contract reads use stdlib; CPU tests later run under original scoped authorization with native initialize/fault/physics/camera/provider sentinels.
- No real backend creation/initialize/fault injection, renderer, physics, camera, provider, network, actual0002, freezev3, Git or stage-document writing. Reuse saved platform evidence; no new real BOOTTIME/platform capability probe.

## 来源与因果合同

1. Production owner authority remains the original private renderer-owner/allocation/attempt/process lifecycle relationship. At bind/BEGIN verify exact backend object identity against private owner-held reference, nonempty live backend._episode_id and fixed owner episode; caller episode_id/step/S arguments, if retained for compatibility, are equality assertions only and never authoritative values.
2. Read BEGIN step from owned backend.total_physics_steps and S from owned backend.get_sim_time(), and episode from owned backend._episode_id. Verify valid non-bool nonnegative integer step, finite nonnegative numeric S and stable identity across sampling. Record explicit origin labels for all three sources; do not silently replace a missing episode by caller data or a descriptor.
3. Before the one injection represented by BEGIN, save the owned fault-record sequence length N and detached exact original prefix; preserve original order and payload. D lower b-minus and immutable BEGIN must precede injection, and deadline=b-minus+60_000_000_000 ns is fixed. No public API accepts caller events, event ordinal, success flag or copied dict as authority.
4. At END revalidate same exact backend, same nonempty episode and owner/process/boot/time-namespace/allocation identity, then read fault_records only from that backend. Require the prior N records unchanged and exactly one fresh appended TARGET_MOTION_STARTED at ordinal N; reject no event, stale/reused ordinal, extra/duplicate/foreign events, truncation/reset or prefix mutation. Ordinal means source-list position in this owned lifecycle, not an invented backend global event ID.
5. Read the new event original physics_step and sim_time_s without adding episode_id. For this synchronous inject_fault interface, require event step/S equal the BEGIN live backend step/S and the END live backend step/S, with finite valid types and no intervening step/reset; reject mismatch/out-of-range/bool/NaN/Inf/negative. Any future legitimate asynchronous/advancing injection requires another plan, not a weakened range rule.
6. END upper b-plus encloses the completed injection and END source sampling; validate integer ordered D bracket and immutable deadline. If identity/event/read/injection/end validation fails, retain BEGIN and all original partial observations, mark failure, consume the attempt and prohibit successful END/retry. Do not refresh b-minus or change episode to obtain acceptance.
7. Derived owner evidence may store episode_source=owned_live_backend._episode_id, separate begin/end episode samples, event_source=owned_backend.fault_records, original ordinal and unmodified event payload plus step/S-source labels. These fields describe a validated join; they are not fields that existed in the original TARGET_MOTION_STARTED event, not cryptographic/live authority, and not a rewrite of old raw.
8. Every later check/finish revalidates original fixed backend/episode and owner lifecycle with current step/S from source; dynamic step/S may advance there but must retain documented monotonic/domain checks. END same-step rule applies specifically to synchronous fault injection. Task1 does not wire these calls into the real runner/teacher or prove actual motion.

If exact owner/backend causal continuity cannot be established within this private Task1 surface, fail closed and report mathematical/CPU behavior only; do not widen to backend/teacher/runner integration or claim actual provenance. A new interface obstacle requires next Astra.

## D、平台证据和历史边界

D固定deadline=b−+60_000_000_000 ns；n+≥deadline即拒绝。BEGIN和失败原件不删除，起点不刷新，attempt不重用。固定原1/199/200分母及所有旧raw/verdict。平台证据只引用已存report及头文件/manpages/两次API读数，不重跑；本地文档语义与API可用性不等于实测suspend/restart/hostpause、UTC/SI校准或硬实时保证。

## Task 1 — 将真实事件/episode来源解释固定为限定合同及命名RED

1. Revalidate bounded pins and save input-pins-before.json plus round66-source-contract.md/json under exclusive round66. Record absent original event episode_id, separate live backend episode, fault_records copy semantics, causal ordinal/step/S rules and conditional software-only limit. Preserve original plan57 unchanged; this supplemental plan clarifies its field assumption.
2. Write named Task1 tests only in tests/test_protocol_generation_sources.py before implementation: retain original test_recovery_wall_integer_deadline_boundaries and test_recovery_wall_owner_lifecycle_fail_closed; add test_recovery_wall_event_episode_provenance for this interface correction. Use private CPU owner/backend fixture with backend-owned event list lacking episode_id; no actual MuJoCo startup or injected real fault. Exact fixture ownership is software behavior, not proof of actual renderer authority.
3. Require healthy exact-owner/same-backend/same-episode control with a freshly appended source event and correct step/S to succeed. Counterexamples independently exercise foreign backend/copy/forged owner, episode missing/drift/reset, old list event or replayed ordinal, no/duplicate/extra source event, prior-prefix change, wrong step/S including invalid/out-of-range types, caller-crafted equal dictionary/episode/success flag without owned source mutation, failure after BEGIN and repeated BEGIN/END. Refusal must arise from the specific guard, not a generic pending-interface exception.
4. Keep original D boundary tests b-minus100ns and deadline60_000_000_100ns, below/equal/above, S-independent refusal, integer/bool/negative/rollback/order/domain, immutable start and lifecycle cases. Scripted counter jumps demonstrate math only; do not relabel as an actual suspend or restart test.
5. Run one named Task1 RED command after the new tests are prepared, before implementation, recording exact selected unique node identities/command/env/exit/stdout/stderr. Expected missing Task1 interfaces/assertion RED follows this plan; unrelated collection/import/runtime failures are unexpected and require next Astra.

## Task 2 — 仅producer实现Task1并做限定GREEN及步骤报告

1. Implement private Task1 owner/brackets/deadline/lifecycle and this episode join only in protocol_generation.py. Producer source internally reads owned backend state/records; keep private testing seam separate from production authorization and no caller-provided source authority. Preserve all episode_binding_contract and original D/history requirements. Do not wire _run_physical/teacher/alarm/public reader/v3/actual paths in RW1.
2. After implementation is stable, run the same named Task1 test selection once for GREEN; preserve original RED without overwrite. Run only relevant existing producer regression selection once and scoped Ruff/format check plus existing applicable typing check for the two owned files if required by established project validation; no full repo/OC1/OC2 suite or platform/API probe. Save exact commands and outputs; do not add reruns together as independent cases. Any new failure stops for next Astra.
3. Archive resulting two source files under round66/source-after and save before/after pins, permitted code diff and comparison proving protected original12 of14 plus all historical/interface/platform metadata unchanged. Original before archives remain immutable; new tests/source are the only two allowed current-path changes. Do not hash or characterize unrelated live OC2/ROOT docs.
4. Write round66/step-report.md/json with static mismatch→plan→named RED→implementation→GREEN/static/regression evidence, original raw failures, input/version ownership, source attribution and pending independent-review status. Send frozen evidence to ROOT for later Task1 independent review. Author software result may be VERIFIED_RW1_TASK1_AWAITING_INDEPENDENT_REVIEW only if evidence supports it; this plan itself declares no PASS.
5. Keep RW2/RW3, public wall receipt/reader, actual physical injection, fixed-opportunity study, source-positive, native/UTC, formal acceptance and actual G4 measurement unaccepted. No actor Git or actual. Any inability to establish causal live source within allowlist ends in fail-closed software-only limitation and next Astra before expanded work.

## 验证、验收与再规划

命名选择：`test_recovery_wall_integer_deadline_boundaries or test_recovery_wall_owner_lifecycle_fail_closed or test_recovery_wall_event_episode_provenance`。使用计划JSON的base_argv及独立RED/GREEN basetemp，真实命令与唯一node identities如实保存。首RED必须先于实现；GREEN后仅一次必要旧producer回归和限定静态检查。原已完成平台probe及OC1/OC2测试不重跑。

最高作者结果 VERIFIED_RW1_TASK1_AWAITING_INDEPENDENT_REVIEW；ROOT Task1独审仍未完成，本计划不宣告PASS。CPU数学/身份拒绝不冒充真实fault接线或物理实验。formal_accepted=false、g4_measured=false。

Any new root cause, expanded scope, protected pin mismatch/collision or unexpected RED/GREEN/static failure: preserve originals and stop affected repair for next gpt-6-astra plan. Named expected Task1 missing-interface RED continues within this plan. Do not silently invent event fields or broaden backend/teacher access.

## 规划工具观察

首次只读rg将platform-evidence位置写为recovery-wall/platform-evidence，返回该路径不存在exit2；同次输出已定位真实implementation/task1/platform-evidence，随后只读真实已有路径。没有重建证据或产品修改；原错误细节见JSON planning_lookup_observation。

## 实际输入SHA256/bytes（37项）

原14项均匹配；以下清单不含活跃OC2源码或六份动态阶段文档。

| Path | SHA256 | Bytes |
|---|---|---:|
| `AGENTS.md` | `8567e10635a650e2619905d6b3a6e0a885812060fecb1cdd4487bbf118593649` | 1774 |
| `artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/duration-fix/successor/independent-review.json` | `6bb46321f35f65ba85c6ac0a86c26ba6a65276fe1ae9812ddce8190e31f225d1` | 124685 |
| `artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/duration-fix/successor/independent-review.md` | `fe6a13bc7bb5878e56d8469ca0fd38e778e14fa6f37cf26b569a6429350ce0b0` | 2365 |
| `artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/duration-fix/successor/protocol/generation.json` | `9a4f804aef2b9ff77b16dfe1114649ae0d8693aaa848f850680d97e6527e888c` | 12117 |
| `artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/protocol-final/allocations/recovery-0001-attempt-1.json` | `03b2d58ba30c3d50c853627b3515dde6210386dc80e47e163640bbb05af975d6` | 313 |
| `artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/protocol-final/generation.json` | `ea21219b1cb98b7520526457211d4ff2dbfaf5a9311451897351a56b911276ba` | 3927 |
| `artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/raw/recovery-0001/attempt-1/result.json` | `9e0dc35d98acd8ed4bc3e152793fde6eeeccfa8afc79474e19538453b6facc4a` | 3110 |
| `artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/before/protocol_generation.py` | `7038a6d2ff76ae14e83dc5f91028b912c2fd6e25fe1de78f14e6a21e00025d3f` | 39221 |
| `artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/before/test_protocol_generation_sources.py` | `7aef1f510b81f03f42aebf874ab26fe1befc1caf625fa2ce3bd5d032dc36a112` | 29845 |
| `artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/interface-observation/backend-episode.original.txt` | `59fdc0da540e6c324f1b85d973006dbe7bb0d0df31b797ccafcad2623622cf7e` | 1082 |
| `artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/interface-observation/physical-observation-episode.original.txt` | `a2e13133cd310cc6802f6f99f9282aaa99fce1441619fccb4d53c780b18d5b1d` | 883 |
| `artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/interface-observation/receipt.json` | `b8d2e3f0867952d5c5445c5b5a4f7e063a363684de9153942daad51ece922021` | 3402 |
| `artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/interface-observation/report.md` | `a69afb988b1a273dfebc6025b311d4e4ccb122023f0e56c9c2726981174bb602` | 746 |
| `artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/interface-observation/target-motion-started.original.txt` | `da0d593728ed036e90291b6b4c507d1176631263fe7cf1c4ed9972c0b46250a8` | 1440 |
| `artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/platform-evidence/boot_id.original.txt` | `892dfffb9b62464156b7db9d9bbc50634f2b533dc371f4a23458ab986056671b` | 37 |
| `artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/platform-evidence/proc_pid_stat.5` | `c05f058c29e7fedefb2ee9a40e89591c53cbb1924e9b40f17353776be134d27a` | 11394 |
| `artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/platform-evidence/proc_pid_stat.5.gz` | `7f52df6374c8ad43bc6f348f0f831dfc22c710b45aed9fb04d06eaf992ad1d80` | 3755 |
| `artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/platform-evidence/process_stat.original.txt` | `6299e366b65743ceb7578fbf0dc89be3d5bc1f6e8969f07ecbf97a4179d4f60c` | 294 |
| `artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/platform-evidence/report.json` | `1f7dd09001b4b288a81ccdf44adb2682ffeecd8276c82ea59dc525c5888cf7f6` | 3945 |
| `artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/platform-evidence/report.md` | `9389a31fca98e780e7924366fc3f44d998b18f8110bd0b1b471a10af34feeb31` | 778 |
| `artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/platform-evidence/time.h` | `3ec585be656ad1a4f97c4a50dd913a489dafdeac462e4db892d2fc13500b43a7` | 1752 |
| `artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/platform-evidence/time_namespace_offsets.original.txt` | `bd9f74ac5eaa3df538867b32ee7d9240020020a199963645d7ab92f008209ac5` | 64 |
| `artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/platform-evidence/time_namespaces.7` | `9b47730ec917ca3727cbb50ca4939c5865ae150836d692a0f2a3f0f4d61c3bf4` | 8978 |
| `artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/platform-evidence/time_namespaces.7.gz` | `c551a3c87e956e48bef075e779e0ea2e4170962162cb40086a74c1e7a6aa7244` | 3228 |
| `artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/preflight-pins.json` | `ef74365d9f08fb5b033d62c9b3e807521459d1b50af86d49d11445e78444966f` | 3250 |
| `artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/implementation/task1/progress.md` | `4636c18da4301c21088a42e6ff278bf9a71610fbe1ab245ef541b1c7882c066d` | 737 |
| `artifacts/research/process/20261004-ced-development/astra-repair-execution/R07/producer/recovery-wall/root-task1-authorization.json` | `a0bec6df57fe610b5bc9f6fe70a6eb94661a75209588c7efaf522f3d5ce41dcc` | 4437 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round57-recovery-wall/plan.json` | `5b5f47a9f455e3731e58e14092252cadda4f97369aee2a167ccc3d354a9a8450` | 9308 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round57-recovery-wall/plan.md` | `5dd08d0e57660c49044b321820d5ee83d52e6f1c026c494bbaae85eb31fe93db` | 18804 |
| `artifacts/research/process/20261004-ced-development/report-step56.md` | `0d4d494d31729e4d34caf10d2dbce080c7d0052cdcf5fe5e65632cd5e7b0c9db` | 7712 |
| `docs/superpowers/plans/2026-10-05-astra-repair-plan.md` | `7e7514b37b7351208176c1d660771facd7dadf668eb3a5cb9de0b3c43aa50579` | 38831 |
| `docs/superpowers/plans/2026-10-05-operational-clock-repair-supplement.md` | `6bf5022020253b73f08d00adf2785e1ca86ff1e34ca389a55e6c716fcc147030` | 6081 |
| `scripts/generate_rgbd_protocol_evidence.py` | `f887cf186d18fb1f662fa6afb0cb9cab29969a1568601e1e3ddd83500ba097b1` | 3249 |
| `src/cloud_edge_robot_arm/datasets/rgbd/teacher.py` | `a7150e980ff0bcf901128701cfce2dd7569263158d5716bd311473975179a033` | 10210 |
| `src/cloud_edge_robot_arm/research/protocol_generation.py` | `7038a6d2ff76ae14e83dc5f91028b912c2fd6e25fe1de78f14e6a21e00025d3f` | 39221 |
| `src/cloud_edge_robot_arm/simulation/mujoco/backend.py` | `b7b6026b1173448de826e53253ae74f92b6b70ea46a404e10054c5cd451a62a6` | 49867 |
| `tests/test_protocol_generation_sources.py` | `7aef1f510b81f03f42aebf874ab26fe1befc1caf625fa2ce3bd5d032dc36a112` | 29845 |

执行者在before/after另记录本plan.md/json pins。规划仅写本计划两文件；产品/测试/平台probe/actual/Git/network/newagent均0。
