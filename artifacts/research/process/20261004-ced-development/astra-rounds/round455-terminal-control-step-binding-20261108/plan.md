# R455 — 终止 CONTROL 与最终物理步绑定

实际 gpt-6-astra，2026-11-08。仅规划，0测试/physics/render/model调用。评审反例尚未执行；来源原文保存于 `intake/reviewer-static-finding.txt`，静态源码原片段见 `intake/static-source-evidence.txt`。22 个输入及完整副本/SHA256见 `intake/input-pins.json`。原R453 final-focused原件已确认50 PASS、rc0、reaped=true、无source drift；本轮不重跑该50节点。

## 根因与范围

现终止两条命令已要求 hold→STOP，二者处于 TERMINATION、当前步N；尾 CONTROL 已要求唯一、最后分配并嵌套于 STOP。遗漏在于 CONTROL 当前步仍来自它自己的 source 声明，payload只被要求为该声明+1。终止CONTROL既不被任何 PHYSICS 引用，又被合法内部STOP例外排除于 ordinary guard语法，因此同步改写多份记录仍不能证明它实际对应最终 state[N]。七步软件图关节不变时，把尾 CONTROL 的当前步改为N−1、payload目标步改N、时间改为state[N−1]，可能满足现所有自洽条件。此为R453/F4来源图最终状态绑定遗漏，与R454转换完整性独立。

仅允许 `src/cloud_edge_robot_arm/research/native_source_effect_graph.py` 和 `tests/test_native_effect_graph.py`。shared helper、reader、backend、raw schema、guard及所有既有转换器只读。不新增产品模块。R454正在修改的 recorder 与 observer-failure 测试明确不pin、不依赖其旧SHA；本轮不编辑它们。

## 实施与精确测试

1. 实施前复核冻结pins。R454可以独立完成；任何R455测试启动前必须等待R454阶段结束并回收，读取其最终批准diff/step-report，将那两个依赖文件的批准后SHA加入R455 implementation/applicability与新runner执行基线，不能改本轮原冻结pins或把并发漂移忽略。其余输入漂移需说明是否已批准，否则停止。新runner只允许本轮两路径编辑；R454完成状态作为已批准先前依赖，不成为本轮额外编辑许可。
2. 新增唯一节点 `test_terminal_stop_control_binds_final_physical_state`，复用现 `fixture/recorded_effect_graph/effect_audit` 通过真实backend wrapper/recorder/guard生成七步 SOFTWARE_ONLY 图；fake engine/camera仍不启动MuJoCo或render。先用未改原件跑正常独立校核，明确 n=7、STOP command当前7、唯一extra CONTROL当前7/payload8、合法嵌套及最终state，原legacy UTC UNAVAILABLE、native/full-H仍未获资格。不能mock检查函数或手拼合法图。
3. 在独立复制目录中对唯一extra CONTROL做同步反例：control_sources.physics_step=N−1，control_state.physics_step=N，control_state.sim_time_s=state[N−1].sim_time_s；对应 operational_events begin_step/end_step=N−1，backend_operation_ledger同operation的BEGIN/END physics_step=N−1，RawInterval start_step/end_step=N−1及start/end_sim_time_s为前态时间。若原结构有同一终止CONTROL的其他真实时间字段也保持此反例内部自洽，不能新增原来不存在字段。保留operation ID、episode、命令、control targets/pre joints/equation、OC1括号/顺序、total_physics_steps=N、states、所有真实physics/control关联和STOP的S=N不变。用原helpers重新封存仅复制图的JSON/库存；断言原目录字节不变。该反例应穿过hash一致性而被语义锚点拒绝。
4. 唯一 terminal-red 只跑新增节点。预期原正例校核完成后，负例 `pytest.raises(ValueError, match="terminal CONTROL current step")` 出现 `DID NOT RAISE`，恰1 FAIL。不是API缺失、import、fixture失败、意外KeyError或hash拒绝；如实遇到其他结果则暂停新Astra，不能改负例到无关失败来完成RED。
5. 最小修复优先放在 `validate_native_command_controls`：已收集每个PHYSICS引用的control interval后，求未引用的extra，严格唯一；该source.current step必须是N、对应CONTROL_APPLY interval为N→N且COMPLETE/error=None、payload target step=N+1。采用明确 `terminal CONTROL current step` 错误定位该当前步锚点。后续现generic replay在step=N下自然绑定state[N]的sim_time、pre joints、真实target/equation和episode，不放宽容差、不猜测状态。已有graph检查必须继续将同一个extra interval/operation映射到最后STOP内部CONTROL、要求STOP当前N、嵌套和无后续physics。可集中局部检查避免重复，但不能只增加尾部某一标签检查而让另一公开校核路径遗漏。N+1是控制payload指向下一步，绝不是多一实际physics。无需修改backend、制造guard或增加普通STOP guard校验。
6. 保留新节点正常STOP正例与同步回退负例，受影响文件唯一 terminal-green 跑原五节点+新一节点，预期6 PASS。同一新节点可补充对原终止source/payload/state对应关系的正例断言，不增加测试节点/额外试运行。

## 有界验证与交付

exact `spec-templates/terminal-red.json`、`terminal-green.json`、`ruff.json`、`format.json`、`mypy.json` 及plan.json内展开规格已生成；新R455runner使用原R413 bounded_stage、独立新目录/basetemp/env/JUnit/events。保存新commands与执行前后source基线，拒绝覆盖任何已有stage。每阶段child120s/outer240s、attempt1、串行。RED后实现，再对批准两路径一次必要import sorting/format；随后GREEN，ruff check两路径、ruff format --check两路径、mypy --follow-imports=silent仅kernel各一次。无collect-only、诊断probe、重试或R453 final50重复。异常失败/新根因/范围扩大停止相关工作并实际Astra新计划。

保存step-report、原stdout/JUnit/events/result、diff及后SHA；与R454报告分别归档。原whole-change reviewer后续scoped复核纳入本F4修复，无需新whole review。R453/R454历史原件不改，软件通过不代表真实full-H。

未来未运行prepare/full/read新runner/source overlay加入本轮准确批准diff及最终pins；已有命令/规格/结果保持。fresh prepare仍必需，依赖实际前软件和scoped review全部通过。R450服务授权完全独立，本计划不授权停/启服务。

原实际额度不变：首组seed439001一次；physics12960、explicit12976、implicit12962、render64852；wall1800s/outer1920s、RSS8GiB/raw16GiB。不扩九组、不开模型请求。本轮actual0，实际仍NOT_RUN，native UNKNOWN。

自审：反例明确标为未执行；STOP现有锚点和遗漏CONTROL锚点区分清楚；只读共享路径及R454并发依赖分开；正常原件与复制mutation配对；一次RED、六节点GREEN及有限静态足够覆盖本纯检查变化。
