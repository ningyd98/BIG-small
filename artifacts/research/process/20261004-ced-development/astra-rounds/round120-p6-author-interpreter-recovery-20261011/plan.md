# R120：P6 实施者解释器选择恢复

实际 Astra，2026-10-11。仅处理工具选择，不改R113技术语义。

## 原始失败及边界

replacement `/root/p6_stage_a_sol` 的bare `python`只读JSON命令5817bc退出127，原输出 `/bin/bash: line 1: python: command not found`。随后系统 `python3` 同一std库元数据解析a8f60e退出0；这是已经发生的事实，不追溯删除，也不称产品验证。原工具只有combined output；没有独立stdout/stderr原流。成功8532-token展示保留在会话，不能补造文件raw。精确命令、失败输出及作者收据路径/SHA完整列在plan.json。

根因是已知的裸python别名缺席及作者另选系统解释器。实际核查：四旧owned源hash仍等原R113激活；两新源/测试不存在。stage-a只含六个元数据文件；8验证输出目录和3tmp leaf仍不存在。作者原件明确source_writes0、A20未写、RED未调用；八预算与R119继承账本一致，均used0/remaining1。此结论是原件加当前限定状态核查，不冒充完整进程历史。项目 `.venv/bin/python`可执行，未导入产品、未跑验证。

R119的“stage-a整体不存在”前置仅在此处改为“精确六文件元数据允许存在”，原验证输出/新源码absence要求保持；既有错误文件不得清理。

## 最小恢复步骤

1. ROOT rechecks this small exact metadata inventory/pins, original four owned-source hashes, two absent targets, eight validation output leaves and three tmp leaves. Check .venv/bin/python executable without product import; no74-source rescan or codebase-wide investigation.

2. Before allowing step-report updates, ROOT preserves byte-exact copies of the six current metadata files under R120/original-state with source-index.json. Keep original metadata-tool-recovery files immutable; do not recreate successful rendering or separate streams.

3. ROOT writes new R120 root-activation.json and recovery-check.json binding this plan, prior R119 identity/authority, exact allowed existing six metadata files, source/output state and eight unchanged budgets. May append ledger.md and stage summary truthful tool-recovery note; original R113/R119 plans and activations unchanged.

4. Resume same replacement /root/p6_stage_a_sol under original R113 stageA six paths/A20/eight commands and existing R119 sole-writer separation. For future metadata Python use only existing .venv/bin/python; original R113 exact argv/cwd/env/output and validation order remain unchanged. Do not rerun already successful python3 metadata parse to manufacture replacement success.

5. Author can create original A20 and follow original RED→implementation→single formatting/static/GREEN sequence after ROOT reactivation. Preserve each actual command output, update inherited ledger before invocation, stop unexpected failure for Astra. No new tests/commands/technical semantics beyond R113.

## 验收与停点

本轮可新建R120激活/核对/ledger/步骤报告及六份原元数据精确副本/source-index；阶段总结允许追加真实恢复记录。保留原R113/R119计划和激活，不重读全库、不重验74无关输入、不重跑已成功解析、不安装、不改PATH、不补产品命令、不重置八预算。原单写者继续原六路径/A20，ROOT保持元数据/独审/交付分工。

任何新产品写入、预算消费、输出占用或hash冲突与原件不符时，先停并交新Astra计划；不得删除冲突或换解释器绕过。本轮通过只证明工具恢复，不提升软件、P6、native、actual或formal验收。
