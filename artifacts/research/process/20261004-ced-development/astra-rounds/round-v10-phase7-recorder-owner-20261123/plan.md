# Phase 7 记录器边界回调的实际 owner 校验计划

gpt-6.2-astra · 2026-11-23 · Git 基线 `2ec0c98f82a6cab7fb1f9abbec37631226d3d605`。当前未提交产品及测试字节见 [plan.json](plan.json)。本计划与全部前序计划冻结后不回改；实施情况与新的来源代另记步骤报告。

## 原失败、根因与范围

独立零步探针验证启动时 operational clock 可用。外来线程的非法 step 触发保护性急停；在其 CONTROL 写入屏障处，backend 数据和 recorder 均存活，guard 尚未退出，显式 clock.close 调用数为 0，真实 clock 已关闭。第一次控制写失败，随后合法 owner 将 ctrl[0] 从 0.75 写为 0，ESTOP 为真。backend 记录两轮共四条命令，recorder 记录 0 条；六条 operational 记录的 token 均为空、bracket 全部缺失。首错是 operational startup identity lost，其余为 operational owner is not live。另一探针前两个 hold 情形已通过，在 CONTROL END 位置确认其余资源尚在、clock_open=false 后中止，未完成余下组合。

NativeFullHorizonRecorder._on_boundary 在校验调用线程前记录 CONTROL 结果、CAPTURE 尝试或新 operational_events 行，随后对真实 owner 调用 begin_event/end_event；其现有异常处理还可能写入 recorder 的失败数组。OperationalClockOwner._check 按身份契约永久关闭误用的 owner。原 VisualRawRecorderV3._require_open 只检查 recorder 自身的活动标志/实际 owner 线程，可在触及时钟前安全执行。产品变更限定于 native_full_horizon_recorder.py 的实际回调入口；测试限定于对应 authority/recorder 来源回归和必要的既有 collector 集成断言。保留时钟身份契约、backend 外来来源错误证据、线程约束和物理制动。若发现超出这条路径的独立故障，先另轮计划。

## 实施、控制与验收

- [ ] **先存 RED。** 在固定候选与现有相邻解释器、软件 MuJoCo/SQLite 夹具上重跑两份审阅脚本，输出另存。用原 source_recorder 和真实 clock，固定合法 owner、外来 writer 和独立释放线程；用事件隔开外来 BEGIN/END、control 写失败和合法重试。在外来阶段前后对照全部相关 recorder 状态：operation/command/control、区间/计数、pending tokens、渲染分配和 recorder failures；检查合法 owner 身份/epoch 和其可用性。仅 owner 线程执行 clock 的有效性检查，外来线程不得调用其探测方法。保留原出错源记录，不用 mocked clock 证明恢复。
- [ ] **入口先拒绝。** _on_boundary 一进入就调用原活动/线程检查，置于所有 recorder 状态读写、super、应用 check_active、真实 owner 调用及会写 recorder 失败的 try/except 之前。适用 BEGIN/END 两相位及所有原分支，不给 CONTROL、CAPTURE、RESET 特例；同一个活动 owner 的正常先分配后采样和异常审计语义继续生效。外来/未活动调用抛出已有明确拒绝；让 backend 自己记录 operation_observer_failures 及原 guard 失败。拒绝不应妨碍真实制动，后台命令与未得到在线授权的 recorder 来源须分别列示。不得代签、补造父/clock、跳过源门、换一个 clock 继续、清除首个错误或把外来记录标成合法。
- [ ] **真实接管的三个区间。** 在外来 CONTROL 写失败后合法 owner 再次实际完成 hold、STOP、嵌套 CONTROL。核同一 clock 全程存活直到既有真实关闭时点；两个命令及一个 CONTROL 的三次 BEGIN/END 均有唯一真实 token、匹配 event_identity、同域有序合法 bracket；逐项对照 backend operation ID 和真实原命令序号、episode、物理步、parent interval、begin/end 顺序和控制写；STOP 包住其 CONTROL，两条命令归合法重试的 TERMINATION。将首次失败的外来命令与 guard/observer 拒绝保留在其真实来源，不接入合法区间、不为缺失早期命令重编号。后验另核无重复 recorder 行/未结 token/并发污染。正控含普通 owner、外来物理制动成功（无合法重试）、外来物理失败后合法重试，以及退出与 shutdown 在 hold、CONTROL END 的八种既有组合。保持 guard 首错及次级制动/来源故障、原五/八例、LIFT 步内与步后对照、合法 owner 真实时钟失效的拒绝。
- [ ] **最终集成与冻结。** 独立复审重复上述交错；在最终静态来源运行真实 worker/SQLite/recorder/落盘/公开 group 与 registry reader 的隔离 E2E及来源相关全套。核 recorder 字段实际落盘和读回，不得将可复算的合法重试升级为全组有效。复核冻结 v9/v10 正式原协议/claim/inventory、历史原结果（原 v10 的 428/429 缺父永久保留），按主计划 C 归档 CLI/独立 API 比对，使用最终代码做私有 --prepare-only、单帧/空登记预检；不运行正式 --collect-once。报告各既有全库分片执行的源码 SHA、selector、数量、结果与最终差分，正在运行的分片等实际完成后登记。对新差异影响的 recorder/guard/collector/reader/注册来源测试补跑全套；最终 targeted、实际 E2E 与独立复审必须是同一最终源码。此前分片不冒充最终整库覆盖。
- [ ] **交付。** 保留失败日志、本轮计划、开发和真实后端证据、阶段总结及最终源码指纹。正式仿真与新正式 claim 都是 0，硬件和生产模型调用均为 0。原正式 DB、协议、raw 和 claim 不修改。仅实施本次 recorder owner 边界。

## 命令

从指定工作树运行，设置 PYTHONPATH=src:.、PYTHONDONTWRITEBYTECODE=1、MUJOCO_GL=egl；PY、E 沿用主计划已有解释器和私有证据目录。先后各用新路径保存 RED/GREEN 与最终复核。

```bash
"$PY" "$E/review-teardown-clock-source.py" > "$E/recorder-owner-final-clock.log"
"$PY" "$E/review-teardown-owner-boundaries.py" > "$E/recorder-owner-final-boundaries.log"
"$PY" "$E/review-stop-probe.py" > "$E/recorder-owner-original-five.log"
"$PY" "$E/review-final-advanced.py" > "$E/recorder-owner-advanced-eight.log"
"$PY" "$E/lift-secondary-guarded-observer.py" > "$E/recorder-owner-lift.log"
"$PY" -m pytest -q tests/test_native_collection_authority.py tests/test_native_observer_failures.py tests/test_native_collection_stop_e2e.py tests/test_visual_raw_recorder_v3.py tests/test_mujoco_execution_guard_v1.py tests/test_mujoco_full_horizon_sampling.py tests/test_native_harness_stop_diagnostics.py
"$PY" -m pytest -q tests/test_native_full_horizon_originals.py tests/test_native_registered_admission_replay.py tests/test_native_registered_teacher_release.py
```

复用主计划已有历史读回与单帧配置，执行受影响范围发现的其余测试文件并记录完整命令、实际源、分母与输出摘要。单纯退出码或物理 ESTOP 不作为来源通过的证据。
