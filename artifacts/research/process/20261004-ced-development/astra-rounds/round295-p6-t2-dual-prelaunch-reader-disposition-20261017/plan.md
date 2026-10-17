# R295：弃用 dual 启动前可选路径读取

实际 gpt-6-astra 处置计划；仅规划，STOP 等 ROOT。

`96e32f exit1` 是可选 metadata reader 对猜测路径 `D289/implementation/root-command-ledger.json` 的 FileNotFoundError。原四项读取已完成，第五项失败；AUTHOR、prior、tool arguments 尚未读取，dual runtime invocation 为 **0**。这不是产品或诊断运行失败。原完整调用和返回保持不可变。

独立必要物理读取 `096e92`、`cd5eb5` 均 exit0，确认真实 ROOT 路径由 `P289.runner_contract.roles.ROOT` 与 reservation 的 `root_role_after.path` 一致指定为 `D289/root-command-ledger.json`；AUTHOR 仅取明确 AUTHOR 项。不得把错路径建立为别名，不遍历 roles 其他字段。原计划 literal 与 reservation.exact_tool_arguments 完全一致。

处置为 **ABANDON**：零修复、零重放、零替代 reader、零新 builder/validator。ROOT 完整接受本计划并正常复核 13 个有限物理输入后，可以将**已预留而尚未调用的原 R289 dual literal**明确重新 release 给同一 soleSol。不重做 gate，不再预留、不退款、不重置角色，也不重跑两个已接受 wait。Sol 不追加自创启动前读取，直接调用 ROOT 所发完整工具参数对象。

reservation 身份为 `R289.dual_first_invalidation.d2483c9a-8aac-4400-9673-2b0ef6be10b0`。ROOT 当前 42871/309a37ec…，AUTHOR 32509/91730e13…；原 reservation 内 copied command 的 HELD 字段不能用于倒退当前账本。完整六份 before（失败、计划、reservation、两角色、prior）已物理/base64/mode 保全；未来合法运行的角色变化仍沿原 R289 生命周期，不将本轮快照当永久 live pin。

完整 literal 和所有边界见 plan.json：env-i，child600s、cleanup15s/TERM5s、outer900s/KILL15s、原生 faulthandler540s、raw32MiB及原监测、stdout≤6000UTF8。实际对象先完整保存再显示；若有 session，仅同 session ≤60s poll，不重放。未知独立流仍为 null。结果即使 PASS 也只算诊断，原资源、DB、线程、hook 和独立 ROOT 验收合同不变。

R293报告、源码及 native、ROOT1341/最终2876证据、两 wait 接受、原 memory next_key=sqlite、STATE/PHASE及历史边界均不改。本轮新增 runtime/tests/static/SQL/probe/review/Git/metadata恢复执行额度全部为 **0**。R295 步骤报告应如实记录 reader 失败和当时未启动 runtime；不得把 96e32f 改写为成功。当前不运行任何 literal。
