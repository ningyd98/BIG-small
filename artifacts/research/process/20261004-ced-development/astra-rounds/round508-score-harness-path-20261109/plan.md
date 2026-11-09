# R508 Score harness path Implementation Plan

> **For agentic workers:** 使用 superpowers:executing-plans 执行；用户已授权最小修复，无需再次确认。实际规划模型：gpt-6-astra。仅规划，尚未实施。

**Goal:** 修正 R506 测试 harness 导入冻结评分器时的数据路径绑定，恢复同一真实输入的旧/新评分语义比较，然后继续既有 R506 离线 score-02 流程。

**Architecture:** 仅在测试 harness 的 capture() 导入模块后，将该模块 HERE、ROOT 显式绑定至原 R505 数据根和项目根。__file__ 保持冻结副本真实路径，不修改冻结副本或评分算法；scorer_sha256 的真实来源差异单列验证，不纳入评分数值相等比较。

**Tech Stack:** 已有 Python 3、NumPy、unittest.mock 和 R506 已通过测试的环境；不安装依赖。

**Spec:** R508 inputs.json、原始 verification.stderr、R506 plan.json 与父任务的最小修复要求。

## 问题、原始证据及根因

R506 diagnostic/verification.stderr 原始 FileNotFoundError 指向 round506-screen-score-json-scalar-20261109/candidates/03-lens/run-01.json。verify_score.py:70 调用 capture(冻结副本)，冻结副本 score():28 读取 run-01 失败。该副本以 __file__.parent.parent 推导 HERE，因此数据目录错误地成为 R506；真实输入仍在 R505。此失败发生在旧结果捕获之初，尚未执行 score-02 子进程，不说明 GPU 或评分计算失败。

规划已逐项读取并核验 inputs.json 四个输入的 bytes/SHA256，全部匹配。plan.json 同时记录当前评分器与 raw-before 清单 SHA，实施前重新核验。父任务报告 R506 已55项测试通过，此处不将报告替代日志验收；本轮不重做已完成且不受影响的序列化修改。

## 限定范围及禁止事项

唯一可修改代码：R506 diagnostic/verify_score.py。

1. capture() 的 spec.loader.exec_module(module) 后、调用 module.score 前，显式设置 module.HERE = R505、module.ROOT = ROOT，对旧/新导入模块均一致绑定。不要更改 module.__file__；冻结副本的原始 import 与算法保持原样。
2. 将本次 harness 最终报告独占写入 R506 diagnostic/verification-02.json；外部执行日志独占写入 verification-02.stdout、verification-02.stderr，记录实际退出码到新的 verification-02.exitcode。原 verification.* 不覆写。
3. 在比较前可增加断言 old['scorer_sha256'] == sha(冻结旧副本)、new['scorer_sha256'] == sha(SOURCE)。现有 normalize 排除 scorer_sha256 的逻辑无需改写，禁止添加其他字段排除或容差。若调整排除位置，只能精确排除顶层 scorer_sha256，不能隐藏嵌套评分字段差异。

修改前将原 verify_score.py 精确复制为 R508 diagnostic/verify_score.before.py（独占创建），SHA 必须等于 dd9139a2b85bcee698c6152218c96bd2732f1f0ead60555b1e901f37d723dcba。允许新增 R508 diagnostic/ 核验记录和 step-report.md，以及按既有 R506 授权生成 score-02.* 并汇入 R505 phase-summary.md。

禁止修改冻结 score_candidate.before.py、R505 score_candidate.py、score_native.py、任何评分计算/数据/协议/结果；禁止复制或伪造 R506/candidates 输入来迎合错误路径。不得重跑 Lens GPU 或重生成 raw。独立 Molmo 工作不受本轮影响，但其结果不用于本轮验证。

## 前置条件

- 实施前重新核验 plan.json 全部输入 SHA；原 harness 修改后以冻结副本保留其旧 SHA，其余输入保持不变。
- 使用 R506 已验证解释器并记录其路径；依赖缺失或 import 新失败不是本轮授权范围。
- R505 的 run/protocol/oracle、raw-before 清单覆盖文件可读，冻结旧 scorer 与修复后 scorer 可导入；不修改数据路径文件内容。
- score-02.json/stdout/stderr 和 verification-02.* 均不存在；若已存在先停止并判定是否已完成，不能删改重试。现有 harness 使用 x/xb 方式写入应保持。

## Review Focus

- 导入位置与数据位置不同：旧和新模块都绑定同一真实 R505/ROOT。
- __file__ 与 scorer_sha256 仍反映各自真实代码文件，不伪造 provenance。
- 排除 provenance 不得排除任何评分字段或放宽数值比较。
- 所有输出独占新建，历史失败及旧 scorer 精确字节不变。
- 文件路径修复不得触发额外模型调用。

## Task 1 — 冻结失败与最小修正

- [ ] 核输入 SHA、保存旧 harness 精确副本；保留原 verification.stderr 作为本轮 RED。无需重跑整个失败 harness；其错误路径和冻结副本 HERE 推导可由只读导入检查直接确认。
- [ ] 在 capture() 导入后添加 module.HERE = R505 和 module.ROOT = ROOT；添加上述两条 scorer provenance 断言；仅将最终报告目标改为 verification-02.json。
- [ ] 审核 diff：只能有路径绑定、精确 provenance 断言及报告版本名；旧副本/评分器/其他输入 SHA 均未变化。以只读导入检查确认绑定值；不改 __file__。

## Task 2 — GREEN 与继承 R506 实际离线验证

- [ ] 以 R506 已验证解释器运行 `<R506>/diagnostic/verify_score.py`，独占写入 verification-02.stdout/stderr 并保存退出码。此 harness 继续原流程：捕获旧/新内存结果、精确归一化比较、运行离线 scorer 创建 score-02、严格JSON解析、50条记录核验、文件/stdout一致、真实scorer hash核验、raw和冻结输入前后核验。不得通过跳过断言取得通过。
- [ ] GREEN 必须退出0、verification-02.json status=PASS、old_new_computation_semantically_equal=true、rows=50、model_load_increment=0、generation_call_increment=0。另核 old/new scorer_sha256 各自等于其真实文件 SHA；唯一排除差异为该 provenance 字段。
- [ ] 严格JSON非有限拒绝、score-02文件独占写入继续由 R506 原实现/测试保障；本轮不改这些行为，不要求无关 GPU 测试。保留 R506 既有55项通过证据，记录本轮路径验证与真实离线核验。
- [ ] 核原 verification.*、原 score-01.*、run/protocol/oracle/raw、冻结旧scorer和当前新scorer bytes/SHA未变；记录实际输出 hashes。若受其他独立工作影响，仅核本轮明确冻结文件，不覆盖他人更改。
- [ ] 写 R508 step-report.md 并汇入阶段总结，列原始路径失败、修复范围、命令/解释器/退出码、语义和provenance核验、产物 SHA。按既有显式路径研发交付流程提交/推送并核三方 commit SHA；不提交 raw/权重/SDK。

## 验收边界和停止条件

开发通过仅说明测试 harness 正确绑定数据路径。实际通过仅说明对已有 Lens 50 次真实调用的离线评分完整、与旧计算语义一致；本轮新增 Lens 模型调用为0。正式研究、heldout、硬件、实机验收仍 NOT_PERFORMED；低分或 screening_signal=false 不能改成通过。

若输入SHA变化、旧/新评分差异超出 scorer_sha256、raw缺失、其他异常或需要改评分器，则停止受影响修复并交新实际 Astra 轮。原缺失 R506/candidates 路径是已知根因，按本计划解决无需重复立项。本计划制定本身未实施补丁、未执行GREEN或生成score-02。
