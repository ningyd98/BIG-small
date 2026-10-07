# Marker freeze 前置检查元数据修正计划 — Astra Round60

> **For agentic workers:** 使用 superpowers:executing-plans 按以下两项执行。用户限定范围优先：本轮修正编排元数据，不修改任何项目源码、不跑 suite/closure fixture、不运行 actual/model/renderer/decoder、不改 Git/Stage/DB、不联网。本次 Astra 仅写 plan.md 与 plan.json；生产 freeze 由 root 按既有授权随后执行。

**Goal:** 修正人工 precheck 对复用源集与完整冻结源集的混淆，完整保留失败，使第一次唯一生产 CLI freeze 可在精确输入不变时继续。

**Architecture:** 新建一份简单、一次性的 precheck 命令与结果元数据，比较固定完整路径→SHA 映射；继续使用原 prepare_full.py 的 freeze 与源门。失败目录保留，在其中新增 exclusive 子目录 round60，不构建新的 gate 框架。

**Tech Stack:** 现有 `.venv/bin/python`、标准库 JSON/Path/hashlib 和原 source-only prepare API；不安装依赖或修改 PATH。

**Spec:** `../round57-marker-full/plan.md/json`、`../round58-marker-preflight/plan.md/json` 与 F/implementation/round58-preflight/report.md/json。F 为 `artifacts/research/process/20261004-ced-development/astra-repair-execution/R01/marker-v4-full`。完整输入 bytes/SHA 与精确 expected 映射见本目录 plan.json。

## 失败证据与根因

1. `F/implementation/production-freeze/precheck-failure-command.py.txt` 第7行，在 `P.necessary_sources()` 后执行 `assert len(sources)==48`；原 log 为 `AssertionError`，exit1。源码静态确认 necessary_sources 返回44个复用依赖；freeze_full 随后追加4个 OWNED，完整源映射才是48。根因是人工编排比较了不同阶段的集合；没有证据要求修 prepare、改变依赖或放宽 source gate。
2. root 的 `implementation/root-fresh-process-closure/result.json` 是已完成的 source-only /tmp fixture：48源、34个公共模块 __file__/spec.origin/live/archive SHA一致，contract digest `16bfd83aa42ba257b2b3932335fdf8d1fdab423c513102a5fa9cbdee53450c99`，status PASS_FRESH_PROCESS_SOURCE_ONLY_CLOSURE。该结果与原 stdout 相符，execution exit0；不是生产 freeze。原 precheck 从未调用生产 CLI，当前 full-protocol 不存在，actual仍0。
3. 独审的普通 `python` 命令由 shell 返回 exit127：`/bin/bash: line 1: python: command not found`；Python 未启动。随后只读摘要把 report.json.tasks 的字符串值当作 dict 调 `.get`，exit1 `AttributeError: 'str' object has no attribute 'get'`。这两项是 root/独审报告的工具失败，不是产品失败或 CPU RED。原始命令与输出应保存在 `F/implementation/independent-review/tooling-failures.json`；文件若尚未完成归档，在执行T1前保留并固定SHA，禁止补造不存在的原命令。
4. Astra 规划中一条只读诊断误将 SHA 字符串与整个环境 pin 对象比较，输出29个假 mismatch；已在工具记录中保留，并改为 SHA-to-SHA 只读核验：29项全部一致。该诊断没有导入项目模块、没有失败 assertion、没有源修复，不冒充环境漂移或软件 RED。

## 范围、输入与不变量

四 owned 当前 SHA 与 round58定稿、root闭包、失败manifest完全一致；prepare_full.py保持 `6f8d7982a85a5e1cff488a5a2204fd0fe64a2c54725bebf22935de6f0f47f550`。round58当前29输入均一致（相对其原before仅3个批准源曾改变，26项保持；原四source-before仍保留）；round57原65输入均一致；48 live/archive及29环境文件SHA一致。这里29 review输入、65 full输入、29环境pins是不同集合。

允许新增 `F/implementation/production-freeze/round60/{precheck-command.py.txt,input-inventory-before.json,owned-before.json,precheck-result.json,command.json,stdout.log,stderr.log,execution.json,input-inventory-after.json,frozen-manifest.json,report.md,report.json}`，以及失败时exclusive命名的原始证据。只读摘要如有需要，直接读取原JSON字段或明确检查类型；tasks是字符串映射，禁止改报告schema以迎合摘要器。既有 production-freeze 前缀不可 mkdir()假定不存在、不可清空/覆盖/改名；仅新建其 round60 子目录，若已存在即停。项目四源、公共src/tests/assets、历史sparse/V3原件及全部既有日志只读。

root随后可由唯一现有 CLI 新建 `F/full-protocol`；不直接调用 freeze_full 创建生产目录，不复制临时fixture作生产冻结，不修改冻结后的源，不改变任何源/归档/origin/header/env严格检查。旧线程 followup 的 thread-limit 失败没有交付旧线程计划；本文件是本次独立 Astra 计划。

## Review Focus

- 集合个数正确但路径缺失/替换/额外项：必须映射全等，不能只比较44/48（T1/T2）。
- OWNED覆盖或复用源SHA漂移：要求不交、合并前SHA固定，已有源门保持（T1）。
- 历史失败前缀已存在：只新增exclusive子目录，原失败不覆盖（T1）。
- 解释器与报告字段类型误判：显式 `.venv/bin/python`，直接读字段/先辨类型，不安装、不改原schema（T1）。
- CLI意外失败或partial freeze：所有字节保留，停止到下一Astra，不重冻、不重试（T2）。

## Task 1 — 替换一次性人工 precheck 元数据

**Files:** 仅新建上述 round60 子目录中的 precheck命令、before/result/command元数据；保留独审 tooling-failures 归档。源码不变。

**Consumes:** plan.json.expected_sources（完整48路径→SHA）、expected_reusable_sources（44）、expected_owned_sources（4）、input_pins；既有 root闭包与round58最终证据。
**Produces:** 新 `precheck-result.json` 与完整 protected before清单，能证实一次生产freeze的前置条件；不产生协议、测试或actual。

- [ ] root实施前核对本计划及所有pins，确认四源仍静止、full-protocol不存在、尚无生产CLI调用、没有并行freeze/actual。若独审tooling-failures仅在对话中报告尚未落盘，先忠实保留其原命令/输出/exit并加入本轮before清单；不能伪称此前已pin。读取原report.tasks只使用其实际字符串值。后续Python命令一律`.venv/bin/python`，项目source-only检查使用`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:.`。
- [ ] exclusive创建 `F/implementation/production-freeze/round60`。新precheck命令保留旧脚本的header验证、input_inventory、necessary_sources、check_origins、require_resources调用；只移除错误阶段的计数assert，改为 `sources == expected_reusable_sources`、`owned == expected_owned_sources`、键集不交、`{**sources, **owned} == expected_sources`。expected来自本计划固定映射，不能从当前可变源重新推导基准；44/4/48只记录诊断数。此检查不调用freeze_full，也不重新运行root temp freeze或suite。
- [ ] 保存实际header环境与初始RAM/disk，要求与本计划固定环境身份一致；原source/archive/origin验证继续全部执行。protected before包括原65输入、当前29review输入与source-before、48 live源及引用archive、29环境文件、原失败三文件、root闭包证据、计划、tooling-failures（如已落盘），逐项记录bytes/SHA。原始压缩raw不在本轮重审或解压。
- [ ] 保存精确生产CLI字符串/argv与SHA、解释器、env、预计stdout/stderr路径、集合/资源结果；仅全部成立才写 PRODUCTION_FREEZE_PRECHECK_PASS。新precheck意外失败保留原命令/日志/结果，停止该切片并交下一Astra；不现场改脚本再试。本计划不新增mirror测试、不重跑131 owned、Ruff或已完成的root闭包。

## Task 2 — root首次唯一生产freeze及冻结元数据交接

**Files:** 由原CLI首次exclusive创建 `F/full-protocol/*`；新 `F/implementation/production-freeze/round60` 运行日志、after/manifest/report。禁止project source修改。

**Consumes:** T1全部通过与静止四源；round57/58既有root授权。
**Produces:** 恰好一次 CLI --prepare结果、精确冻结manifest及保全报告，供独审在真实full freeze后启动；不授予actual或研究PASS。

- [ ] 紧邻启动再次核对源/pins与full-protocol不存在。用exclusive创建stdout/stderr及command元数据，通过原命令恰好调用一次：

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. .venv/bin/python artifacts/research/process/20261004-ced-development/astra-repair-execution/R01/marker-v4-full/run_full_once.py --prepare --protocol-directory artifacts/research/process/20261004-ced-development/astra-repair-execution/R01/marker-v4-full/full-protocol
```

- [ ] 保存exit/stdout/stderr及SHA。非零退出、超时、任何源门/环境门/资源失败或不完整冻结均保存目录与原日志，标记失败并回下一Astra；不得删除目录、换名规避一次限制、修源码或重试。成功仅接受 PREPARED_SOFTWARE_ONLY，model/renderer/decoder/actual为0。
- [ ] 只读核对生产 execution-source-hashes 映射与plan.expected_sources全等，archive index键集同等且每项live/archive bytes/SHA匹配；owned四源归档为当次定稿，34公共源origin要求保持。核对header绑定的manifest/index/input SHA、65输入映射、environment29、contract及exact4807范围/资源字段；生产路径与初始资源允许区别于/tmp fixture，因此不要求生产header SHA等于临时header。原 source_preflight 已由CLI执行，不再重建或重跑temp闭包。
- [ ] 对protected before集合保存after，要求missing/changed为0，新建生产协议/本轮日志单列；原precheck失败与tooling失败字节保留。生成两任务步骤报告并交root汇入阶段总结。独立review必须在此真实freeze后才运行其既定一次owned suite/窄static，沿round57范围；它仍最多给 PASS_SCOPED_SOFTWARE_READY_FOR_ONE_FULL_ATTEMPT。本计划不执行该review suite或actual/readout。

## 实际运行前置条件与验收边界

freeze及以后actual的资源门仍为可用RAM≥6GiB、目标磁盘≥16GiB；capture≤3600s、reader≤1800s、每进程RSS≤4GiB、output≤4GiB、失败自由空间≥1GiB、frame JSON≤8MiB、journal row≤16MiB。初始资源历史值不能代替执行前重新测量。actual需真实冻结独审通过、全部source/live/archive/origin/header/env pins一致、attempt-1不存在、无并行renderer及root原授权；最多一次actual与一次新full读出，失败不自动retry。未达这些门前actual保持0。

本轮验收仅限元数据编排修正、首次freeze证据与原件保全。131 owned PASS和root source-only PASS均为已存历史软件证据；本次不重跑、不累加样本，不证明4807帧可观测、gap门、物理一致或正式研究通过。round57固定0..4806/4807、4806物理步/743命令/9动作/2dwell/120settle、SimulationS gap≤.005及相机/marker/controller/detector全部保持。formal_accepted=false、native_admission=NOT_PROMOTED、source_authenticity=UNKNOWN、continuous_visibility=NOT_ESTABLISHED、continuous_motion=NOT_CERTIFIED、independent_calibration_group=false、future_stability=UNAVAILABLE、误差/角速度界null、stability UNKNOWN；UTC队列独立不变。
