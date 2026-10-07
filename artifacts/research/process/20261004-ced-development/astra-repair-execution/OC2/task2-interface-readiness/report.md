# OC2 Task2 静态接口就绪审查

本报告只读当前源码、round60/round57 计划与保存 metadata；未运行产品 import、inventory、CLI、test、probe、backend/renderer、网络或 Git，未读 raw/DB，未修改代码。Task2/3 stub 是计划内待实现接口，不登记为新产品 failure。marker 与 OC2 Task1 门仍由 ROOT 释放。

## 准确接线

| 责任 | 现有接口与接线边界 |
| --- | --- |
| startup/prereg | `_prepare_source_v1(app, exact worker, original job, start_monotonic=original)` 已建立真实 RUNNING/唯一 lease/open attempt、zero-arg OC1 owner、精确 handles 与 exclusive prereg 读回；随后才能 initialize/注册 observer/RESET。 |
| sole observer | 新 `OperationalPrefixRecorderV1` 继承 `VisualResetClockRecorderV2`；`__enter__` 唯一注册 `backend.observe_operation_boundaries(self._on_boundary)`，须在 backend.initialize 后。新 D tee 先分配 attempt，再调用 super；按 operation_id map 支持嵌套。 |
| D API | BEGIN→`begin_event(kind)`；可信成功 END 核对 id/kind/result/error 后→`mark_event(token)` 一次→`end_event(token)`。current→`read_current(after=原capture token)`；exact token/bracket/domain 活对象有效，descriptor/hash 等值不授权。 |
| S/RESET | event 原字段是 episode_id、physics_step、sim_time_s、parameters/result/error。RESET BEGIN 保留 old/None episode，END 才是新 episode；不回填 BEGIN。operation_ledger 本身没有 sim_time/result，D ledger 需保存完整 event 快照。 |
| capture/cache | RESET 与 step(120) 内部 cached CAPTURE 都实际新渲染；正常 recipe 是 cached1+cached1+explicit1=3 实际 CAPTURE。继承 capture 一次调用真实 capture_with_instances；按实际 allocation/failed IDs 归档，不能只数成功 frames。真正 cache read 保留原 acquisition/source bracket，不刷新年龄。 |
| failure | backend 吞 observer BaseException：function return 不证明观察成功，必须核对 backend failures+D partials+super audit。error END/缺 END/result 重构失败不补 MARK/END。 |
| publish | 原 repository.publication_guard 内重新核对 live lease/fencing/精确 handles/config/source/asset、原件 hash+bytes 与 public reader；exclusive receipt/catalog 均落盘成功后才开放 private catalog。失败保留全 prefix，不重试。 |
| reader | 新 reader 仅读原件重算 prereg/source/recipe/session/RESET120/D-S/event/frame/allocation joins、完整分母、路径与 SHA/bytes；不读现在 D/DB live，不重建 token，不信 receipt PASS。R03 reader 固定 explicit=0，不能直接用于 OC2 explicit=1。 |

runner 顺序：prereg 读回→same backend initialize→borrowed capture enter→single new recorder issue/enter→RESET1→purpose(SETTLE)/step120→inherited capture1→原 acquisition current D/S→freeze/export→guarded publish。各大操作前后复核 exact/live 状态。age 用 `[max(0,n−−c+), n+−c−]`，TTL 用上端 ≤5_000_000_000；TTL 与 source complete 分开。

容易误接的现有行为：legacy `_clock_pair` 与 RESET journal 仍是 MONOTONIC+UTC，绝不能重命名为 D；borrowed capture 进入不会 initialize/reset/shutdown backend；RawV3 构造要求具体 backend/capture/executor compatible CPU fixture；legacy export 默认 INCOMPLETE 不是新 source verdict，export/flush/退出可能重复写 frame，new layer 要保全 frozen originals、失败 ledger 和 allocation census。worker `_execute` 目前只特别识别 native/vision result scope；round60 只允许 early branch，若需改 terminal mapper 或 teacher/backend/OC1，应先 ROOT→Astra，不能在此扩大范围。

## 225 闭包与 RW1 并行边界

独立 stdlib/indexed AST BFS 得到 **225**，与保存 Task1 metadata 一致；未调用产品 inventory。paths-list SHA256：`652b792c49bac2a484049c2a764cc69e067058a4f288d1e3f3b63305b49c6f9d`；pins-map SHA256：`c6429e5bfa201791532d26b65adc371ea3012d8479f291341d567bec15bc5f7c`。

- 实际 `research/protocol_generation.py`、`simulation_runtime/recovery.py`、`datasets/rgbd/teacher.py` 都不在 225。
- `recovery/protocol_generation.py` 与 `vision/teacher.py` 不存在。teacher 虽不在闭包，却在 OC2 plan59、round61 input94、独审保护142 等 metadata 的显式保护清单中。
- 已核对 OC2 plan59、round61 plan/input94、preflight59、独审 before/after142：均无 producer 路径；当前已读保护源码全部匹配 round61 保存 pins。
- R07 plan14、保存 source/archive maps 均不含 worker/operational 四模块。现有 `_source_pins` 是显式 SOURCE_PATHS20+XML glob，不是 transitive inventory；另做独立 static closure186 也无 worker/operational 模块。
- ROOT 释放 marker 与 OC2 Task1 终审门后，严格 **RW1 producer 私有 owner** 与 OC2 Task2/3 软件改动在静态源窗口不相交，可并行。不能引入 OC1/OC2 dependency、改通用 raw/origin/source-contract constructor 或借此执行 actual；这会改变结论并需 ROOT/Astra。
- **RW2 teacher 绝不并行**。RW3 最终 freeze/actual 应待协调 quiet window；所有 renderer actual 继续全队串行。

建议窗口顺序：当前只读→ROOT 完成并释放两项门→OC2 owned modules+small worker branch 与 RW1 producer 软件并行→OC2 bounded software/quiet freeze/独审→ROOT unique actual 与 frozen reader→再协调 RW2/3。此审查不替 ROOT 授权，也不声称软件/实际来源/正式研究验收。

逐文件 SHA256/bytes、接口来源窗口和 reader join 清单见相邻 report.json。

RW1 两文件补核：`research/protocol_generation.py` 与 `tests/test_protocol_generation_sources.py` 在上述六份 OC2 metadata 均无保护引用。并行窗口仅这两路径；未接 teacher/wallguard 前最高是 owner 整数数学/生命周期软件结果。禁止 recovery-0002、freeze/prepare v3 或任何 actual，本报告不授权这些步骤。
