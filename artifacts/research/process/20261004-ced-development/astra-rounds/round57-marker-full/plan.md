# Marker V4 Full-Horizon Implementation Plan — Astra Round57

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement task-by-task. 本轮仅交付计划，不实现、不测试、不运行 actual、不联网、不修改 Stage/Git。实施和独审的角色沿用户授权；出现新问题必须停止该切片，由下一轮 Astra 先生成修改计划，不自行套补丁或重试。

**Goal:** 在独立冻结的 development 协议下，一次采集并严格逐帧验证 step 0..4806 的全部 4807 个 marker V4 RGB-D，判定完整帧可观测性。

**Architecture:** 新建 artifact-local prepare/runner/streaming reader/test 四个源码文件。以 SHA 验证后复用旧 V3 教师、控制器、守卫及 pure verification helpers；新增完整范围 recorder 和 final guard，不修改历史 sparse producer/reader、公共生产源码或旧原件。离线仅传入真实保存的 RGBDObservation 与固定 marker registration 调用原 detector。

**Tech Stack:** Python 3.12、现有 MuJoCo 3.3.7、NumPy、OpenCV ArUco、Pydantic、gzip/JSONL；不增加依赖、不升级环境。

**Spec:** `artifacts/research/process/20261004-ced-development/report-step56.md`，R01 V4 `fix-round-1/offline/report.md` 与两份 scoped independent-review；本次用户 full-horizon 要求。精确输入 SHA/bytes、源清单和机器可读验收条件见同目录 `plan.json`。本计划及新 full 协议均不回写上述 sparse 证据。

## Global Constraints

- 旧 V3 完整分母是 4807，4618 OBSERVED / 189 UNKNOWN，采样 max gap 0.004166666700001542 SimulationS；旧 sparse 分母永远为 201，189 原 UNKNOWN + 12 健康，实际 201 OBSERVED / 0 UNKNOWN，max gap 2.1166666836000267 SimulationS。两者不得拼接或互相扩分母。
- V4 资产 SHA `045ce032032426ec6130348ee75e5f53b7db02699fc1f39558727edd63f67e0d`；ID7、DICT_4X4_50、75 mm、局部 attachment [0.16,0,0.03505] m、37 visual-only tiles，mass/density/contype/conaffinity=0。不再次设计尺寸或偏移。
- 原同一顶视 640×480、noise0、seed0、physics_dt_s=0.0041666667、control_dt_s=0.02、sensor_dt_s=0.0333333333、120 settle、9 原教师动作、2 原 dwell、4806 物理步、743 命令和 controller 原样保留；不改 formal/default 320×240/noise.001 域，不将 development640 设为新默认。
- 原严格 detector SHA `68f9e6e0675a4b6ccdead896bd767c685fd53357591ab1fdf4d71d124c72264f`，guard SHA `65649dff03ddc84cfaca14fa6f8439c325746b6dddaf956e525df70a9d71aa28`。不改阈值、errorCorrectionRate=0、不用 truth 补 pose、不迁移帧号、不插值、不删除 UNKNOWN/失败、不重跑旧 actual。
- `formal_accepted=false`、`native_admission=NOT_PROMOTED`、`source_authenticity=UNKNOWN`、`independent_calibration_group=false`、`continuous_motion=NOT_CERTIFIED`、`continuous_visibility=NOT_ESTABLISHED`、`future_stability=UNAVAILABLE`；geometric_error_bound_m/angular_velocity_bound_rad_s 保持 null，每帧 stability_status=UNKNOWN。全帧 OBSERVED 仅关闭本次 frame-observability 缺口。
- UTC 与 simulation.operational-time.v1 是独立队列；本轮不新增时钟来源或消费者资格。SimulationS 仅指同一 episode 的保存 sim_time_s，绝非 UTC、capture wall、运行 60 s 上限或新 operational 域。现有 nominal monotonic brackets 保留来源及嵌套检查，不升级为认证时间。

## Review Focus

1. 范围相同帧数但头尾错位、缺末帧、额外末帧：完整性必须依赖 exact IDs、终点、time 和事件 join，不能只计数（T1/T2 范围测试）。
2. 采集成功但 publication/guard/finalization 失败：保留 allocation、可用 raw/partial 原件及失败，终态不 COMPLETE（T2 故障注入）。
3. 长 journal、异常压缩帧和伪造时间类型：流式有界处理，bool/NaN/Inf/超限拒绝，失败分母仍 4807（T1/T3 负例）。
4. 文件完整而某帧 UNKNOWN、重复 observation ID 或原件 hash 错：不能声称全帧可观测；只对有效原件调用 decoder（T3 序列测试）。
5. 同一 source 名但加载来源漂移、读到旧 sparse header、已有 attempt 目录：在 runtime/model 前拒绝，不重冻、不自动 retry（T1/T4 gate 测试）。

## 源白名单与复用决策

以下令 `F=artifacts/research/process/20261004-ced-development/astra-repair-execution/R01/marker-v4-full`。只新增四个可执行源码：

| 新文件 | 责任 |
| --- | --- |
| `F/prepare_full.py` | 严格 full header/range/schema/source/environment 检查、一次 freeze、新旧输入保全 manifest |
| `F/run_full_once.py` | 配置隔离 V3 module、FullRGBDRecorder、逐回调 full capture、最终 guard、一次 attempt |
| `F/verify_full.py` | 流式原件/trace 校验、一次 strict decode、完整旧新配对/分母/采样 gap/失败报告 |
| `F/test_cpu.py` | 本变更的有限 CPU fixtures、range/失败/streaming/admission 反例 |

其余新增仅为本 F 内协议/source archive、限定日志、review、实际原件、readout；不得新写公共 src/tests/assets、旧 sparse 树、Stage56 377 项交付输入、Git 或 root 当前文档。F 不存在时新建；冲突即停止，不清空重用。

复用 V3 `t7b-continuous-visibility-v3/run_once.py`（SHA `0f7c5d31f21bd35a5d7085e57376436b6bf33f043c47fe227542d6d94d654340`）的 teacher/control/action wrappers、journal、CaptureAdapter、AcquisitionCoordinator、runtime_preflight、execute_once；在独立模块命名空间注入新 specification/source_preflight/recorder/coordinator，不全局更改公共配置。复用已审 sparse 的 FullStateAdapter 思路，将完整 qpos37/qvel33/act0/ctrl9 保留于每帧 capture evidence，不把这些数据送 decoder。

不把 `selected_steps=list(range(4807))` 填进旧 sparse header 或直接调用旧 sparse main：它固定路径/协议/201/selection，与完整协议不同。也不直接换回通用 StepRGBDRecorder：它没有冻结 exact4806 gate，且采用独立 UTC nominal 检查/容差语义。本地 FullRGBDRecorder 借用已审 BEGIN/END/FAILED publication 结构，新增完整 scope/range/final guard，公共 recorder 字节保持。

prepare/sparse pure asset validator 可 SHA 验证后 import；V3 helper 的 guard/recipe 验证可复用。不得调用原 `read_journal()` 将整个 journal list 化，不调用会扫描模型的预演，不对旧 201 或 4807 再 decode。source/archives 检查只枚举真实依赖，已有相同 SHA 档案直接引用，不重复复制 34 文件；新增四源各归档。仍从 live import 的模块须执行前核对 live SHA 和实际 `__file__`/runtime origin，不仅验证 archive。发现某必要公共源已漂移即拒绝并留下一轮；不临时放宽 pin，也不构建一套未审替代 import 系统。

## Task 1 — 冻结独立完整协议及资源合同

**Files:** Create `F/prepare_full.py`, `F/test_cpu.py`；生成 `F/full-protocol/{header.json,execution-source-hashes.json,execution-archive-index.json,source-final/*}`、`F/implementation/*`。旧文件只读。

**Interfaces:** `validate_full_header(header: dict) -> None`; `source_preflight(base, header: dict, directory: Path) -> MujocoStateContract`; `freeze_full(directory: Path) -> dict`。`run_full_once.py --prepare --protocol-directory F/full-protocol` 为唯一 freeze 入口；准备不加载 MuJoCo runtime/model。

- [ ] 先编写并仅运行本 task CPU 负例：sparse protocol、201/range/错误 type、gate=False/1、dt/gap/schema/source/environment/asset 变更、既有目录必须失败；冻结 exact range 的健康 fixture 通过。spy 明确所有拒绝先于 configured_runner/runtime/session/model。
- [ ] header 固定 `protocol=research.custom-full-guarded-marker-v4.v1`、`scope=EXCLUDED_SAME_COMPONENT_FULL_MARKER_V4_DEVELOPMENT`、`capture_policy=STEP_ZERO_AND_EVERY_REAL_PHYSICS_END`、`expected_physics_steps=4806`（type=int，bool 不接受）、gate=true、`expected_callback_steps=list(range(4807))`、`expected_frame_count=4807`、`attempt_limit=1`；`range_policy=RETAIN_ALL_ACTUAL_CALLBACKS_REQUIRE_EXACT_ORIGINAL_HORIZON`。scene/config 仅 V4 group_id 标记 full scope，不变 camera/physics/teacher 参数。
- [ ] schema 明定 `research.full-marker-v4-index.v1`、`research.full-marker-v4-readout.v1`，raw observation 继续既有 RGBDObservation schema 和序列化。不将 custom 标为 RawV3。固定 9 动作 identity/spans 来源、2 dwells、120 settle、743 commands、源/归档/环境 SHA、XML registration 与 snapshot contract digest `16bfd83aa42ba257b2b3932335fdf8d1fdab423c513102a5fa9cbdee53450c99`。新增 reader/test source pins 也冻结，不能 actual 后修改 reader 再称预冻结。
- [ ] 同一 episode 所有 callback/frame/index/PHYSICS/scorer sim_time_s 必须 exact join、finite real（bool 拒绝）、step0=0、逐步严格递增；`gap = t[i]-t[i-1]`，每个实际 gap `0 < gap <= 0.005`，无向上容差，保存实际 max 和越界 IDs。dt 一致性如需数值容差仅用于解释浮点累积，绝不能用于 0.005 admission。终点实际 time 必须等于最后 callback/frame/physics/terminal 的同一记录值。
- [ ] 资源合同预冻结：采集单进程 wall 上限 3600 s、reader wall 上限 1800 s，各 peakRSS 操作预算 4 GiB，执行前可用 RAM 至少 6 GiB、目标文件系统可用空间至少 16 GiB。新输出 raw+logs 总预算 4 GiB，预留至少 1 GiB 自由空间供失败终态。每帧 uncompressed JSON 上限 8 MiB、每条 journal 16 MiB，单帧解码后立即释放。上限是本轮操作止损，不是方法耗时证明或既有研究门的变更。超限终态为 RESOURCE_ABORT/PARTIAL，不减采样、不删原件、不续跑。
- [ ] 本 task 先以 /tmp CPU fixtures 验证 freeze 行为；真实 full-protocol 只在 T2/T3 四源全部定稿、owned checks 完成后、T4 独审前创建一次。freeze 含资源初始测量、旧新输入 inventory 引用和 CLI 命令；用 create-exclusive 写入，不重写目录。依赖 manifest 逐项核对，已有 21 MuJoCo/NumPy 环境 pin 保留；补齐 actual decoder 使用的 Python/OpenCV cv2 binary/Pillow/Pydantic 版本及加载入口 SHA（只读元数据，不网络安装）。若环境不能固定，停止到下一 Astra。
- [ ] 只对四 owned 源做定向 Ruff/format/in-memory compile；保存本 task RED/GREEN 命令及实际输出，不能重复旧 40/90/342 或全仓 suite。

## Task 2 — 全回调 recorder 与最终守卫

**Files:** Create `F/run_full_once.py`; update only `F/test_cpu.py` before freeze。

**Interfaces:** `FullRGBDRecorder(directory, capture, *, episode_id, max_sample_gap_s, expected_physics_steps=4806)`；`observe_step(*, episode_id, physics_step, sim_time_s) -> None`、`record_step(...) -> dict`、`finish(*, final_step, final_sim_time_s) -> dict`；`configured_runner(header: dict)`、`execute_once(directory: Path) -> None`。factory closure 保存 adapter/backend/contract，使 finish 能取得终态 snapshot，无需改 V3 execute_once。

- [ ] 先补 CPU 范围 fixtures（微型 observation/capture spy，不调用 detector/model）：准确 0..4806 为 COMPLETE；0..4805 为 short；0..4807 为 extra。extra 4807 callback 和已启动采集及原件都保留，绝不裁剪到 4806 变为 COMPLETE。检查固定 expected denominator4807、actual callbacks4806/4807/4808、missing/extra IDs 和非空原因；对额外合法 callback 一样保存 full capture，待终态拒绝范围。
- [ ] 每个有效 actual callback 先分配并记 PHYSICAL_CALLBACK，再恰好一次 coordinator acquisition BEGIN→camera guarded capture→raw exclusive write→END。step0、120 settling 和两个 dwell 全覆盖；不修改 teacher 的步进终止条件来凑 4806，不允许缓存帧代替新采集。duplicate/skipped/out-of-order/wrong episode/invalid-time 先保留 REJECTED 原始声明及失败原因，然后停止；不得把 malformed callback 伪装成合法范围。
- [ ] 采集失败/guard 变化/写文件失败/END publication 失败/FAILED publication 失败均保存已知 allocation、camera evidence、错误类型与原错误；已写 raw 或 partial 文件不能清理。guard failure 后无重试，无后续正常采集。顶层 finally 最佳努力保留失败终态和 summary；如果进程被 supervisor 强杀，则外部日志和 raw prefix 是 PARTIAL，禁止合成正常 terminal。
- [ ] 每帧独立验证 before/after support-aware guard 完整域，不仅 qpos/hash；nested monotonic brackets、sole camera/context/noise、两次注册 pass 与 before physics SHA 完全一致。full qpos/qvel/act/ctrl 字节映射与 guard DATA_BACKED 数组域一致；不把 unsupported null allocations 随机 owning bytes 当真实物理状态。
- [ ] `finish` 在 backend 尚活跃且最后读取/评分完成时保存 `FINAL_GUARD`：真实 `capture_state(backend, contract)`、last capture after-state/guard、final callback、final sim_time、command count、operation ledger 等 joins。要求与最后受护 camera after snapshot 的保护域一致且没有新增 physics/control/command；不调用 step/forward/reset/render。final guard mismatch 或无法取得原件必须 `INCOMPLETE`，写明 reason，不能仅据 final_step=4806 放行。已知 final-guard 失败以 summary 返回而非异常逃出阻止 V3 finally 写 terminal；I/O 无法保存时保留外层失败而不虚构日志。
- [ ] 补 final_step bool、terminal time 错、missing FINAL_GUARD、guard mismatch、capture exception、partial write、END journal 错、double finish、attempt 重入 tests；验证 initial+全部 planned callbacks 的分母保留。针对新 wrapper/recorder执行一次 owned suite与窄 static；与 T1 重合用同一 suite 身份，不累加虚高计数。

## Task 3 — 流式原件核验与严格逐帧读出

**Files:** Create `F/verify_full.py`; update only `F/test_cpu.py` before freeze；新 `F/offline/*` 只保存派生输出。

**Interfaces:** `iter_journal(path: Path)` 每次至多一条 journal；`validate_full_trace(attempt: Path, header: dict, contract) -> dict` 输出紧凑 join/错误索引；`verify_and_decode(attempt: Path, output: Path) -> dict`；CLI `--protocol-directory F/full-protocol --output F/offline --decode-once`。输出 4807 行 `offline-markers.jsonl`，外加 unexpected actual rows 的独立原件索引（不混入 planned numerator），`offline-verification.json`、旧新配对行、raw/source inventories、resource/log/report。

- [ ] 先写真实格式小 fixture 的故障测试：完整三帧、首/中/末缺失、同数错位、额外 ID、重复 observation_id、坏 compressed/original/checksum、unknown schema、错误 camera/context/pass、错 nested bracket、UNKNOWN 和 decoder exception。unknown/exception/invalid raw/missing 均必须在固定 planned 行中显式可见，numerator 只计 OBSERVED，decoder 调用次数只计有效原件；source 全局 pin 失败则禁止 detector，输出未解码原因。
- [ ] journal 流式校验 record_seq、每个 operation begin/end、每步 CONTROL/ACTUATOR/PHYSICS 顺序、action ownership、743 commands、4807 scorer 和原配方。对同一 record 的 guard/full-state即读即验证并释放，保留紧凑 step identity/digest；必要跨段可用新 offline 临时索引（本目录，readout 内），不可把完整 camera guard 字典存入 4807 元素列表。旧、新 journal 顺序读取；对未知事件、未闭合 pair、truncated gzip 均记录错误并拒绝 VERIFIED。
- [ ] 全量 raw manifest 逐项核对 canonical 路径、实际文件集合、bytes、compressed SHA、原 JSON SHA、RGB/depth/mask member SHA、RGBD schema+checksum；逐帧解压/检测/释放，不批量展开约 10 GB JSON。frame→index→journal→callback→physical→terminal→header 一一绑定；每帧 37/33/0/9 状态及 final guard 全量复核。
- [ ] 只一次调用原 `detect_pose_marker(observation, frozen_registration)` 于每个有效新帧。保存完整估计、ordered corners/min-side、原因、原件 hash、step/SimulationS、action；truth只做离线 physical/scorer/来源关联。unavailable raw 不能调用 decoder，不给 UNKNOWN 编造角点/pose。异常原件保留并处理后续有效 frames；不可见帧也保留，无 decode 重试。
- [ ] old baseline 用既有 R01 4807 `offline-markers.jsonl`，先要求 old IDs exact0..4806 且每行来源 SHA 对应旧 raw manifest，old 原件 SHA 分块只读核对，不重新 decode。new 全部 4807行严格配对；旧4618 OBS/189UNKNOWN、新 counts、全部 transitions、缺失和新增 UNKNOWN 区段完整报告。原201另列固定子组，不把它替代完整比较。
- [ ] 完整 old/new recorded physical4807、actuator4806、commands743、scorer4807逐字段比较，唯一排除 `episode_id`。必须各自 exact no-missing 后才下比较结论，不做 intersection。记录 mismatch明细；旧full qpos unavailable，不能声称内部全部状态相同，也不能造反事实旧pose。新的 full capture 可能改变轨迹，零差异是待测条件而非从 sparse 推定。
- [ ] 输出三个独立结果：`integrity_status`、`sampling_gap_status`、`full_frame_observability_status`。仅当 exact范围/recipe/guard/source/raw齐全、no failures、全部4807 OBSERVED、每个采样 gap≤0.005且首尾齐全，后者才为 `PASS_THIS_FULL_HORIZON`。同时报告 OBSERVED 相邻最大 gap与UNKNOWN连续段；全帧时可测 coverage=1，但不升级连续物理证明。所有时间门使用 SimulationS；wall/RSS 单独字段。
- [ ] before/after 分块 hash：全部新 attempt 原件、所用旧完整 raw manifest 全成员、sparse manifest/报告及被引用源档案/元数据，报告 added/missing/changed 各为0；新 actual 输出本身单列预期创建。没有完整旧原件就报告 comparative lineage unavailable，并停止通过判定，不以 manifest 声称已重新读 raw。
- [ ] streaming CPU fixture 用含 sentinel 的迭代器证明只保持有界条目，拒绝大于8MiB帧/16MiB条目和 truncation，spy forbidden read-all/renderer/model/decoder truth input。CPU仅小 schema fixtures和4807整数元数据循环，不重播旧201/4807，不重复大审计。

## Task 4 — 一次独审、一次 actual、一次新 full 读出

**Files:** 新 `F/implementation/independent-review.md/json/log`、`F/actual/*`、`F/full-protocol/attempt-1/*`、`F/offline/*`；root 负责串行执行。

- [ ] 作者完成四 owned 源，记录 delta范围和 RED→GREEN。冻结新 full 协议及 reader，然后独立 reviewer 检查 exact pins、source-load顺序、range三个终态、failure保全、最终guard、streaming/SimulationS、原件隔离、资源与 CLI；独立仅跑新 owned bounded suite一次及四源窄static。不重跑旧40/90/342、不执行 actual/decoder、不对旧raw再次全面审计。
- [ ] review只可给 `PASS_SCOPED_SOFTWARE_READY_FOR_ONE_FULL_ATTEMPT`，不得给 actual/readout PASS。预定 missing-behavior TDD RED 是实施证据；除此之外任一新 finding/意外 RED 必须 `REQUEST_NEXT_ASTRA_PLAN`，保存原件/具体反例，停止该切片，不在本轮临时修到绿。修订后新冻结目录如何命名由下一Astra决定。
- [ ] root核对 review/plan/header/source/env SHA与资源、无并行 renderer、attempt-1 不存在。实际命令使用 `/usr/bin/time -v` 分开记录 GNU全过程wall/RSS及程序内部wall，PYTHONDONTWRITEBYTECODE=1、PYTHONPATH=src:.，`.venv/bin/python F/run_full_once.py --execute-once --protocol-directory F/full-protocol`。supervisor依 header 3600s 上限触发 SIGTERM，最多60s清理后强制终止；保留 supervisor 超限原件且不 retry。不要把 notebook/本规划执行当作 actual。
- [ ] actual唯一 attempt；必须终态退出且 raw 只读 inventory完成后才执行 reader。即使 actual partial，可运行一次只读保全/失败读出，但不标完整通过或补采。reader 使用单独 `/usr/bin/time -v`，1800s 操作上限，同一输出目录 create-exclusive、无 resume/第二次 decode。actual 与 reader 串行，网络/provider/hardware调用0。
- [ ] post-terminal独审读取新4807派生行/实际源 pin/错误清单及资源和before/after，不再执行第二轮decoder；核对所有 counts/分母/范围/时间门与没有权限升级。报告区分软件CPU次数、actual1、作者decoder真实次数、独审decoder0，不相加同一suite。
- [ ] 如通过，仅报告本次 development full marker frame observability；如有UNKNOWN、range/trace差异、资源超限、pin/guard/raw缺陷或不能比较，保留全部源/日志/失败，明确下一轮 Astra问题与原件路径。禁止擅自调marker、改阈值、缩分母、重试、补校准组、推进formal/native。

## 资源依据与验收边界

旧 V3 采集实测915.764513714 s；4829 raw文件519937924 B（约519.9 MB）；frame JSON解压总量10091460121 B（约10.09 GB）。sparse reader实测41.75 s/2389828 KiB（约2.28 GiB）；201frame JSON421564947 B，compressed16790554 B。这些是历史测量，不是本次 wall/RSS 上界。简单按frame数量缩放 sparse wall约998 s仅供预算，不据此承诺读出期限；guard journal规模变化必须用流式算法控制。full reader不应复制 sparse `read_journal()` 的全量list，更不应批量载入新旧两份 journal。

操作资源不足时在 model构造前拒绝；运行中超预算保留PARTIAL。4GiB/RAM和wall参数不构成Rcap、未来稳定性或研究证据的耗时界。相机 calls成功预期4807额外 +1setup +1bootstrap +10boundary=4819，按原两/三pass结构估计 render passes9649；两者分开，未测实际render总数保持null，不能将估计列作实测。

完整性与可见性允许分开失败：若4807原件全部验真但仍有UNKNOWN，integrity可VERIFIED而observability失败；若采样gap合格而缺姿态，不能通过姿态可观测。即使本次4807全OBSERVED，也不能从离散帧推导角速度或两帧之间全程姿态。至少9独立支持组/连续界/UTC与operational时间消费者/正式域仍由其他已定队列推进。

## 本轮交付与自审

本轮只新建本目录plan.md/json；固定输入实际SHA记录于JSON，没有重新哈希全部旧raw或重新执行其测试/解码。34当前sparse live source与原execution manifest全部匹配，仅作为本轮读取时事实；未来freeze/actual仍必须重新检查必要pin。计划覆盖固定range、完整分母、原件和失败保留、source/model/env/schema、final guard、逐帧strict detector、资源、UTC独立、full旧新比较和下一Astra停止门。所有任务仍NOT_STARTED，尚无新full协议、actual或full观测结论。Stage56提交由root独占，本计划不触碰其交付输入。
