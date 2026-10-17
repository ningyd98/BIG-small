# R248 — writer start 条件同步

实际作者：`/root/astra_status_plan`，实际模型：`gpt-6-astra`。仅冻结计划，等待 ROOT 门控；本轮未实施或运行验证。

R242 实际 child/wrapper 均退出 1，三个节点均在第 221 行 episode 计数失败。三个 writer 的 start.wait(10) 已先抛异常，随后才记录 PRIVATE_BOOTSTRAP_ENTRY_BEFORE_LOCK；没有原 SAVE 入场、真实双 COMPLETE 或正向 legacy 变更，因此不是合法 RED。R242 三槽均已消费，原始证据保留。

真实夹具先启动 writer，再由主线程进行 genuine poll；start 只在真实 private 入口或现有 finally 设置。十秒 host 等待给该前置工作加了机械时间假设。性能主因、阶段耗时和全局死锁状态仍未知。本轮只修这个同步条件，不改变任何 OC1、任务预算、TTL 或产品行为。

## 唯一既有源码变化

`assert data['start'].wait(10), 'R223 writer start barrier timed out'`

改为 `assert data['start'].wait(), 'R223 writer start barrier timed out'`，仅一次删除 ASCII `10` 两字节。原 release.wait()、其他 wait/join、所有断言、observer 与产品不变。原 finally 仍设置 start/release 并 join；全子进程仍 600 秒加总计 15 秒清理。finally 导致的释放不能作为正常竞态见证。

- before：16527 B，`c14e1f7b02f4e3d93a94245a075c6d8a7d3d386705a61afd173acea979e054ae`。
- 预期 after：16525 B，`106fdeaaa0ff47cb0584fa6f79e1a0e8afef82bc58622b618717cd88a6038e14`。

唯一 Sol 保存完整 before/CAS/native actual/diff/report，并在本轮新建 prepare-evidence.py、run-command.py；从物理冻结 R242 脚本读取，候选先持久保存，不依赖易失 store。ROOT 完整读新脚本后才预留执行。原脚本、原角色和原失败不可覆盖。

## 独立新额度

顺序只有 baseline 120 秒一次、E9/F63/F7/F82 Ruff 120 秒一次、原三个节点恢复 RED 600+15 秒一次。各槽双方初始 HELD 0/1；精确 argv、有限 env、cwd、外层时限见 plan.json.commands/execution_rules。ROOT 每次先预留再发送 literal，无 prelaunch helper、试跑或重试。旧 R242 三槽永久 spent，R223 后四槽、GREEN9、父 GREEN7、fresh review12×600、Git0 保持 HELD。

RED 沿用精确 R235 import-only prerequisite，不加载诊断 trace/sampler。新输出、basetemp、数据库全部在本轮 workspace 持久目录，运行前必须不存在且非 symlink；不清理或复用旧路径。完整原始流、JUnit、cases、资源、前后 source/index 和实际 tool 返回保全；控制台只输出不超过 6000 UTF-8 字节摘要。

## 严格证据适用性

输入观察 296823 B，SHA256 `9baefb01351bb854aae9b4ffbac2ee5305a41687f49eecf22945cedf5ecee31b`：344 个精确输入 pins、27 当前源及实物、211 保护项，533 项普通规划核查全部 true。该读取不是产品验证。

以实际 R242 source-index schema 为准：sources27/protected211/scripts3/history_observations812/explicit_maps13/historical_registry35/sidecar_states90/input_records28。不能套用 R239 字段或把计数当列表。身份仅 path/bytes/sha256。

保留既有 13 个精确归档映射，包括旧 84e fixture→R239 实物；另加 c14 fixture→R242 baseline 实物，以及最终结算 index 中准确 7 个 before/archive 对。旧 invocation 只用其自身已记录 fullbytes 核对应世代，不能按同一逻辑路径豁免所有历史。当前新目标 106fde 单独核对。

35 个历史缺失项仍逐项隔离、原因未知、bytes/hash/match 不伪造；原 90 sidecar 缺失状态保留。R242 新工作区 6 DB/18 sidecar 必须每步严格前后核验，不属于缺失例外。新的运行数据库不代表旧数据库恢复。任何未列明漂移或旧缺失文件重新出现先 STOP。

最终 STATE/PHASE 已按 R242 receipt 核验，只是激活时点快照。ROOT 后续只能完整 before/CAS 后追加 planning.R248 与 PHASE 事实，精确建立该世代归档；R242 最终控制、旧计划和证据不动。

## 合法 RED 与停止条件

必须真实走到 episode、bootstrap/binding、两库 COMPLETE，writer 原 SAVE 正常返回且无异常，正向 legacy 写入/readback 真实成立，然后原 late-binding 断言失败。仅 child1/wrapper1、line221、任何 timeout、缺 COMPLETE、无正向变更或清理不完整都不合法；保存并消费该槽，STOP 交下一 Astra。资源分母仅本次实际观察，不沿用历史 564。

取得合法 RED 后仍须下一轮明确 continuation 才能修 event3；本轮不放行 GREEN、review 或交付。T2/T12/native/formal 均未完成。

R249 的失败 store 路径已放弃，本计划从物理 R242 plan.json 核完整 22524 B / f6d8aef8b1e7ee62aadaa55c95b8a465878d7eda46fe6e48f27f4d7a0c945137 生成，先保存 prepared-plan-candidate.json，再逐字保存 plan.json；MD 概述与 JSON 合同一致。冻结后 STOP。
