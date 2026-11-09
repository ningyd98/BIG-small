# R506 Screen score JSON scalar Implementation Plan

> **For agentic workers:** 使用 superpowers:executing-plans 执行本轮；用户已经授权此最小修复，无需再次批准。此文件由实际 gpt-6-astra 规划子代理生成；规划不等于实施。

**Goal:** 保留 R505 现有 50 次真实调用和失败原件，仅修复离线评分结果中的 NumPy 标量 JSON 序列化，生成新的 score-02.json。

**Architecture:** 评分计算完全保留，在 score_candidate.py 的 JSON 输出边界使用本地、严格白名单的 scalar default 回调。文件与 stdout 两条输出路径共享相同转换，保持 allow_nan=False；不修改 score_native.py。

**Tech Stack:** 现有 Python 3 / NumPy / stdlib json；使用现有已可导入评分器依赖的运行环境，不安装依赖。

**Spec:** request.md 与 failure-inputs.json；上轮 R505 plan.md/plan.json 的冻结评分规则继续生效。

## 原始问题、证据和根因

R505 candidates/03-lens/run-01.json 的 status 为 ALL_50_REQUESTS_COMPLETED，model_loads_started=1、generation_calls_started=50、completed 长度=50。此为已读取的运行清单事实，不能代替逐项 raw 核验。

score-01.stderr 的原始 traceback 在 score_candidate.py:161 json.dump(...allow_nan=False) 报 TypeError: Object of type bool is not JSON serializable。score-01.json 为 3174 字节的不完整原件，截断在 rows[0].modes.box.valid_depth 的冒号之后；不得修补、删除或覆写。

源代码支持的根因：score_native.pixel_assessment 的 valid_depth 表达式最后一项 depth[index] > 0 对 NumPy float32 产生 numpy.bool_，Python and 返回该最后操作数，导致其进入嵌套 result。日志中的类名 bool 与 NumPy 2.x 标量命名相符；实现阶段须以实际类型与 RED 回归确认，不能仅凭文本推断全部标量路径。计数/其他浮点结果也可能携带 np.integer/np.floating，同属输出标量类型根因，允许在同一白名单中处理。

本规划逐项核验 failure-inputs.json 的全部 10 项 bytes/SHA256，均匹配；完整清单嵌入 plan.json。规划命令裸 python 不存在，已用 python3 完成只读核验；这只是执行前置条件，不授权修改环境。

## 全局限制与限定文件

唯一允许修改的运行代码：R505 implementation/score_candidate.py。仅增加本地 JSON 标量回调、给两条 JSON 输出接入该回调及严格非有限拒绝、将独占创建输出改为 score-02.json。不得修改 score()/stats() 的计算、返回结构、判断、分母、阈值、点映射、模型输出解析、记录顺序或任何 shared/common helper。

允许新增 R506 tests/test_score_json_scalars.py、diagnostic/ 下只读核验/RED/GREEN/语义比较证据及 step-report.md；允许新建 R505 candidates/03-lens/score-02.json、score-02.stdout、score-02.stderr 与运行退出码证据；允许更新 R505 phase-summary.md 记录本次修复及离线结果。保留修改前评分器精确字节副本于 R506 diagnostic/score_candidate.before.py，SHA 必须等于输入清单。此副本为证据，不作为新评分实现。

score-01.*、run-01.json、protocol.json、oracle-inputs.json、所有 raw/模型/SDK/公共与冻结 schema 均不可改。不得重跑 GPU、加载模型、重新生成 mask 或触发硬件。原数据分母为12正例+4缺目标，重复调用不变成独立样本。新评分器 SHA 改变属于真实 provenance 变化，须如实记录，不能伪造旧 SHA。

## 实际运行前置条件

实施前重新逐项核输入 hashes；评分器修改后比较 frozen 副本而非要求新评分器仍为旧 hash。所有其他输入全程保持原 hash。查看 git diff，避免覆盖他人修改。

指定 Python 解释器须已能导入 numpy、pytest 和评分器依赖（VisualDecision/pydantic），记录绝对路径及版本；可使用现有 R505 合适环境，不假定 python 命令存在，不安装或升级。

真实离线评分前确认 run-01 的50条 completed、协议绑定、raw-response hashes/output token counts、raw-mask-logits 文件及 oracle 关联数组均存在，现有 scorer 的全部断言继续执行。记录所读 mask/log/数组 raw 文件的 bytes/SHA256 快照并在后续核对未变；无法读取或断言失败不得重建原件。

score-02.json 及本次 stdout/stderr 必须不存在；独占创建，已存在则停止以免覆盖，先辨认是否是本轮已完成输出。禁止启动 runner/GPU 命令。离线 scorer 可读取既有 GPU 资源日志，但不产生新 GPU 测量。

## Review Focus

- np.bool_ 必须成为 JSON true/false，不能成为整数或字符串。
- NumPy 有符号/无符号整数及浮点标量保持值与 JSON 类型，不作舍入或字符串替代。
- Python/NumPy NaN 和正负 Infinity 均拒绝，文件与 stdout 均保持严格 JSON。
- ndarray、complex、自定义对象不得被宽泛 tolist/str/item 接受。
- 重跑不能覆盖失败原件或新结果；真实分数与基线仅容许类型归一化及 scorer_sha256 变化。

## Task 1 — RED 回归、最小修复、GREEN

**Files:** 修改 R505 implementation/score_candidate.py；新增 R506 tests/test_score_json_scalars.py 与 diagnostic/ 测试证据。

**Interfaces:** 新增本地 `_json_scalar(value)`，只将 np.bool_ → bool、np.integer → int、np.floating → float；其余类型抛 TypeError。不在此处修补非有限值，由 json 的 allow_nan=False 拒绝。两处 json.dump/json.dumps 都传 default=_json_scalar，均显式 allow_nan=False。输出文件为固定 score-02.json，保留 open("x")。

- [ ] 保存旧 scorer 精确副本并核 SHA，新增测试。测试经现有实际 JSON 输出路径运行：用合成嵌套评分结果覆盖 bool true/false、np.int32/int64/uint64（包括 >2**53 的可表示整数）、np.float32/float64 与原生标量；反序列化后核 type 与确切值；无舍入，float32 对照 float(original)。测试须能证明输出路径实际接入转换，不能只测回调。
- [ ] 在尚未修复的实际输出路径重现 numpy.bool_ TypeError，保留命令/stdout/stderr/退出码为 RED。可在测试中拦截 json.dump/json.dumps 记录其真实 kwargs，或在隔离临时目录运行输出；不得向现有 score-01 原件写入。RED 的预期标量 TypeError 属本计划授权，无需新轮；导入/依赖或其他根因失败不算预期 RED。
- [ ] 增加非有限拒绝测试：Python float 与 np.float32/np.float64 的 NaN、+Inf、-Inf，在文件与 stdout 序列化均报 ValueError；未知 object/ndarray/complex 均 TypeError；输出目标已存在时 FileExistsError 且字节未变。保留正常 nested list/dict/tuple 的原有 JSON 语义。
- [ ] 仅实现以上回调及两个输出调用、score-02 文件名。不得给整个结果 indiscriminate str/item/tolist，不能 catch TypeError 后跳过字段。
- [ ] 用已验证解释器执行 `-m pytest <R506>/tests/test_score_json_scalars.py -q`，GREEN 全通过；随后执行现有 R505 tests，保存原始日志与退出码。新失败暂停相关修复并交新 Astra 轮，不趁机扩大范围。

## Task 2 — 已有真实数据的离线重评分与语义核验

- [ ] 在测试 harness 中以冻结旧 scorer 计算同一实际 run 的内存 result：仅在测试侧拦截输出，重定向输出文件到临时目录，捕获 result 后停止序列化。不得改旧副本计算逻辑，不能重新运行模型。旧/new 计算结果逐路径比较，允许 NumPy scalar 对 native scalar 的精确值等价；除 scorer_sha256 必须反映对应源码外，键/值/顺序/行数/指标/协议和run/oracle哈希全部相等。可用独立测试侧显式标量归一化辅助比较，但必须先核每个转换值类型/值，禁止用生产回调同时生成 expected 与 actual。
- [ ] 记录前置核验后，以已验证解释器运行 `<R505>/implementation/score_candidate.py 03-lens`，stdout/stderr 分别独占写入 score-02.stdout/score-02.stderr，记录退出码；本轮模型加载/生成调用增量必须为0。
- [ ] 严格解析 score-02.json 与 stdout（拒绝 NaN/Infinity），文件 rows=50、completed_calls=50，摘要与去 rows 的文件内容相等；run/protocol/oracle hashes 不变，scorer_sha256 等于修改后文件 hash，hardware_dispatch=false，acceptance 仍 DEVELOPMENT_SCREEN_ONLY_NOT_HELDOUT_OR_PHYSICAL_ACCEPTANCE。不把 screening_signal 的真假作为修复通过条件。
- [ ] 对比全部 frozen 输入和 raw 前后 hashes，特别是原3174字节 score-01.json 与 stderr 完全未变。记录实际指标，不改低分，不补缺失预测。
- [ ] 生成 R506 step-report.md，汇入 R505 phase-summary.md：分别列开发测试、已有真实GPU证据的离线重评分、未进行的正式/实机验收，列原失败路径、输入与产物 hashes、命令/解释器/退出码和剩余限制。
- [ ] 按项目现有独立研发分支与显式路径流程提交/推送已验证交付，并核本地/上游/远端 SHA；不提交大raw、数据库、SDK、权重或凭据，不把派生清单称完整远端复现包。

## 验收与停止边界

开发验收：RED 正是 NumPy bool 序列化错误；GREEN覆盖类型/值、非有限拒绝、未知类型拒绝和防覆盖；已有合约测试通过。真实运行验收：仅完成现有50条GPU记录的离线评分，严格JSON完整且与旧计算语义一致，新增GPU calls=0。正式研究、heldout、3D、控制器和实机验收均 NOT_PERFORMED。

若出现输入 SHA 变化、raw 缺失、评分语义差异、新异常类型或需修改共享 helper/冻结协议/模型输出，暂停该修复并调用新实际 Astra；不能以此计划为扩大范围授权。计划本身尚未执行 RED/GREEN 或真实重评分，也不宣称候选通过筛选。
