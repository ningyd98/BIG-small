# R449 — 实时 tracker 与原始时间离线重放

实际规划模型：**gpt-6-astra**。2026-11-08 Asia/Shanghai。仅规划；未执行测试/物理/render/模型请求，均为 0。

## 原始失败

R448 ruff/format 子进程 rc0；pixel-repair **2 FAIL**、rc1、监督 2.503807901 s，reaped、无漂移/残留。两项已经通过真实 marker 尺寸/平面路径，但 B bootstrap 的 OpenCVTargetTracker.__init__ → _binding_reason 以机器当前 UTC 检查 2026-11-07 fixture，报 `initial acquisition unavailable: capture_time_not_fresh`。原 stdout/JUnit/events/result/spec 与源码完整复制 intake；所有输入 SHA256 见 inputs.json/plan.json。

同时确认产品 reader 缺口：registration_bootstraps 的 B/E 初始化与 decisions 的 grounding/admission facts 都调用实时 tracker。已有 binding_now、evaluation_at 和 timeline.checked_at 分别属于不同判断，不能冒称 tracker 内部读取的 UTC。仅 monkeypatch 测试时钟会掩盖 reader 对超过 5 秒历史原件的错误拒绝。

## 限定设计与接口

1. **旧 tracker 仅提取纯判断 seam。** 在 vision/tracking.py 把现有 _binding_reason 函数体原样提取为 `_binding_reason_at(observation, evaluated_at)`，仅将 datetime.now(UTC) 换成参数；全部身份/相机/几何/时间门限及顺序保留。实时 `_binding_reason` 每次自行调用 datetime.now(UTC)，将该次实际值保存在私有 `_last_binding_evaluated_at`，再调用纯 seam；提供只读 property `last_binding_evaluated_at`。构造与 facts 原流程继续走实时入口，不增加 caller clock、skip freshness、archive flag 或公共资格开关。返回 facts 的原 schema/内容不变。每次调用都覆盖旧值；不能读取上一帧时刻冒充本次。naive/不合法离线 UTC 在适配器入口拒绝。

2. **分离纯 bootstrap 像素计算。** 在新 grounding 模块将现 bootstrap_collection_tracker 的相机/marker/目标和区域像素/resolve_top_grasp/evidence 计算提取为 `collection_bootstrap_evidence(observation, registration)`，不改算法。实时 wrapper 调用它后仍构造精确 OpenCVTargetTracker。reader 不调用这个实时 wrapper，而使用同一纯 evidence 计算和独立 archive adapter，禁止复制 tracker 全算法或伪造 facts。

3. **私有 archive adapter。** 新文件 research/native_archived_tracker.py 定义 `_ArchivedTargetTracker` subclass，仅 reader 导入。构造显式接收经过验证的原 tracker UTC；覆盖 _binding_reason 只调用原 `_binding_reason_at`，同一个原算法。后续 `facts_at(observation, state, evaluated_at=...)` 用单次上下文调用 super().facts，finally 清除时刻；无有效单次时刻的普通 facts 调用拒绝，不能悄悄沿用上次或读分析机时钟。构造也只使用单次上下文。adapter 不输出任何控制令牌/权限，不被 live bootstrap 返回。保留 app `_evaluate_collection_admission` 的 `type(tracker) is OpenCVTargetTracker`，新增测试证明 archive subclass 被拒绝。无需新增 universal allow 或改 owner/controller/Shield。

4. **记录真实每次判断，不能借用邻近时间。** 给 B 初始化、E 初始化、每个 grounding facts、每次 admission PRE/POST/TERMINAL facts 建立 `native.tracker.clock.v1` 原始记录。每条包含：purpose（BOOTSTRAP_B、BOOTSTRAP_E、GROUNDING、ADMISSION_PRE/POST/TERMINAL）、index/step_id（适用时）、acquisition 原始 path/SHA/id、observation_id/checksum、source_generation、started_at、evaluated_at、finished_at，及 consumption_before/consumption_after。started/finished 由实际 source 在判断外围读取 UTC；evaluated_at **只能从本次实际 tracker 的只读 property 取值**。两个 consumption 都来自现 app._consume_capture，分别在对应真实工作外围调用；保留原 capture、OC1 domain/bracket、S、lease 和 original deadline。不得从 UTC 推算或制造 BOOTTIME。

   B/E 的记录分别保存 `tracker-clock/bootstrap.json`、`tracker-clock/dispatch.json`，注册 timeline 两行各增加其 path/SHA 引用；bootstrap.json 和 dispatch-bootstrap.json 仍保留原 evidence。B 尚未 compile 时 _consume_capture 不依赖 original，可先记录，之后 reader 用同一身份/来源核对；不提前发放 session。handoff helper 可增加私有关键字 callback `consume_capture`，生产调用明确传 app._consume_capture，软件 fixture 仅提供标为 SOFTWARE_ONLY 的一致性 stub，不产生物理动作。

   grounded_collection_step 在每次真实 facts 后保存实际 `tracker_evaluated_at`；其 evidence_sink 由 app 的局部 wrapper 将外围起止 UTC、前后真实 consumption 合成完整 `tracker_clock` 后再交 recorder.record_grounding。不得先落一份不完整记录后覆盖。保留 binding_now/checkpoint 时间原语义。admission 同样取得本次时刻，现已存在前后 consumption 可保留并显式绑定到记录，后消费须发生在原始输入落盘/授权执行之前；不能丢弃原后检查。

   最多两次 bootstrap、8 次 grounding、17 次 admission，共 **27 条**，不存在逐帧无限 trace。额外 owner reads 不增加 physics/capture/render；原 OC1/lease/TTL 上限照常约束，失败则停止。记录/写入失败仍产生 partial/failure，绝不继续权限分发。

5. **reader 先验原件，再以原时刻重算。** 为 _Audit 增加严格 `tracker_clock(...)` 校验：原库存 SHA/引用/phase/index/step/frame/source generation 完全匹配；三个 UTC aware 且 UTC offset=0，started≤evaluated≤finished；实际 freshness 仍为 -0.05≤evaluated-captured≤5（B/E handoff 更严格原规则仍保留）。调用现 consumption 校验处理前后两条，验证同 acquisition、当前 S、domain、原 deadline、真实 acquisition bracket 和 lease；二者单调，UTC 起止与 lease acquired/expires、task 原有效期一致。不能用新到期时间刷新来源。检查各调用先后顺序，B 判断先于 original registration；E 判断晚于 handoff checked_at；grounding 的 binding_now/checkpoint 在本次判断之前；admission evaluation_at 在本次 facts 后。检查完整 clock 记录亦在原 caller 外围起止内，不把 UTC 与 OC1 数值相互换算。

   registration_bootstraps 验完 B/E clock 后才构造各 archive tracker；保留 B/R/E、每次 frame bytes 复验与 max10 boundary identity cache。decisions PRE 用原 grounding tracker_clock 的 evaluated_at 重算 ground facts；每次 decision 用对应 admission 的时刻重算 facts。collection_grounding_inputs/_nominal_release 只调用 _geometry，不新增虚构 clock；bind_step_grounding/evaluate_conditions 仍分别使用各自原 binding_now/evaluation_at。逐处检查所有 bootstrap/facts 调用没有遗留 live-clock fallback。旧缺时钟证据的 raw 不补写，报告缺原件/UNKNOWN，不能用捕获时间推测替代。

6. **软件 fixture 的时间统一。** R446 fixture 可在测试内同时 monkeypatch tracking、grounding、app 三个模块 datetime 为同一 FixedTime，保留历史 t0 与时间差；生产禁止 global monkeypatch。添加相应 SOFTWARE_ONLY clock source 数据供真实 reader 校验。现 _registration_case 先 compile 后 B bootstrap 的顺序也应改为与真实 app 一致：B 的 bootstrap/clock 先完成，再读取 lease/compile R，最后 E；使用原 t0 的合理严格中间时刻，不回填任何实际原件。已有独立 fake 单元夹具可显式提供其 SOFTWARE_ONLY 时刻属性以适配记录 API，但不得用 fake 替换本轮四节点的真实 pixels/tracker。独立 archived replay 测试必须解除/推进 live clock 到数天之后，再以原字节和原 clock 记录重算；由此证明 reader 无测试冻结时钟依赖。R448 的 10px marker 和 quiet-plane 原件不再调整。

## 范围、验证与停止条件

精确允许路径见 plan.json.allowed_edits：旧 tracking 一处纯 seam，既有新 grounding/app/reader，新增 archive adapter；测试限 grounding/authority/reader 与新 archived tracker 文件。不得改旧 owner/RawV3/Shield/backend/marker/资产/阈值。相关源码生成 hash 将真实改变，必须 fresh prepare；历史数据与协议不重写。

新增 tests/test_native_archived_tracker.py 恰四个节点（完整 node IDs 和 argv 已在 plan.json）：

- 历史真实像素在原时刻可重算、事实等于当时实时结果；数日后的原实时 tracker 仍拒绝旧帧；reader 不依赖分析时钟，raw bytes/hash 不变。
- 原判断已超 5 秒、未来超过 .05 秒、naive/missing/reversed clock、不同 frame/phase/S/lease/deadline/source、超 TTL OC1、修改原字节逐项 fail closed；在同节点内部参数循环，无额外 collected 扩张。
- archive tracker 无单次时刻直接 facts 拒绝，异常后上下文清除，两个实例隔离；实际 app exact-type gate 拒绝 archive subclass，原 LIVE freshness 不受影响。
- 真实 bootstrap B/E、grounding 和 PRE/POST/TERMINAL 重算逐处消费各自来源时刻；missing/tampered clock 不允许 fallback；保留 NONE/UNKNOWN 与原绑定、原 Shield 原件比对。可使用既有软件 authority/reader fixture，但不得 mock tracker/detector/facts。

唯一 RED：先写四节点 API/record-contract 断言，运行一次，预计恰四项明确缺 API/record contract 失败；不接受 import crash 或意外失败。保留 R448 原两失败作为基线，不再额外 probe/RED。

实施后对允许九文件一次格式化；依次运行一次 scoped ruff、format、mypy，再唯一 clock-green：旧 tests/test_opencv_target_evidence.py（验证旧实时语义）以及 collection_grounding、collection_authority、full_horizon_originals、calibration_collection 和新增 archive tracker 六个 CPU 文件。产品时钟 seam/reader/source 发生改变，这一范围有直接回归理由；不重跑整个 230。child RED/static120 s、GREEN300 s，outer 各加120 s。所有命令、环境、隔离 basetemp、事件/JUnit/原始日志路径均在 verification_specs；无真实物理节点。恰四新节点，其他旧节点不删不放宽；实际 collected 数从冻结源码与本次事件报告，不单独 collect-only。

任何计划外失败、pin 漂移或范围扩大停止依赖工作，下一轮实际 Astra；禁止自动重试、边跑边修或额外诊断运行。验收须原节点目标实际到达、全选 CPU PASS、各子命令 rc0、reaped/无漂移/残留。R447/R448 原失败永久保留，跨轮覆盖按源依赖列明，不冒称本轮新跑完整230。

## 仅面向未来的 R439 source overlay

本轮实施后新建 `implementation/future-r439-source-overlay.json` 与新的 runner/commands 副本（可名 commands-r449.json），记录本 plan SHA、原 R439 baseline/commands-r440 SHA、每个批准改动的前后 SHA、现 source inventory/source generation、stage/runtime pins。只适用于**尚未运行的 prepare/full/read**，将本轮精确旧 tracking 与新 archive adapter 及已允许新模块/测试纳入原计划路径集合；禁止通配扩大、忽略漂移或覆盖历史 commands/spec/results/baseline。先复核 baseline→当前所有变化都有 R439–R449 授权，再冻结 fresh specs。prepare 必须重新生成真实新 source generation，full/read 使用同一不可变原件。原工作树其他变化不因此获准。

原 R439 的首组独立分配、原 full/read 命令行为与资源/物理/render/时限上限均不增加。所有 CPU/static 通过并完成一次新鲜 whole-change review 后才可按原实际前置条件放行；本 R449 规划/验证实际额度为 0，九组仍未放行。旧 raw/native UNKNOWN 不因 archive replay 获 online/native 权限。

自审：修复真实 reader 边界而非仅测试时钟；没有扩大 freshness、复制 tracker 算法或借 caller flag 发权；实际判断时刻由源记录并同 OC1 核验；验证与未来 runner overlay 都有明确边界。
