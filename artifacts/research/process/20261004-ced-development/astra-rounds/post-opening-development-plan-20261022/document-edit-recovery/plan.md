# 新规划文档编辑恢复计划

**Actual model: gpt-6-astra。** 仅计划，不修改主稿、不测试、不Git。

## 原始失败与根因边界

原错误上下文实际存在且唯一；回执所述最后hunk目标位于前一hunk之前，与单向游标匹配失败一致。所保留回执未含完整原补丁字节，因此不声称已重演内部游标；文件零变更已由当前SHA与before/after核实。

只读核对：失败期望段出现1次，在第99行；其前一提交hunk对应正文在第102行。当前主稿SHA256仍为`66802bfa96c70532c2dd6d544dfefdca14e1d6633d09ed9759e8794dfe1a2e1f`，与失败前后相同。

## 限定修改

1. **Task1 当前输入/角色步骤：** 明确当前HEAD及旧冻结精确HEAD/输入适用性；仅文档变更不自动放行，不修改旧期待值。
2. **Task2 文件表：** 使用src/cloud_edge_robot_arm/simulation_runtime/{operational_lease,worker}.py与src/cloud_edge_robot_arm/vision/worker_runtime.py；其他源码补完整src/cloud_edge_robot_arm前缀，tests引用明确tests前缀。
3. **Task3 文件表及第二步/出口：** 先补原源码路径前缀，再写P7完整支持域/完整horizon保守界必须有限且≤10mm；与正式G1条件样本定位P90≤10mm+coverage分开，不互相替代。
4. **Task4 文件表、probe及INITIAL前步骤：** 源码路径前缀明确；P3现行probe在P6D完成且P8/D相关源静止后绑定；INITIAL前首次登记方法/消融比较、统计与多重检验规则，方法精确开关METHOD冻结。
5. **Task5 文件表及开发准入步骤：** 源码路径前缀明确；exploration依INITIAL/风险/预登记有限候选/当前native源，不依自己的selection结果；accepted依完整selection证据，LOCAL_RECOVER仍关闭。
6. **Task6 文件表、Task7首次步骤：** Task6源码路径前缀明确；Task7仅复核Task4已登记对照/统计规则并冻结METHOD实现，不把INITIAL前置放到T13后首次启动。
7. **Task8正式采集首步：** 明确FINAL及G0/G1正式入口条件满足后方可开展冻结正式比较；保持全部原统计/安全/分母阈值。

## 一次写入恢复

1. 保存原失败回执、编辑前完整主稿与hash；本计划固定主稿66802bfa…，运行写入器前须全hash相同。
2. ROOT按文件实际出现顺序准备old/new全文段落映射（仅上述范围）；每个old在原输入中出现恰1，区间不重叠、无倒序依赖，所有预期目标先在内存检查；不存在或多次则零写入并停止，不扩大匹配。
3. 基于原输入位置升序构造完整候选字符串，保留所有非目标区间逐字；在内存确认各项变更、引用路径及依赖语义，写入前重读主稿SHA防并发改变。
4. 所有检查通过后仅一次提交主稿写入（可用同目录安全临时文件原子替换，保留before），保存after SHA、精确diff与old/new映射；禁止重试原失败多hunk补丁，禁止部分成功后补修余hunk。
5. 只核对新文档hash、JSON、引用/链接和本轮限定语义；确认现有源文件存在只做读取，不执行任何gate/产品导入/测试/模型/物理/SQL。新不匹配或写入失败立即保留并再次Astra，不反复尝试。

## 前提与验收

- 本计划及父计划的current_document_corrections继续适用；真实输入hash未变。
- 仅新主稿和本轮恢复证据可写，产品、旧冻结计划/角色/额度不写。
- 旧R296/R298运行前提不因文档校对而满足；不执行旧gate。
- 所有七类已批准校对落在新稿，非目标字节不变，相关引用真实存在。
- P7保守界与正式G1 P90区别清楚，P6D后probe、INITIAL前消融登记、两阶段开发准入及FINAL+G0/G1无循环。
- 原失败和before/after证据保留，新计划不改旧期待值、不提升历史来源或研发验收。

## 输入SHA256

- `/home/ningyd/文档/ChatGPT/BIGsmall/docs/superpowers/plans/2026-10-22-post-opening-development-plan.md`：`66802bfa96c70532c2dd6d544dfefdca14e1d6633d09ed9759e8794dfe1a2e1f`
- `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/post-opening-development-plan-20261022/root-document-patch-failure.json`：`b4959052a120572be5ad33019a31216f180e3ade3e394ba79bbf381f13d5546d`
- `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/post-opening-development-plan-20261022/root-draft-review.json`：`265f17eb2b2c3367035a23f7cb17862ac0ed1db16b25d3db5dd8a59255a6bbab`
- `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/post-opening-development-plan-20261022/plan.json`：`07be64bffa8436d29835add88ba900858b2d98d29468a9da89d8fd888b7c69d6`
- `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/post-opening-development-plan-20261022/scope-clarification.json`：`8c0acfbd48f146a39f87f95c341e0cd30d6bc0a0953415b1f3d96a5219066007`
