# R563 Multiscene Namespace Apply Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans；父流程内联完成R561同根范围，不新增整体审查。

**Goal:** 修正辅助补丁定位歧义，完成R561 I5已批准的命名空间和只读额度核验。

**Architecture:** 只在研究脚本的_registry_check/_reservations函数内增强既有验证；调用接口和运行预算不变。

**Tech Stack:** Python AST、现有pytest/Ruff。

**Spec:** R561 plan.json、namespace-red.log及父流程R563请求；实际planner_model=gpt-6-astra。

## 失败与前置

辅助命令全局匹配source_hashes循环并断言仅1处，实际_registry_check:320与_check_sources:1903各有1处，故退出1 AssertionError，未写源码。parent-transcript.txt明确为父工具结果转录；read-only-match-proof.json为本次只读核验。当前SHA与R562 implementation-ast.json最终目标一致，原件另存gzip；全部精确输入SHA见plan.json。

R561 namespace-red.log保留4 failed/81 deselected：未登记reservation/claim/event/group仍使all_cases_pass=true。它们是R561 I5预期RED，不是新行为根因。新增问题仅补丁工具错误使用全局唯一性假设。

### Task 1：函数限定修改并验证

**Modify:** scripts/probe_molmo_multiscene.py中_registry_check(root, registry)、_reservations(root, registry)；签名不变。_check_sources、生产、七案、阈值、模型、预算和runtime冻结。

- [ ] 实施前复核当前脚本SHA。用AST确定两个目标FunctionDef的lineno/end_lineno，或严格限定def _registry_check至def _identity区间；仅在选定函数文本内匹配并要求唯一。所有断言和候选diff成功后才写入。不得全局replace；验证_check_sources源码字节完全不变，所有其他函数AST不变。
- [ ] _registry_check增加静态登记身份一致性：schema=molmo.interface.r558.v2；groups由现有GROUPS/CAPS生成；prior={loads:4,generations:10,paid:2}；retries=0；hardware_dispatch=false；physical_formal=NOT_RUN；现有additional_max及七案验证不变。值类型与既有规范JSON一致，不能接受bool伪装数字。
- [ ] 同函数只读核验实际命名空间：claims下仅group-G1/G2/G3.json与七案case-ID-start/end.json；events下仅七案ID及_G1/_G2/_G3目录，目录内仅原连续序号json文件；root中所有G*项仅G1/G2/G3目录。非法条目、错误类型或符号链接拒绝。允许未开始组/案的文件不存在，不能初始化时要求全量已完成；原有完整性/闭合验证仍由现有validator执行。
- [ ] _reservations保留原kind/seq/identity/membership/global cap校验；增加reservations全部目录条目集合恰好等于本次已识别records路径集合，拒绝未知文件、子目录和符号链接。只读重算每组load<=1、point<=CAPS[group]、paid<=1；每案point<=登记point_cap、paid<=登记paid_cap（N为0）；load仍group scoped。只核验现有预留，不增删/回收预留，不重算实际调用为预留。
- [ ] 运行 `.../.venv/bin/python -m pytest tests/test_molmo_multiscene.py -q -k unregistered_accounting_namespace`，原4项RED转GREEN；再完整harness应85项全部PASS（若父流程继续补充，记录实际新增数量）。原回归组合和 scoped Ruff（script+tests）、git diff --check均通过。仅这两函数允许行为AST差异；R562两处保留。
- [ ] 保存限定diff、验证原输出与步骤报告并汇入R561；不改旧RED/原始证据。静态身份、每案/组额度及不存在未来文件的边界用R561现有相关测试核验，缺少覆盖时只在既有测试文件补最小定向断言，不引入新运行流程。

## 验收与边界

原app绝对解释器、worktree cwd和PYTHONPATH=<worktree>/src；修正仅辅助定位及已批准I5验证范围。任一新根因/生产变更/额度变化另交Astra。开发验收为4RED→GREEN、全部harness与原回归/静态检查；计划不宣称已经GREEN。真实与正式运行均NOT_RUN，本计划0load/0generation/0paid/0hardware，不变更累计7/30/5上限或剩余3/20/3。无第二整体审查，无待定接口。
