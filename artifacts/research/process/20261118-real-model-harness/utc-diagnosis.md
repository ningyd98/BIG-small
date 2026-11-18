# UTC 双后端 600 秒门诊断

原联合门于 600.017 秒退出，状态为 `TIMEOUT_UNCOMPLETED` × 2。CPU 采样把初始阻塞定位到本地时序记录的反复解码、历史回放和投影。±24 小时 UTC 替身和联合门的计时使用不同来源。测试的全帧资源观察器进一步增加解码开销。当前结论只覆盖 CPU 软件诊断。600 秒门仍待修复与重验。 [原联合门回执](../20261117-grasp-lift-stop/evidence/closure/utc-joint-600s-gate/result.json)

## 原始证据

| 冻结记录 | 结果 |
| --- | --- |
| [联合门](../20261117-grasp-lift-stop/evidence/closure/utc-joint-600s-gate/result.json) | 两节点同一次 pytest，memory 排首，600.017 秒，退出 −15，两个节点均未完成 |
| [memory 单独诊断](../20261117-grasp-lift-stop/evidence/closure/utc-diagnostic-memory/result.json) | 1 PASS，2,466.618 秒 |
| [SQLite 单独诊断](../20261117-grasp-lift-stop/evidence/closure/utc-diagnostic-sqlite/result.json) | 1 PASS，2,468.269 秒 |
| [此前 watchdog 原始栈](../20261004-ced-development/astra-rounds/round-simulation-baseline-regression-20261117/input-evidence/closure-watchdog-crash.log) 与 [120 秒非完成](../20261004-ced-development/astra-rounds/round-simulation-baseline-regression-20261117/input-evidence/closure-sampled-time.txt) | 相邻的 startup memory 节点出现 pytest 原生 watchdog 栈输出中 SIGSEGV，停用该 watchdog 后在 120 秒外层约束退出，消耗 119.56 CPU 秒 |

单独通过总和为 4,934.887 秒。原联合运行已设置 `faulthandler_timeout=0`，仍消耗全部 600 秒。旧记录均保留。原联合门和独立诊断从 `41bb3334` 启动。本轮检查 `318a546dd3a945bddc076cc06bc3528966a4051a`，两版的 `src/`、UTC 测试、软件工厂和 conftest 逐文件无差异。 [前轮汇总](../20261117-grasp-lift-stop/report.md) · [原 runner](../20261117-grasp-lift-stop/runner-as-executed.py.txt)

## 计时和调用路径

- 测试 `_b_t3_utc` 安装 16 个指定模块的 `datetime` 替身，固定 `now()` 为当次 UTC 基准 ± 一天，保留 datetime 类型检查兼容。它未改动标准库 datetime 模块、`time.monotonic`、`Event.wait`、子进程或 runner。runner 的外层 `proc.wait(timeout=cap)` 和耗时 `time.monotonic() - start` 位于父进程。worker 的起始元组同时记录真实 monotonic 和被注入的 UTC。租约启动和 RPC 真实限时由 Event wait 控制，心跳使用 Event wait 间隔。两个 operational clock 的手动 `_Counter` 原本就是测试的控制条件，用于推进监督 300 ms 和硬边界精确到期。 [测试 UTC shim](../../../../tests/test_operational_runtime_closure.py#L5657) · [测试计数器](../../../../tests/test_operational_runtime_closure.py#L3799) · [worker 启动](../../../../src/cloud_edge_robot_arm/simulation_runtime/worker.py#L298) · [租约 session](../../../../src/cloud_edge_robot_arm/simulation_runtime/operational_lease.py#L580)
- 真实 `SimulationWorker.poll_once` 进入已明确隔离物理接口的 `software_factory` 后，`_b_t3_ground_and_route` 经实际 worker 读取 bootstrap、采集和计划保留，进入 `_local_adopt`。两组采样都在此进入 `_local_mutate`，同时出现重复的 `LocalEnvelope.from_payload`、`_history`、`_semantic`、`semantic_projection`、`_copy` 和 JSON 序列化。16 秒点也采到已知正常的 locked-check 边界。历史成功工件的终态输出时间显示，每个正向 ±24 小时情景约 20 分钟，三个 worker poll 都完成后才写最终 provenance。末尾真实硬边界情景约 10 秒。这个拆分用文件 mtime 近似，CPU 栈采样覆盖首个正向情景前 32 秒。 [测试入口](../../../../tests/test_operational_runtime_closure.py#L5712) · [真实 CPU 工厂](../../../../tests/test_visual_worker_factory.py#L63) · [本轮采样和历史 mtime](../../../../experiments/results/phase9/real-harness-20261118/utc-diagnosis/trace-summary-v2.json)
- 生产 codec 对原始和子记录执行严格 JSON 拷贝、规范化、递归投影及历史重放。同一次 `LocalEnvelope.from_payload` 已经能复用已成功验证的子记录，键为完整规范内容和类型，容量 128 项、8 MiB。每次命中之前仍深拷贝和规范化。根解码结束即清除；下一次正常读或独立投影重新验证。同一记录的 `to_payload()` 和多处内部属性也反复解析和拷贝。worker 会分别处理持久化读取、CAS、PENDING/COMPLETE 事务内容及其子记录。当前采样显示的是这些有限计算的持续运行。 [codec 与每根 memo](../../../../src/cloud_edge_robot_arm/vision/local_temporal.py#L1834) · [历史重放](../../../../src/cloud_edge_robot_arm/vision/local_temporal.py#L1365) · [worker 发布事务](../../../../src/cloud_edge_robot_arm/vision/worker_runtime.py#L570)
- `_b_t2_observe` 为测试主线程和新线程安装 Python profile 回调，观察真实 poll、session、broker/heartbeat 及收尾。它也接收 codec 细粒度函数事件。UTC 测试使用既有软件工厂的三个完整 poll，且原本运行两轮正向 grounding/route/supervision。该安排会集中暴露大型生产记录的处理开销。 [观察器](../../../../tests/test_operational_runtime_closure.py#L3818) · [UTC 情景](../../../../tests/test_operational_runtime_closure.py#L5716)

## 本轮 CPU 数据

[机器可读诊断回执](../../../../experiments/results/phase9/real-harness-20261118/utc-diagnosis/result.json)

32 秒采样组保持真实 worker、原 memory 测试和资源观察器，选择历史联合门相同的 CPU 7、15，关闭 pytest 原生 faulthandler，使用 Python 信号采样。对照仅在临时进程把 `_b_t3_utc` 置空，因而不能验收外部 UTC 断言。采样到时停止于第一个正向分支，尚未触发外部检查。两组最后的 SIGTERM 采样均显示进入实际 adopt 后的生产方法。无 UTC 替身对照在 1 秒清退宽限后收到 SIGKILL，结果以清退前的进程 CPU 样本为准。 [采样命令](../../../../experiments/results/phase9/real-harness-20261118/utc-diagnosis/command.sh) · [正常原始日志](../../../../experiments/results/phase9/real-harness-20261118/utc-diagnosis/normal.log) · [无 shim 日志](../../../../experiments/results/phase9/real-harness-20261118/utc-diagnosis/no-utc-shim.log)

| 组别 | 进入首轮 grounding/route | 最后停止前进程 CPU / 采样 wall | 退出 |
| --- | ---: | ---: | ---: |
| 正常 UTC shim | 3.952 s | 31.430 / 31.843 s | 124 |
| 移除 UTC shim | 3.936 s | 31.448 / 31.844 s | 137 |

读取旧 memory PASS 留下的只读 UTC provenance，取首个正向情景的 route 和 supervision。当前生产 codec 对两份 payload 分别独立完整解码两次。第一次不装 profile，第二次安装轻量同类事件过滤。两遍各记录的输出 SHA256 一致。这个微测隔离了生产解码本身和接收 profile 事件的额外代价，实际测试观察器的完整总开销尚待独立计量。 [微测命令](../../../../experiments/results/phase9/real-harness-20261118/utc-diagnosis/codec-command.sh) · [原始结果](../../../../experiments/results/phase9/real-harness-20261118/utc-diagnosis/codec-probe.log) · [输入 SHA256](../../../../experiments/results/phase9/real-harness-20261118/utc-diagnosis/codec-input.sha256)

| 产物 | 紧凑 JSON 字节 | 裸生产 codec | 帧事件过滤 |
| --- | ---: | ---: | ---: |
| Route | 856,395 | 1.018 s | 2.075 s |
| Supervision | 2,465,241 | 3.326 s | 6.548 s |

没有在本轮运行 SQLite 完整测试或原联合门，也未启动真实物理、renderer、GPU 或模型 API。定位来源是 memory 前 32 秒的对照采样、历史两个 backend 的证据与双方共用的生产 codec。离线汇总首轮因包含 pytest 别名链接而退出，失败记录与空输出留存，修正汇总仅排除符号链接。 [定位输入 SHA256](../../../../experiments/results/phase9/real-harness-20261118/utc-diagnosis/source-inputs.sha256) · [汇总首轮失败记录](../../../../experiments/results/phase9/real-harness-20261118/utc-diagnosis/trace-summary-first-attempt.log)

## 给修复计划的边界

先为当前可保留的完整 route/supervision 和采用记录补测独立 codec 次数、相同根重复率与自耗时。优先减少现有纯 codec 操作中同一输入的重复复制、规范化、读取和递归投影，优选已验证对象的内部窄读取或单次同步操作内的有界复用。外部不可信输入仍做严格校验并返回独立可变副本。一个新的可控性能对照可锁定重复操作数量和实际耗时，并校对规范字节/哈希、合法样本、篡改记录、同内容不同类、异常及跨上下文隔离。当前 memo 入口和上限已有明确测试约束。跨请求缓存、按对象身份跳过校验、对 PENDING 和 COMPLETE 共用授权结果都不具备本轮支持证据。 [现有 memo 验证](../../../../tests/test_local_temporal_decode_memo.py#L113) · [JSON copy 行为](../../../../tests/test_local_temporal_copy_dispatch.py)

可以独立估算 UTC 测试资源观察器只在现有真实生命周期边界采样的性能收益。候选变更应保留 poll 进入/退出、资源创建/关闭、issuer、心跳和 broker 等证据。如果变更涉及共享观察器，须对共享它的相邻 startup、terminal 和 public 路径回归。历史约 8.22 倍的总耗时差距，无法由本轮微测中约 2 倍的 profile 影响单独解释或验收。

验收仍是原 `[memory]` 和 `[sqlite]` 节点在同一次运行的合计硬上限 600 秒内都通过，保留两次 UTC 偏移、本地 provenance 与预算、监督 cadence、公开 UTC 的 ±1/5 秒等精确边界、过期判定、硬上界迟到回复拒绝、不再发布及资源证据。使用新目录和独立日志、JUnit、回执。现有路径和原始证据保留。软件门的结果与真实模型 Harness 和正式研究验收分别记录。 [原断言和节点](../../../../tests/test_operational_runtime_closure.py#L5682)
