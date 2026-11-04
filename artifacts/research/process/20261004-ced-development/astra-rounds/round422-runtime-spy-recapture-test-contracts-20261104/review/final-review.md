# R422 / R423 一次联合 fresh 最终审查

审查者：实际 gpt-6-astra，独立 Senior Code Reviewer，非本轮实现者。
BASE = HEAD = `f63e271f56a361b43d84be5538f73efe6afce226`；对象为未提交工作区精确差异。审查时间：2026-11-04T03:42:07.149329+00:00

## Strengths

- `tests/test_visual_worker_execution.py:24; src/cloud_edge_robot_arm/vision/evaluation.py:70`：只有SOFTWARE_ONLY注释和_local_mode=False；生产严格type认证保持，原fake-owner两个参数节点仍拒绝。监督模块直接复用episode，未复制或赋予替身owner资格。
- `tests/test_visual_worker_test_contracts.py:17; src/cloud_edge_robot_arm/vision/execution.py:693`：真实recapture/check_active重装runtime持有预算后拒绝过期deadline，断言无claim/capture/completion；另一个真实消费者测试用local时间陷阱及budget_payload/capture顺序，避免只验证flag常量。
- `tests/test_rgbd_closed_loop.py:392; tests/test_visual_worker_test_contracts.py:47; src/cloud_edge_robot_arm/vision/execution.py:1372`：只接受completion关键字，未知关键字仍TypeError；原-4.0速度/1.5上限和真实shield不变。新增执行测试确认None转发、唯一dispatch、SKILL_RETURN后真实SAFETY_POSTCHECK REJECT。
- `tests/test_visual_worker_supervision_execution.py:295; tests/test_legacy_reference_mode_compatibility.py:10`：精确GREEN覆盖真实Memory/SQLite仓库、取消后拒绝、未知action、默认模式、伪造观测、UTC租约撤销及未知mode；这些均限定为软件证据。
- `R422/validation-summary.json; R422/final-integrity.json`：原22节点19完整函数AST（含装饰器和参数化）保留；各原节点可映射R413原longrepr、此次RED与GREEN。72stage原始事件、JUnit、spec/pins、退出及清理记录一致，未用跳过/xfail/重复节点换绿。
- `R423/local-preservation-manifest.json; R423/step-report.md:7`：16份create-only副本与16原树的持久化before/copy/after可核对，459文件/17,266,800 bytes及16条symlink保持；56项明确ABSENT_OBSERVED并无target。报告保留local-only及非自包含边界。

## Critical / Important / Minor

- Critical：无。
- Important：无。
- Minor：无需要作为本轮修改项提出的问题。

没有发现阻塞本次选择性研发分支交付的缺陷。该结论只覆盖实际读过的改动、相关消费者和已保存证据。

## 证据核对与限制

审查开始和写报告前两次核对23个冻结输入的bytes/SHA256；另核对40项不变R422规划输入、11项R423规划输入。读取实际HEAD版本并机械确认旧文件只有两处获批修改。1310基线源中只有两旧测试改变，其余1308及全部406个src字节匹配；新增代码只有新contract测试文件。原22节点对应19个完整函数AST（包括参数化装饰器）匹配，原业务输入和期待不变。

独立读取R413原事件并逐项对应22个原longrepr；核对计划与target-manifest的72个精确job，以及每stage的spec、source pins、STARTED、三阶段事件、JUnit、raw-exit、precleanup退出、terminal和invocation。504个已保存关键证据文件bytes/SHA全部匹配。保存结果为25 RED（23缺mode、2completion关键字；setup/teardown通过）和47唯一GREEN（37pure、10真实软件repo/owner；141阶段PASS），无JUnit failure/error/skip。每stage仅一个STARTED；72个stage自然FINISHED/reaped，无signals/errors/source_drift/owned残留。原22均在GREEN内，未额外重复。上述是对既有运行证据的审计，本审查没有重跑pytest或产品。

读取现存静态检查记录：两旧文件diff-check、新文件Ruff及format均为退出0；未重新运行静态工具。读取实际消费者后，能确认新测试走真实check_active/recapture/budget_payload/execute；安全盾未替换，超速拒绝不是靠捕获签名错误。真实软件仓库测试使用Memory/SQLite和VisualWorkerRuntime，不能将native标签解释为实体。

R423只读重算16个原目录与副本：459普通文件、17,266,800 bytes、16个符号链接，当前lstat身份、类型、文件SHA及链接原文本与持久化before/copy/after一致；没有跟随symlink读取目标。56项source与target目前均不存在，且记录copy_attempted=false。11输入pins仍匹配。

**归档历史证据局限：** 72个validation整树的before/after摘要只在当时行政命令内存中比较，manifest持久化的是比较通过计数；没有独立可重算的逐树历史before清单。执行者说明原命令chunk8dc984中逐树assert通过，exit0/0.332秒；该说明与现存终态相容，但不是独立持久化逐树证明。审查已独立核对早于R423冻结的504关键stage文件和16原树/副本完整清单。此局限不阻塞两helper修复的选择性交付，也不允许声称全raw历史可独立重建或完整远端复现。

初次只读命令的`python`别名不存在，另一次rg包含一个不存在的猜测helper路径；均未运行测试或修改输入，随后使用项目绝对解释器及实际导入路径继续读取。未执行SQL、网络或Git写入，未进入两个dirty gitlink；唯一写入为本报告与同名JSON。

## Declined_to_judge（每项须由root裁定）

- **D1 全4751/full5580、P0重新验证及其它历史失败是否已解决**：本轮授权为25 RED + 47 GREEN精确节点零重试；未运行全suite或P0，不能从本轮PASS减算历史35FAIL/1INCOMPLETE。
- **D2 真实模型、相机、机器人、控制器与正式研究验收**：本次仅软件替身契约及真实软件仓库/owner路径，未调用实体或外部模型；不改变已有实体gate。
- **D3 local temporal owner全部权限、非None effect completion及跨进程/并发租约整体正确性**：本次生产源码不变；检查的是False选择的durable分支、None回调和限定反例。没有新的此类运行证据，后续租约根因仍须独立Astra计划。
- **D4 API返回时进程内FD零泄漏及长期性能/稳定性**：保存证据证明stage自然退出、owned回收及无信号；不能推出API返回时资源审计或持续运行性质。
- **D5 R423复制前后72个validation整树的独立历史逐字复算**：整树before摘要只存在于当时行政命令内存，现存清单只持久化72项比较通过结论。独立复核已覆盖早于R423冻结的504个关键stage文件及16树before/copy/after；其余全树历史依据执行者当时assert与exit0记录，不冒充独立持久化证明。
- **D6 56个basetemp在完整历史上从未创建、以及副本自包含可移植性**：仅能确认目前ABSENT_OBSERVED与无target；16条绝对symlink保持原文本且仍可能依赖源路径。
- **D7 最终Git选择清单、提交推送完成与三端SHA一致，main合并批准**：审查时尚未提交，HEAD仍为f63e271f56a361b43d84be5538f73efe6afce226，index无已暂存差异；由root后续按精确allowlist执行并核对，审查不执行网络或Git写入。

## Recommendations

root逐项裁定D1–D7并保留对应边界。提交只使用R422 plan.json中的3个代码路径、固定文档和每stage七项精确路径，另加R423 plan.md、plan.json、intake/observation.json、step-report.md。完整stdout/stderr、DB/raw、副本、local-preservation-manifest与本地Git事务回执不选入；不要为复现包表述扩大交付范围或重写冻结原件。

## Assessment

**本次选择性研发分支交付：无阻塞，可进入root的精确暂存/普通提交/推送与local、upstream、exactremote三SHA核对。**

实际改动符合两轮计划，保存证据足以支持有限软件测试和归档事实，且报告未把47PASS提升为全suite或实体验收。最终提交/推送尚未执行，本审查不批准main合并，不宣称正式研究或实体通过。
