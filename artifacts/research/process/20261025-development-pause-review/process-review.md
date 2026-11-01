# 暂停期间独立流程与证据审阅

审阅基准：2026-10-25，HEAD `dd9df375e1d372490145327bcbfee5804352fcc4`。仅阅读原文件、JSON 与源码文本；未 import 项目/runner，未运行测试、候选、采集或 DB 引擎，未创建修复轮、修改证据或调整账本。仅新增本报告。开发仍暂停。本报告不是 GREEN 的完整运行后接受，也不释放执行。

下文 `Rxxx/` 指 `artifacts/research/process/20261004-ced-development/astra-rounds/roundxxx-…/`；`总计划` 指 `docs/superpowers/plans/2026-10-22-post-opening-development-plan.md`。引用 JSON 字段为实际文件中字段，计数由现有 JSON 静态读取计算。

## 1. 当前真正关键路径

当前最先缺的是**对已经完成的 GREEN 做独立事后接受**，不是重新运行 GREEN，也不是再设计一次诊断。随后才是仍未运行的 `codec_regression_01` 与 `utc_memory_01`。这既是最短推进路径，也是现有 runner 的实际依赖：`R365/implementation/run-validation.py:1149–1169` 要求所有前序槽位 SPENT 且 `ROOT_accepted=true`。

已交付与未证明须分开：

| 层级 | 已有事实 | 仍缺什么 |
| --- | --- | --- |
| 产品候选 | 当前 patch 仅把 `_copy` 的 Mapping 条件改成 `type(value) is dict or isinstance(value, Mapping)` | 这行候选能否使真实 UTC 节点完整结束 |
| 微测试 | RED 原 child=1、最终指定断言失败、语义前缀完成、实际精确 dict ABC 次数4，ROOT 已接受；GREEN 原 child=0、实际次数0、语义前缀完成、observer 恢复、validation/test 均 true | GREEN 完整 ROOT postrun 接受尚未发布；微测试不是超时修复或 T3 证明 |
| 当前系列 | 两次运行均保留 result/completion/transport；ROOT 与 AUTHOR 前两槽 SPENT1/0、后两槽 HELD0/1，一致 | codec 回归和原完整 UTC-memory 节点尚未执行 |
| 产品里程碑 | 历史 R350 两个节点获限域接受 | 当前源码九节点 T3、B9/full B、C、P7/P8、D 的完整链尚未验收；正式研究更未验收 |

证据：本目录 `pause-state.json:GREEN_observed/slots`；R365 `root-copy-red-acceptance.json:all_pass/ROOT_accepted/accepted_scope`；两槽 `implementation/*/result.json:child_exit/validation_pass/errors/cleanup`、`completion.json:finalization_complete`、`author-original-transport-return.json:exit_code=0`；两份真实 `copy-dispatch-case.json:semantic_assertions_completed/exact_dict_classifications/observer_restored`；ROOT/AUTHOR live ledger 的 `commands`。

原600秒未完成根因仍 UNKNOWN。R365 本身明确允许先验证这个确定减少冗余工作的候选，并不以“先完全解释历史超时”为执行出口；不能让诊断完备性重新吞掉产品关键路径（`R365/plan.md:13–19,25–38`）。如果当前 UTC 完整通过，只能获得该节点在当前源码上的候选证据；后续 T3 冻结评估/复验全部九节点仍是现行计划要求，不能拿微测试或旧两节点直接替代（`plan.json:acceptance_and_followup.T3`）。

## 2. 流程复杂性已经成为实质堵点

**判断：是；这是由实际新增的前置工作与故障分支支持的结论，但现有材料不足以量化它占总耗时的比例。** 不能据此宣称原600秒完全由流程或仪器造成。

第一，所选诊断工具本身成为了一个需要研发、审查、修复的子产品。R354 原运行前已审查70个 runner 定义、51个 observer 定义与23个目标（`R354/phase-step-report.md:3`）；R356 解决 native SIGUSR2 所有权，R357 解决资源 profiler 共存并引入临时 test binding adapter，R358 再解决日志失败会阻断原应用调用的路径（各自 `plan.md:5–17`）。这些问题确实需要处理，因为既然引入仪器就必须控制其干扰；但它们不是机械臂正常动作本身的功能要求。随后 R354 发生 SIGSEGV，R363 去掉主动 SIGUSR2 后仍在600秒不完成。现有证据既不能证明仪器导致崩溃，也不能证明两次诊断解决了产品问题（`R354/phase-step-report.md:5–11`；`R365/root-r363-diagnostic-disposition.json:limits`）。R365 已明确取消新 observer/profiler/SIGUSR2，恢复后应保持这个收敛方向。

第二，行政错误持续插入产品关键路径。可逐项核对：R355 是计划中的 runner 基线引用冲突；R359 是读错步骤报告路径；R360 是27,591字节元数据生成脚本多一个右括号；R361-B 是摘要字段 KeyError；R362 是同路径 Delete/Add 被拒；R364 是 ROOT 静态检查器漏建模 `__file__`；R366 是把不存在 conftest 传给 rg（各 `plan.md:3–18`）。这些并非产品失败，但实际都消耗了新 Astra 计划、输入 pin、角色激活和 disposition。用户要求“新问题先 Astra”不能被豁免；应减少制造这些问题的机会，并对同一根因合并处理，而不是继续扩建元数据生成器。

第三，历史保全被实现成了递归运行依赖。R350 gate 为381项（`R350/phase-step-report.md:3`），R354 为539项，R363 继承570项，R365 RED644项、GREEN649项。当前 GREEN 总计114,081,904 B，其中389项/101,782,691 B 路径属于 `artifacts/research/process/`；这不是“649个产品依赖”。R365 `source-proof.json:dependency_pins` 另列157项直接准备依赖。runner `verify_lineage` 在 `1247–1261` 行要求把旧 gate 的所有 pins 与新输入继续带进当前 gate，旧账本还在 `1194–1227` 行受检查。这样每轮历史报告、行政修复和接受链都会变成后继运行必须再次满足的条件。**保留历史文件是必要的；让所有历史文件永久成为当前运行前置，不是 AGENTS.md 明文要求。** 当前两 gate 仍有约束力，本审阅不建议临时绕过它们。

这个数量不能直接当作运行性能成本：本次 RED/GREEN 各约0.8秒完成，尚无证据说明114MB pin 库导致原600秒。因此这里指审查、角色交接、生成和适用性维护成本，以及出错面扩张。

## 3. 用户要求与代理选定机制的区别

| 用户 AGENTS.md 必须保留 | 当前额外实现机制 | 可前瞻收敛的方向 |
| --- | --- | --- |
| 实际 Astra 先为新问题/计划外失败规划；同根因可合并；输入 SHA、范围、验证、运行前置和验收边界齐全 | 每次机械读错后再堆多层 activation、source-gate、disposition 与继承链 | 仍调用实际 Astra，但同根因一次处理；计划交付前做完整字段/路径静态核对，沿用已验证读取方式 |
| 保留原始失败、实施结果和验证证据，步骤报告汇入阶段总结 | 历史报告全文、旧角色绑定、旧 ledgers 和所有祖先 gate 永久纳入后继运行 pins | 保存不可变档案及其一次验证的 manifest；后继运行仅冻结实际执行输入和被结论依赖的证据，记录边界 |
| 实施前确认计划与输入仍适用；新根因/范围扩大停受影响工作 | 固定旧 HEAD、同一 live 作者席位、双 ledger/CAS、每节点精确 reservation、禁止一切预 import 的整套方案 | 这些是现行具体计划约束，不是用户逐字指定；未来如确需更改，由适用 Astra 计划明确替代，不能私自忽略 |
| 软件验证、真实运行、正式研究验收分层，不拿通过软件替代真实证据 | 七阶段采证、AST/hunk 全谱系证明、四层接受记录 | 产品/资源关键证据不削弱；纯单测用普通真实 pytest/JUnit/case 与源身份，只有实际需要的运行保留对应资源证据 |
| 已验证交付按明确路径 commit/push，核对本地/上游/远端 SHA；raw/DB 等按边界管理 | 任一文档提交改变 HEAD 后重新展开长祖先适用链 | 约定有限交付点；每次提交后仅明确核对受影响输入/新 HEAD，保留旧记录，不以清单冒充完整复现包 |

现行角色/额度门禁是已批准计划的一部分，不能因为“不是用户原话”就当作无效。简化只能面向后续、明文替代适用约束，同时满足用户核心要求；不需重写历史来实现简化。

## 4. 状态与证据的一致性检查

未发现本次 ROOT/AUTHOR live ledger 的额度冲突：RED、GREEN 都 SPENT1/0，后两槽都 HELD0/1。GREEN 已运行而未接受的状态也明确记录，不能把 `ROOT_accepted=false` 误读成“未运行”。RED 原 result/completion 的 `ROOT_accepted=false` 与后来独立 acceptance 的 true 也不矛盾：前者是保留的运行时记录，后者是派生接受决定。

确有**状态入口易误导**：`R365/phase-step-report.md:3,15` 仍说产品未改、四槽 HELD、等待 RED；`source-proof.json:product_patch_applied=false/four_commands_all_HELD=true` 同样是准备时状态。已验证该步骤报告同时位于 RED/GREEN 的 immutable pins，SHA `3672f89b…`，所以不应覆盖。最新 `pause-state.json`、`progress.md` 与 live ledger 才描述当前状态；`root-r363-diagnostic-disposition.json:next_step` 也是前次暂停时的历史下一步。建议以后新增一份明确标注“截至何时/哪些是历史快照”的阶段结果/当前入口并链接原件，而不是改冻结原件。尚无证据表明有人故意改写历史。

总计划还有一个完成门槛与当前小轮证据粒度不对齐的问题：完整路径明确是 B/C→P7/P8→D→合格 B0/INITIAL，但当前主要状态围绕槽位和 source acceptance。应以“还缺哪个真实出口”作为阶段摘要主轴，槽位是证据管理附属信息（总计划 `46,66,86–107`）。否则 SOURCE_ACCEPTED、OBSERVATION_ACCEPTED、SPENT 等记录数量容易遮蔽“正常正链仍未证明”。

## 5. 用户恢复后的最短可辩护推进顺序

1. **先收现有结果。** 不重跑 GREEN；独立完成它的原 transport、result/completion、JUnit/case、源身份与清理等事后审阅，单独发布接受或明确缺口，再用新增阶段摘要连接冻结的准备快照。若发现新问题，按用户要求交 Astra，不能借审阅偷偷修复。
2. **沿现有计划完成剩余两项。** 在用户恢复、输入适用和原门禁仍满足后，分别预约 codec 与原完整 UTC；不增加新诊断、不扩大 timeout、不削弱断言、资源真实性或 UNKNOWN 口径。两槽已有方案，不应为“重新梳理流程”先造一个新执行框架。
3. **把通过与失败都收敛成明确下一步。** UTC 完整通过则按 R365 的范围接受候选，准备当前源码全部九节点 T3 的有限后续验收；失败/不完成则保存原件，Astra 直接决定最小产品修复或一项能区分具体假设的有限调查，禁止默认再设计通用 profiler。历史600秒原因可保留 UNKNOWN，不以彻底解释历史作为所有后续任务前置。
4. **回到第一个产品出口。** T3→B9/full B→C→P7/P8→D；P7 CPU 来源/协议准备可按总计划66行在不触碰共享源码、教师保护和运行资源时推进，实际采集仍须 B/C 前置。不得倒置为“先完成 D 才能 P7”，也不应等 METHOD/FINAL 才做开发闭环。
5. **在后续适用计划中固化简化边界。** 保留稳定 runner，改为命令/输入清单的有限配置；每轮只审实际差异与相关依赖，历史 manifest 归档复用；一轮一份结果摘要，明确产品出口、已验证事实、唯一下一项、未证结论。禁止为本次暂停审阅另开修复轮或启动上述动作。

应停止的具体行为：反复从全历史重建信任链；为简单报告继续编写大型生成脚本；把诊断工具完善当作产品交付；为保留原件而让陈旧准备报告充当当前状态；用“许多检查全真”替代正常动作正链。必须继续的行为：真实 Astra、新问题留证、原始失败保留、必要的当前输入绑定、有限运行与清理、独立接受、分层验收及已验证交付的 Git 三方 SHA 核对。

审阅过程备注：本审阅一次只读元数据命令因系统不存在 `python` 返回127；该原始工具返回保留在本审阅工具记录中，随后使用已有 `python3` 读取 JSON。未修复环境、未运行任何项目代码、未把该行政现象归为产品故障。
