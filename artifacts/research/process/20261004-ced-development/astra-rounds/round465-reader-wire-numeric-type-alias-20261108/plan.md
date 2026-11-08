# R465 Reader wire numeric types Implementation Plan

> **For agentic workers:** ROOT 使用 `superpowers:executing-plans` 逐项实施；本实际 Astra agent 只规划。本轮在 R464 任一验证启动前接管联合验证，R464 五项保持 `NOT_RUN_SUPERSEDED_BEFORE_LAUNCH`。计划完成不等于验证完成。

**Goal:** 拒绝 wire `true`、`1.0` 冒充合法冻结整数预算 `1`，并在新的六阶段 CPU 验证中共同验收 R464 顺序修复与本轮类型修复。

**Architecture:** 只把 reader 原三处完整 body/fields 的 Python 相等比较改为保留 JSON 数字类型的排序 JSON 文本比较；排序只用于内存比较。原两个 helper、独立 messages 编译、生产序列化、摘要及原件 hash 均保持。沿 R461 runner 派生新 R465 runner，R413 supervisor 不改。

**Tech Stack:** 现有 Python/json、pytest、ruff、mypy、R413 bounded_stage；无新依赖。

**Spec:** `AGENTS.md`、R461 `plan.md/plan.json`、R464 完整计划和已实施的两处字面量 diff、本轮 intake。实际规划模型 **gpt-6-astra**；基线 HEAD `fdbf481d3c843c1583d97970f8229b479363c334`，分支 `research/20261004-continuation`。用户已授权 R461 CPU 研发继续，ROOT 实施，本 agent 不运行产品。

## 事实、输入与根因

本根因来自静态源码和 Python/JSON 语义检查，**尚未执行数字类型缺口的产品失败**。`intake/static-evidence.json` 中 `{token: True} == {token: 1}`、`{token: 1.0} == {token: 1}` 只是标准库比较证据。R461 原唯一 RED 是六个预期失败；随后唯一 GREEN 为四个 nominal 失败、两个 B0 通过。那四个失败属于 R464 的序列化顺序根因，不能冒充本轮类型 RED。

`compatible_chat_generation` 对 Sol 的冻结预算要求 exact int 且范围 1..32768；`_recorded_chat_fields` 验证冻结设置，但 B0 `_verify_b0_request_body` 及 CED 字段 gate 仅用 Python dict 相等，未验证实际 wire 的数字类型。nominal 第一处全 body 比较亦有此缺口，虽然后续摘要/hash 另有保护，仍应一致地在原完整比较处拒绝。不得以已有摘要保护为由放松其他门槛。

R464 已仅调整两个 expected body 字面量为 `model, messages, **_recorded_chat_fields(settings)`；16 份保留 raw 的静态字节诊断支持该顺序。当前 reader SHA256 **79438296c48c7ff1a20d66e79725a345e3fa57973dff9fa98e9fe3b712bb68ea**，测试 SHA256 **413fed83aab5691b245463bf932c1688271c12bc8f8fc5b210bb76e3a067f67f**。R464 五阶段都未启动；后续验证由本轮承担，不在旧路径补跑。

本轮必要输入 bytes/SHA256 见 `intake/planning-input-pins.json`；旧清单按来源引用，不重复复制全部原件。已逐项核验 R464 的 102 份冻结副本及当前文件，唯一明确覆盖是上述 post-R464 reader；结果见 `intake/planning-applicability.json`。R465 初始 intake 原 reader 保留修序前字节，不能覆盖为新状态。实施前重新核验当前两文件、两个 R464 计划及所有引用输入；RED 测试源码与 GREEN 最终源码分别建立不可覆盖的屏障。

## Global Constraints

- 产品修改仅 `src/cloud_edge_robot_arm/research/freeze_evidence.py` 原三处完整比较；测试修改仅 `tests/test_sol_evidence_reader.py` 必要行为覆盖。R464 两个字面量保持，不增加 helper，不改函数签名、resolver、planner、旧 fixtures、schema 或源码清单规则。
- `json.dumps(..., sort_keys=True)` 只授权用于这三处双侧比较；R464 禁止修改实际序列化/summary/hash 的边界继续有效。不改 raw 字节、摘要实现、预期摘要来源、成本/长度/hash 连接、typed context、grounding、physical audit 或 acceptance。
- 保留 Qwen temperature/num_predict/think 的原生成语义与合法原件；完整字段比较拒绝多余键，不转 subset。合法 Sol low/4096、medium/8192、预算 1 仍按原冻结类型通过，不硬编码默认值。
- 实际 API、engine、physics、render、service、hardware dispatch 均 0，监听端口 0。保留网络/引擎拦截，仅允许现有内存 transport boundary。不能 monkeypatch reader、grounder、cost 或接受结果为 True。
- 每阶段一次且串行，任何计划外失败或范围扩大保留原件并先交下一实际 Astra；不重试、不改旧失败、不执行完整全仓套件。P1/P2/P3 未运行、native UNKNOWN、formal NOT_ACCEPTED。

## Review Focus

继续执行 R461 六个节点：完整 nominal 原件、B0 PLANNER、真实 typed SUPERVISOR 无 transport 编译、generation 漂移、两种官方身份 route、Qwen 原件及 raw/cost 拒绝。新增类型覆盖放在原 generation 节点，避免扩大测试节点或绕开完整 reader 路径。B0 的 `Mapping[str, Any]` 接口需保留；加入顶层 `MappingProxyType` 正向检查。

## Task 1：冻结唯一类型 RED

**Files:** 仅改原测试文件中的 generation 漂移节点和必要 import/测试构造；新增本轮 runner、spec、源屏障及证据文件。现有 `_nominal`、`_planner_body`、`_supervisor_body`、`_ced_case` 继续提供完整 CPU 原件。

- [ ] **Step 1 — 前置复核。** 输入/冻结副本匹配，确认 R464 两字面量 scope 正确、旧 R461/R464 验证目录不改、新 R465 stage 与 basetemp 不存在。记录精确当前 reader/test SHA、R464 `reader-order.diff` 和状态。本轮 planning 中曾尝试无版本 `python` 得 shell command-not-found；未运行脚本，改用已存在 `.venv/bin/python` 后只作标准库文件读取。这是命令路径发现，不是产品 RED。
- [ ] **Step 2 — 扩展原 generation 节点。** 在任何 nominal 构造前，创建合法 `reasoning_effort="low", max_completion_tokens=1` snapshot/settings，使用真实生产 messages 的 PLANNER body 和真实 typed context 编译的 SUPERVISOR body。按 PLANNER 后 SUPERVISOR、每 role 按 True 后 1.0 的固定顺序执行：原 int1 body 正向通过，顶层 `MappingProxyType(body)` 正向通过，然后独立副本只改 wire `max_completion_tokens`，以 `pytest.raises(ValueError, match="complete original B0")` 要求拒绝。冻结设置不改变，不能对非法 frozen True 进行测试冒充 wire 测试。
- [ ] **Step 3 — 完整路径覆盖。** 原 nominal/CED 配置循环增加 `low/1`，同时保留 low/4096、medium/8192。三个配置均须先完整 nominal available=True、B0 两角色原 body 通过、完整 CED audit 正常返回其原合成物理失败结果 `success is False`。对预算1分别加入 wire True、1.0；对4096、8192分别加入同数值 float。每种类型 mutation 均走两种 B0 角色、完整 nominal 副本及完整 CED 原件；重新计算现有测试的外围 request hash/length/summary/cost 联接，以保证拒绝来自语义 gate。nominal 错误须含 `frozen frame/prompt/settings`，CED 须在原 `actual model wire differs` gate 拒绝，B0 须含 `complete original B0`。保留已有 effort、整数预算漂移、旧字段、多余字段、缺项、无效冻结值、response_format 和 Qwen 覆盖。使用唯一 case 名，别让 True/1.0 路径键混淆。CED 原 PLANNER fixture 足够覆盖该共享字段 gate，不为本根因改其角色 schema。
- [ ] **Step 4 — 一次测试整理与 RED 源屏障。** 仅本轮新增测试可各执行一次 `.venv/bin/ruff check --select I --fix tests/test_sol_evidence_reader.py` 和 `.venv/bin/ruff format tests/test_sol_evidence_reader.py`；在 RED 前完成，保存 stdout/stderr/returncode。命令120s/outer150s，沿显式无秘密环境、无真实资源调用；若失败停止，不重复。两次是必要编辑整理，不是最终静态检查。reader 不获额外 formatter/import-fix 写入额度。建立 exclusive `implementation/red-source-ready.json` 及其固定 SHA sidecar：reader 必须仍为 post-R464 SHA，记录新测试 SHA、精确 RED 触发行、plan/spec/runner SHA 和全部运行输入。RED 后测试字节保持到全部 GREEN/static 结束。
- [ ] **Step 5 — 唯一 reader-red。** `.venv/bin/python <R465>/implementation/run_stage.py reader-red` 仅收集原 generation 节点。预期 rc1、恰一个 failed call，原因是第一个 PLANNER frozen int1/wire True 的 `pytest.raises` 得到 **DID NOT RAISE <class 'ValueError'>**；无 collection/setup/teardown 错误。保留全部原始 events/JUnit/stdout/stderr/result 和 assessment。该 RED 将在第一条别名处停下：float、SUPERVISOR、完整 nominal/CED 类型覆盖此时为 NOT_REACHED，不能声称已经执行。任何其他失败或意外通过不算本计划预期 RED，必须停止并重新规划。

## Task 2：原三处比较的最小类型修复

**Files:** 只改 reader，原错误消息、顺序构造和两个 helper 保持。JSON 已导入，无新增依赖或 helper。

- [ ] **Step 6 — 在预期 RED 通过审核后修改。** nominal 原 `body != expected_body` 改为双侧 `json.dumps(..., sort_keys=True)` 文本不等；B0 原比较左侧使用 `json.dumps(dict(body), sort_keys=True)`，右侧使用 `json.dumps(_b0_expected_request_body(body, role, observation, instruction, settings), sort_keys=True)`；CED 原排除 messages 的完整 fields comprehension 和 `_recorded_chat_fields(settings)` 也分别同样序列化比较。可为排版换行，不移动整个 auditor 或改 gate 顺序。

这种比较忽略 JSON object 键顺序，但区分 `true`、`1`、`1.0`，同时保留数组顺序、完整键集合与内容。排序结果不落盘、不作为摘要或 raw 的替代；nominal 仍用 R464 的生产插入顺序 expected body 走原 `summarize_role_request`。B0 的 `dict(body)` 只保留原顶层 Mapping 输入兼容，绝不从 actual body 派生 expected。

- [ ] **Step 7 — 冻结 GREEN 源屏障。** 对比 post-R464 reader，恰三比较处变化；测试等于 RED 屏障 SHA。保存 diff/scope review，exclusive 写 `implementation/source-ready.json` 及 SHA sidecar，绑定最终 reader/test、RED 屏障及通过的 RED assessment、所有 plan/spec/runner/输入 SHA。runner 自 RED 起保持同一字节。GREEN 之后到所有静态检查结束不得再改 reader/test 或重新采样接受新 SHA；新语义修改需要下一计划。源屏障只能读取验证，不能每阶段覆盖。

## Task 3：同一 R465 runner 的联合验证与证据

`plan.json.verification_specs` 与 `spec-templates/*.json` 定义完整 argv/env/path/nodes。入口统一 `.venv/bin/python <R465>/implementation/run_stage.py <stage>`。runner 派生自已冻结 R461 `implementation/run_stage.py`，保留 R413 supervisor、清理、原结果与事件/前置插件；只精确替换新轮次、唯一新 RED 判据、两阶段源屏障和额外资源核对。旧 R461 RED/failed GREEN 仅作历史输入，不要求其 rc0，不改结果。

| 顺序 | stage | 内容 | child / outer |
|---|---|---|---|
| 1 | reader-red | 原 generation 节点，唯一预期类型失败 | 120s / 150s |
| 2 | reader-green | 原六个精确节点，包含新增完整类型覆盖 | 180s / 210s |
| 3 | adjacent-green | 原 `test_ced_initial_freeze.py`、`test_rgbd_role_models.py`、`test_openai_sol_visual_migration.py` | 180s / 210s |
| 4 | ruff | `.venv/bin/ruff check` reader 和测试 | 120s / 150s |
| 5 | format | `.venv/bin/ruff format --check` reader 和测试 | 120s / 150s |
| 6 | mypy | `.venv/bin/mypy --follow-imports=silent` reader | 120s / 150s |

- [ ] **Step 8 — runner 和前置。** 精确校验 plan SHA、全部 spec 模板、对应固定源屏障及 SHA sidecar；RED 用 red-source-ready，之后用 source-ready。所有固定输入启动前后验证；当前运行 pins 从冻结清单读取，不把当前文件重算成新真值。新目录已存在拒绝启动；各阶段只运行一次，前阶段原结果和资源核对合格才放行。显式白名单 env，不继承 secrets；所有临时资源/cache/数据库在本轮 stage 内，新 pytest basetemp 为 `/tmp/bigsmall-r465-<stage>`。无端口；磁盘前置同时核验stage与basetemp所在文件系统。
- [ ] **Step 9 — 资源证据。** 每stage独立runner进程，child前记录 `resource.getrusage(resource.RUSAGE_CHILDREN)` 并确认没有已有child，child退出回收后记录 `ru_maxrss * 1024`（Linux KiB），上限4GiB。该口径是已等待child最大RSS，不是并发进程树合计峰值；R413已有采样单独保留，不能将稀疏采样称为精确峰值。退出后统计本stage及其basetemp内regular-file逻辑字节总和（去重，不跟随越界symlink），上限合计2GiB，记录清单/数量/时间及磁盘可用前置。报告自身计入或保守预留64KiB。写新 `resource-budget.json`，不改原 result；缺证据、超界、无法解释的资源口径均停止。这里是事后预算核对，不冒称 R413 连续强制 RSS/磁盘上限。超时只处置本runner拥有的进程，outer额外30s，不操作服务。
- [ ] **Step 10 — GREEN 五项依次运行。** reader-green须collection恰为六节点、六个call全部passed且无收集/设置/清理错误；其余须正常rc0。所有阶段须 `state=FINISHED,reaped=True,source_drift=[],remaining_live=[],errors=[],cancellations=[]` 及资源核对通过。RED仅豁免其明确预期rc1/call失败，仍须上述监督及资源条件。不运行R464任何stage，不消耗两套重复预算。
- [ ] **Step 11 — 收口交付。** 保存每步原始退出、source pins、diff、实际结果、step-report与phase-summary；把R464顺序修复列为本轮联合验收的已计划前置，R464自己仍NOT_RUN。只有六阶段实际合格、三处scope正确、六节点后半段确已执行，才能报告本轮P0软件修复完成。按明确文件路径提交推送当前研发分支，复核本地/上游/远端commit SHA；完整bulk raw/运行数据库/凭据/模型/SDK继续遵守既有交付边界。

## 验收边界与自查

软件验收要求：冻结int1的wire True和1.0在三处原门槛拒绝；合法1、4096、8192仍重建通过；B0两角色及Mapping兼容；完整nominal四原件、Qwen/route/raw/cost/typedcontext保持；CED可被正常审计但原合成物理结果仍失败。R464排序原件问题由本轮同六节点联合验证，不能只证明字典序列化比较通过。

本规划未运行pytest、产品import、API、engine、physics、render、service或产品/测试修改。验证状态全部NOT_RUN；真实fresh role、full-H及P1/P2/P3均NOT_RUN，native UNKNOWN，formal NOT_ACCEPTED。真实阶段仍须R461条件路线图及其独立冻结额度/来源，不由软件PASS替代。

自查：单一数字类型根因、三处比较、一个原测试节点内扩展、唯一明确RED、原六节点联合GREEN、三文件邻接及三静态各一次；固定测试RED→GREEN、固定最终产品GREEN→static；R464限定范围与原失败永久保留；没有来源/成本/物理门槛放宽。
