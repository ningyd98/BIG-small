# R564 Archived Multiscene Verification Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans；父流程内联TDD，这是新失败修复计划，不是第二次整体审查。

**Goal:** 新增独立只读离线工具，按封存调用时间验证历史tracker拒绝，使汇总不依赖核验当天的墙钟。

**Architecture:** 保留75f5a991fe16549843177a1fa79c76cf1914e741全部登记源码和raw。新工具调用原case/group/summarize验证器；唯一差异为离线tracker拒绝回放显式使用该原调用的开始/结束时间包络，仍执行原绑定与几何门。结果写全新派生目录。

**Tech Stack:** Python、原OpenCVTargetTracker与_binding_reason_at、现有pytest/Ruff。

**Spec:** 本轮request.json（47输入全部复核）、readonly-case-comparison.json、readonly-findings.json、readonly-inputs.json。实际planner_model=gpt-6-astra；规划0真实调用。

## 已证实问题与保留事实

原summarize CLI exit2；summary.local.json valid_suite=false、可信suite 0/7。七份运行时行级分类是P01/P02通过、N02/N04预期拒绝通过、N01/N03 ERROR_POINT_OR_BINDING、P03 FAIL_INTERFACE。这三层不能合并或覆盖。

逐案原码重算唯一差异为N02：verdict/passed/evidence_ok/evidence_errors/refusal_source五字段变化。G2/G3及其余六案逐字段相同；不是数组顺序或浮点序列化差异。_visual_source重新构造OpenCVTargetTracker，其_binding_reason读取当前墙钟，先报capture_time_not_fresh，遮住原color_identity_ambiguous。用同一原构造器、仅绑定检查显式调用原_binding_reason_at，分别在封存stage开始/结束（观测年龄1.922080s/1.960417s）均复现原颜色歧义。原内部精确读钟未记录，因此只能证明整个已记录包络有效，不冒称知道精确读钟值。

N01/N03为相同raw SHA、非token上限、无规范点标签、严格parser INVALID；人可解释的不存在自然语句不是ABSENT协议成功。保持两案失败，本轮不改提示/parser/白名单。P03原生与几何点均(193,90)，高色度直接保留；原3×3深度world-z跨度0.07000005245m，超过原0.008m门，原resolve_top_grasp拒绝被CPU重现。RGB点位处于彩色轮廓上缘、原深度混合支撑面附近与高处，支持边界混采假设；不以此宣称已证实物体真实表面身份或提出已验证的新选点规则。该案保持FAIL_INTERFACE，后续研究另立计划。

## 精确修改范围与接口

仅新增 `scripts/verify_molmo_multiscene_archive.py`、`tests/test_molmo_multiscene_archive.py` 和本轮研究证据/步骤报告。所有既有登记源码（含原harness/tests/guide/生产）、registry、七案结果、summary.local.json、manifest、原图/深度/native/cloud/合同原件冻结。不能更新原source_hashes来适配新工具，不能调用原CLI main覆盖summary。

新接口固定：

- `verify_archive(raw_root: Path) -> dict[str, Any]`：只读验证与派生返回，不创建provider/session/ledger，不调用pipeline.process、run_group或任何模型/HTTP。
- `_historical_tracker_refusal_scope(harness, raw_root, registry)`：同步上下文管理器，包裹原harness._visual_source。在其原参数opened/ended中只针对恰好一个符合原精确白名单的tracker失败，建立本次局部回放类并调用原_visual_source。其他路径原样调用，不改变分类规则。
- `main(argv=None) -> int`：仅`--raw-root`、`--output-new`；输出必须原根之外且不存在，独占创建。证据有效返回0，证据不完整/矛盾返回2；0仅指派生证据验证成功，不代表all_cases_pass。

回放类继承原OpenCVTargetTracker，__init__核验本次观测checksum与原stage grounding规范JSON精确相同，再原样调用super().__init__。唯一覆盖_binding_reason：分别调用原基类_binding_reason_at(self, observation, start.utc/end.utc)，任一返回拒绝即fail closed。原5s/50ms门、标定/session/相机字段与几何原实现完全不变；不覆盖datetime.now，不改观测时间/深度，不忽略绑定检查。开始/结束须同op/parent/case/frame/context、带时区、UTC和monotonic有序；原event/manifest核验先行。两端均有效才执行原几何判断，且最终异常完整消息必须仍与封存白名单拒绝一致。

原_visual_source在函数内import tracker，因此仅在该函数调用期间临时绑定tracking.OpenCVTargetTracker到局部回放类，finally恢复原类；外层harness._visual_source也finally恢复。此独立单线程进程不能暴露worker命令或执行在线工作；不在原生产进程应用patch。禁止用异常文本匹配直接返回成功，禁止跳过原构造器/manifest/原source验证。缺stage、多个候选、时间无效或原错误不复现均保留失败。

## 身份、输出与历史边界

先检查request冻结harness SHA b27df4b4dfc4015e940ca807e6f1e72b56f3058a7b70d4f7268baa8e8df3a262；原_registry_check继续逐一验证原registry.source_hashes，原根路径不搬迁。所有旧source仍须真实匹配；未来不匹配则明确无法回放，不自动替换或绕过。新工具和测试SHA、解释器/相关包版本、原commit、registry/原summary/manifest SHA与补充只读输入清单，作为新的derived_verifier身份独立记录，不声称新工具是当时运行源码。

从原磁盘读取stored rows，调用原summarize并限定上述回放上下文；不编辑rows或重写verdict以通过原stored==recomputed比较。派生报告同时列出：历史strict summary（0/7及SHA）、原运行时七行分类、derived archive verification（来源/模式/每案比较/证据错误）。若所有验证成功，预期valid_suite=true但all_cases_pass=false，阳性2/3、阴性2/4、合计4/7；这是可复核假设，必须实施后真实离线验证，不是本计划已取得的结果。

独立输出建议 `datasets/model-cache/molmo-multiscene-r564-offline-verification-20261111/`。完整原件仍local ignored，不复制原图/depth/native文字/token/cloud正文或合同至公开报告。公开仅代码、SHA/计数/状态/必要几何统计和派生报告。前后复核原raw清单与注册源码SHA，不修改旧manifest自证成功。

### Task 1：CPU RED再最小实现

- [ ] 新测试利用原完整CPU磁盘fixture（只import，不编辑旧测试）构造封存tracker颜色歧义；将回放墙钟移至采集后超过5s，证明原验证失败而新工具尚未实现。保留原真实N02差异诊断。
- [ ] 测同一封存数据在两个不同未来墙钟下得到相同派生核验；两端有效重现原拒绝，非白名单/未知错误仍失败。精准覆盖5s和-50ms包含边界、任一端越界、缺时区/倒序/错op/context、原件缺失/篡改、source/registry漂移。断言patch在成功和异常后恢复，原在线构造器仍拒绝过期帧；禁止provider/HTTP/pipeline调用与原根写入。
- [ ] 仅按上述接口实现新文件。运行新测试及原harness完整CPU回归、两新文件Ruff和git diff --check。原旧tracker重算失败是保留基线，不修改旧测试来掩盖。复用原回归已知无关失败说明，不修无关范围。

### Task 2：原七案只读派生验收与交付

- [ ] 确认47输入及补充SHA适用、原source/422 raw清单未变；用原app绝对Python、worktree cwd与src PYTHONPATH运行新CLI至独占新目录。保持原raw根所有文件size/SHA/mtime；仅新目录允许输出。
- [ ] 逐字段原7行==重算7行，三组计数3load/17generation/2paid对账不变；预期只修复证据可重复验证，不改变三个接口失败。所有证据门通过才记录派生4/7，否则保留新失败并另立计划；不得强行重分类。
- [ ] 保存步骤报告，明确原strict失败、运行时四行通过、派生核验三层。按用户Git规则提交推送仅新文件和安全派生材料，核对三端SHA；不新增整体审查。

## 运行前置与验收边界

本轮只实施离线软件修复；现有ABI/runtime和原资产不动，无需GPU/网络/模型。规划与实施均0新增load/generation/paid/hardware。累计实际7/27/4，loads额度已耗尽；账面剩余3generation/1paid不构成新的加载或重试授权。②③后续候选需要另轮实际Astra，任何新真实运行先独立预算。开发GREEN不替代真实七案或正式研究验收；本轮不改善或宣称改善模型缺失表达和P03选点。

发布边界：readonly-inputs.json完整底层读取清单仅本地保留；公开plan.json只保留其自身SHA/条目数、47项指定问题输入及少量诊断来源，不发布完整raw路径清单。原清单不修改或删除。
