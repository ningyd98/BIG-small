# Marker full preflight 修复计划 — Astra Round58

> **For agentic workers:** 使用 superpowers:executing-plans，按三项任务执行。本派单仅制定计划；不实现、不测试、不创建真实 freeze、不运行 actual、不调用 detector、不修改 Stage/Git/DB。根执行者沿既有授权实施；本轮预定 RED 以外的新根因、范围扩大或计划外失败须先进入下一 Astra 轮。

**Goal:** 在真实冻结前修复四处静态问题及有直接 producer/consumer 证据的两个 END 格式桥接问题及 exact9 teacher journal 漏门，使后续独审能评估固定协议的软件准备状态。

**Architecture:** 只改新 full artifact 的 runner、reader 和 CPU fixtures；保持旧 V3、旧 sparse 和公共源码字节不变。用固定协议显式适配旧 V3 END，并令新 recorder 的返回值与其实际 END 原件完全一致，保留 reader 的严格全字段比较，并补齐声明的 exact9 teacher/18 action 边界。

**Tech Stack:** 既有 Python 3.12、pytest、Ruff、JSON/gzip；不增加或升级依赖。

**Spec:** `../round57-marker-full/plan.md` 与 `plan.json` 是原 full 合同；本计划仅补充 preflight 修复。所有直接输入的 bytes/SHA256 见本目录 `plan.json.input_pins`。令 `F=artifacts/research/process/20261004-ced-development/astra-repair-execution/R01/marker-v4-full`。

## 事实与原始证据

- `F/implementation/ruff-initial.log` 是已观察失败：共 8 条、工具自动修过 4 条、剩余 4 条。run_full_once.py:95 E501；test_cpu.py:188 E731；verify_full.py:1161 B905；verify_full.py:1246 E501。原日志、format.log 与先前 RED 均保留；不得重写为新的通过输出。
- `owned-green.log` 记录格式化前 91 passed in 9.05s；`owned-first-green.log` 为更早 85 passed in 8.15s。它们不证明当前 paused 字节通过，更不证明完整 reader、actual 或研究验收通过。
- V3 producer `src/cloud_edge_robot_arm/research/step_rgbd.py:167–187` 保存/返回 END，字段为 `observation_checksum_sha256`、`observation_json_sha256`；本轮只读现存旧 index 的前两行也确认了这些字段。旧 full `offline-markers.jsonl` 第一行有 `checksum`，没有 `original_sha256`。新 `baseline_markers():868` 却取 `saved["checksum"]`：静态确定存在字段不兼容，预期 fixture 会触发 KeyError；尚未运行 baseline reader，不得称已观察 actual 失败。
- 新 `FullRGBDRecorder.record_step():153–168` 的 row 无 event；`emit("END", **row)` 在原件中添加 event；方法返回无 event 的 row。旧 V3 `AcquisitionCoordinator.record():373–380` 将该返回值原样保存为 `ACQUISITION_END.saved`。新 reader `validate_full_trace():436` 与含 event 的 index END 作严格全字段比较，因此合法 producer 记录会被拒绝。该不兼容由源码确定，尚无运行失败输出。
- root 后续提交的 exact9 finding 已静态复核：verify_full.py:505–511 仅要求 TEACHER_ACTION ordinal 为不重复 int，未限1..9；旧 helper.verify_original_recipe():542–580 只检查 summary 的9 begins/ends并遍历1..9，不拒绝 teacher_actions 的额外10。ACTION_BEGIN/END 分支已拒绝超出1..9，但终态尚无精确18键集断言。额外 teacher ordinal10 可绕过当前合同；这是静态遗漏，待 CPU 反例证实，不是 actual 失败。
- 当前 `F/full-protocol` 不存在，paused manifest 声明 actual/model/detector/真实 freeze 均为 0；本次计划只核对目录与静态输入，不运行项目代码。计划状态仅 `PLAN_ONLY`。

## 限定范围与不变量

允许源码修改仅 `F/run_full_once.py`、`F/verify_full.py`、`F/test_cpu.py`；四源总白名单包含 `F/prepare_full.py`，但本轮对其**只读，不需要改动**。允许实施后在 `F/implementation/round58-preflight/` 新建 source-before、日志、结果与步骤报告。修改前逐项复核本计划 pin，复制四源原字节并记录 SHA；源或输入漂移先停止，不覆盖 paused manifest。

保持 round57 exact 0..4806 / 4807 分母、743 commands、120 settle、9 actions、2 dwells、相同相机/marker/guard/detector/recipe/resource/time 合同；旧 full 4618 OBSERVED / 189 UNKNOWN 和旧 sparse 201 OBSERVED / 0 UNKNOWN 各自保留。旧 201 与旧 full 均只使用已有读出，禁止再次 detector/decode、批量 raw 解压或模型预演。

`formal_accepted=false`、`native_admission=NOT_PROMOTED`、`source_authenticity=UNKNOWN`、`independent_calibration_group=false`、`continuous_motion=NOT_CERTIFIED`、`continuous_visibility=NOT_ESTABLISHED`、`future_stability=UNAVAILABLE`，误差/角速度界 null，stability UNKNOWN。软件检查不替代真实运行或正式研究证据。

## Review Focus

1. exact9 teacher 与18 action边界不能容纳额外ordinal10、缺项或bool；原recipe helper不得用summary计数替代 journal精确键集（T2）。旧 V3 END 合法长字段必须接受；缺字段、sparse 短字段、错误 protocol、identity/checksum/manifest 不一致必须拒绝（T2）。
2. 新 recorder 返回值、实际 index END、coordinator.saved 必须完全一致；不能通过 reader 忽略字段或只比较交集变绿（T2）。
3. 相邻时间差 n 与 n−1 的有意长度差不能误设 strict=True；真实 old/new 序列仍由 zip_longest/exact denominator 防截断（T1/T3）。
4. source/live/archive/origin 闭包必须在独立进程中成立；已有同名错误 origin 负例保持；规划的源码阅读不冒充运行 preflight（T3）。
5. range/final guard/streaming/raw 拒绝行为保持；唯一真实 freeze 在最终字节和 owned 检查定稿后、独审前（T3）。

## Task 1 — 四处语义等价静态修复

**Files:** 修改 `F/run_full_once.py:95`、`F/test_cpu.py:188`、`F/verify_full.py:1161,1246`。接口与输出字节合同不变。

- [ ] 保存 source-before 四文件和计划/原日志 pins，确认无真实 full freeze、无执行中的 actual。
- [ ] 将过长注释分行；将测试 `provider` lambda 改为同分支无参数 def，返回同一 dict；将报告字符串拆成相邻字面量，拼接结果和换行保持完全相同。
- [ ] 对 `zip(observed_times, observed_times[1:])` 明确设 `strict=False`。这是同一列表的相邻时间配对，n≥1 时长度天然相差一；strict=True 会错误拒绝健康读出。不要改 old/new 的 `zip_longest`，不要删除其 exact ID/count 门。空/单元素仍返回 None，多个元素仍取全部相邻差最大值。
- [ ] 不运行全仓 lint 或自动 unsafe fixes；与 T2 合并定稿后在 T3 一次执行四源 static。原四条已是本 task 的失败证据，毋须为注释/换行新增镜像测试。

## Task 2 — 固定协议 END/recipe 合同与真实格式 CPU RED→GREEN

**Files:** 修改 `F/verify_full.py` 的 baseline、ACQUISITION_END、TEACHER_ACTION/terminal recipe 接口附近、`F/run_full_once.py` 的 record_step 成功返回值、`F/test_cpu.py`。公共与历史 producer/reader 均只读。

**Interfaces:** 若抽取 exact recipe 合同，使用 `validate_recipe_event_inventory(actions: dict, teacher_actions: dict) -> None` 并由 validate_full_trace 的终态路径实际调用；精确要求 actions 键为 `{(i, e) for i in range(1, 10) for e in ("ACTION_BEGIN", "ACTION_END")}`、teacher_actions 键为1..9，均须原生 int 非bool，值中ordinal须与键一致。新增纯函数 `adapt_old_v3_end(row: dict, *, protocol: str) -> dict`，只接受 `research.custom-whole-step-guarded-rgbd.v3` 且 event END。返回新 dict（原输入不变），保留原字段，显式增加 `checksum=row["observation_checksum_sha256"]`、`original_sha256=row["observation_json_sha256"]`；拒绝缺失/无效 SHA256、错误协议、仅 sparse 短字段或混入冲突短字段。`baseline_markers()` 从旧冻结 header 取 protocol 后调用该 adapter。`FullRGBDRecorder.record_step(...) -> dict` 返回成功写出的完整 END record。

- [ ] 在 test_cpu 写两个 fixture 族：`test_old_v3_end_schema_adapter` 使用本轮读取的真实旧 END 键形状与 full readout 键形状的小数据，断言合法长字段映射、原 dict 不变、readout checksum/identity 与 index/manifest 绑定；缺长字段、sparse-only、错协议、错误 event、conflicting alias、checksum/identity/manifest 不一致拒绝。旧 full readout 无 original_sha256，不能凭空要求它提供；该 SHA 只来自已固定旧 index，不在本轮再次解压来声称重新验证它。
- [ ] 增加 `test_full_recorder_coordinator_end_record_identity`：用真实 FullRGBDRecorder + tiny capture + 原 V3 AcquisitionCoordinator（fake backend/journal/tracker，无 runtime）完成单步。检查方法返回 END、实际 JSONL END、coordinator 捕获的 saved 三者完全相同，包括 event/schema/checksum/所有 metadata。capture stub 每次恢复 last_capture 以匹配真实 coordinator 清空语义；关闭 recorder 并保留测试原件。fixture 不手造缺 event 的所谓合法 saved。用此真实形状接入 reader 的 ACQUISITION_END 比较，并断言任一 payload 字段篡改仍拒绝；可仅抽取现有严格比较为窄纯 helper，必须由 validate_full_trace 实际调用，禁止降级全字段检查。
- [ ] 增加 `test_full_trace_exact_recipe_event_inventory`：healthy九个teacher/18 action边界接受；teacher额外ordinal10、0、bool、缺一、重复（重复在流式分支测试）、action缺边界或额外键都拒绝。用小型metadata fixture并实际覆盖 reader调用的校验路径，不靠手造一条无关断言；summary保持合法9/9以证明不依赖其计数掩盖多余journal事件。保留原recipe helper的顺序/跨度/dwell检查，不改其历史源码。
- [ ] 仅运行上述新增 fixture 的 RED，保存精确命令/退出码/原始输出。预定失败为旧 V3 adapter 尚不存在/旧字段 KeyError，、新 END 返回值 event 缺失/严格 join 不等，以及 teacher额外ordinal10未被拒绝（或新窄合同函数尚不存在）；与这些根因无关的失败立即转下一 Astra。
- [ ] 实现固定 adapter 并接到 baseline_markers；保持原 exact4807/count/manifest/raw hash 验证。record_step 在 END publication 成功后返回 `{"event": "END", **row}`（或严格等价一次构造的完整 END 对象）；不能在 emit 的 kwargs 中重复 event，不能改变失败写入顺序。保留 reader 的全字段相等，不做 .get 多格式 fallback、删字段或交集比较。
- [ ] 在 TEACHER_ACTION 流式分支将 ordinal gate收紧为原生int且1..9且不重复；在终态recipe检查前要求teacher_actions精确1..9、actions精确18键集，不以summary count替代；若抽取纯helper须在该生产路径调用。
- [ ] 重跑同一新增 fixture 为 GREEN；必要的影响集限原 publication/final-guard/range 与完整分母比较测试。新 fixture 的模型/renderer/真实 detector/旧 raw 解压调用必须为 0；不运行 baseline_markers 对真实 raw 全量审计。

## Task 3 — 定稿、窄验证与回交独审

**Files:** 仅 `F/implementation/round58-preflight/*` 新证据，T1/T2 所列源码；prepare_full.py 字节应等于 paused pin。

- [ ] 先检查差异只落于批准位置和新 fixtures；保存 source-after SHA、任务结果、RED→GREEN 身份与限制。对四源执行 `.venv/bin/python -m ruff check`、`-m ruff format --check` 和内存 `compile()`；若需格式化只限四源且最后重跑检查。保留每次输出，不覆盖旧 log。
- [ ] 用 `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. .venv/bin/python -m pytest -q -p no:cacheprovider F/test_cpu.py` 执行一次最终 owned suite，记录实际数量、退出码及墙钟；不得沿用 91 的旧数。定向 GREEN 与最终 suite 不累加成独立样本。不要重复旧40/90/342或全仓 suite。
- [ ] root 在真实 freeze 前做源码/metadata 闭包复核：必要 live 源、archive 与实际 import origin，一致的 fresh-process source inventory，prepare/execute/readout 必需项在冻结 manifest 中齐全；使用仅 /tmp 的 source-only preflight（如需）且禁止执行 runtime/model/camera/decoder。既有 temp-freeze 和错 origin fixture 证据有效但不能以先前 CPU 绿代替独立进程闭包结论。如 fresh process 暴露新依赖根因，停止到下一 Astra，不能本轮扩改 prepare。
- [ ] source-final 冻结只能发生在四源定稿与所有 owned checks 后，且为 `F/full-protocol` 首次 create-exclusive；独审在该 freeze 后评估精确字节，不得 actual 后修改 reader 并冒充预冻结。冻结及独审继续沿 round57/root 权限，本派单不执行。独审最多给 `PASS_SCOPED_SOFTWARE_READY_FOR_ONE_FULL_ATTEMPT`，不能给 actual/readout/formal PASS。
- [ ] 实施报告汇入 root 的下一步骤/阶段总结，保留历史失败与全部冻结原件。只有 root 后续在独审、pin、资源、无已有 attempt 等前置条件满足后，才可按 round57 执行最多一次 full actual、最多一次新 full readout；失败不重试。

## 实际运行前置条件与验收边界

执行本轮源码修复前必须核对本计划和所有 pinned input 仍适用。actual 前需最终 frozen source/header/environment/live/archive/origin 全匹配、独审 scope readiness、attempt-1 不存在、无并行 renderer、RAM≥6GiB、disk≥16GiB。沿用 capture≤3600s、reader≤1800s、每进程 RSS≤4GiB、output≤4GiB、失败自由空间≥1GiB、frame JSON≤8MiB、journal row≤16MiB。资源不足/失败保全原件和 PARTIAL，不降采样、不自动 retry。

本轮完成条件仅：批准 delta 已实现、真实格式新 CPU fixtures RED→GREEN、四源 static 和最终 owned CPU 通过、SHA/失败/步骤报告完整、准备交独审。规划阶段没有验证执行结果，不授予软件 PASS；即使随后软件通过，也不宣称 full4807 OBSERVED、gap 通过、physical equality、actual 成功或研究验收。

## 本次静态快审边界

已逐段阅读四源并追溯旧 END producer/coordinator/helper。range 保留 exact/short/extra；final guard 保留实际 snapshot 与最后 camera/state/ledger joins；journal 使用逐行上限和 guard释放；old/new 完整序列仍用 zip_longest；旧 full 与201现存读出仅有界读取首行确认格式。本轮除上述两个格式桥接问题及 exact9 teacher事件漏门外，未提出推测式框架整改。source/archive/origin 为代码路径复核，未执行 import/preflight，因此闭包运行证据仍待 T3/root。对旧 metadata/readout/index 的 SHA256 是输入身份固定，不是旧 raw 复现审计。未读取或解压旧帧 raw、未执行 tests、项目模块、model、decoder、网络、Git/Stage/DB 修改。
