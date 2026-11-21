# Phase 6 首组正式仿真与读回计划

gpt-6.2-astra · 2026-11-22 · 基线 `6a26ac812f1c215c35031a80e3848252ce3c52e7` · 研发分支 `research/harness-candidate-v10-phase2-20261121`。

本次只授权 `native-p0-v10-20261121-0001`（seed 11921001）一次正式仿真。先在隔离进程取得同场景单帧；通过后，以既有登记执行。指定正式输出为 `experiments/results/phase-v10-formal-20261122/`。本轮不修改产品、算法、冻结协议或清单。

## 原始证据与要验证的假设

- Phase 5 的正式入口工厂只在隔离登记副本到达 QUEUED，0 次尝试、0 个租约、0 次正式仿真。权威登记现仅有 80,136 字节 protocol.json，研究工作树没有 experiments/results 或本轮既有目录，HEAD 与本地上游均为基线。最新中断信号要求执行者重新检查运行进程及状态。
- Phase 4 的冻结 v9 首组只有一个动作和两条准入，PRE ALLOW、POST STOP、Shield STEP_TIMEOUT；冻结正式资格 0/9。两份协议各自独立，匹配该正式原件的协议 SHA 以 6ac30e90 开头；16,885 项 inventory 由 Phase 4 核对。用户工作树的未跟踪检查清单对冻结 v9 的完整性、协议对应关系及相机/标记描述有误，保留原字节。
- 待验证假设为当前 EGL 主机能在注册的正上方 rgbd 相机、r593 场景及首组初始条件下测得 ID 7，并能按冻结 v10 物理步截止运行、采集和离线重建。软件轨迹、GLContext 成功和 Phase 5 的空登记读回均未实测这些结果。

登记文件 SHA256 `da431fdb96f8b2672fb621d4ca4c87b673835f26ce874c7ce03da8fb043a7972`，canonical SHA256 `bca768e63e0e7a1fa5d4e4c1b0ca322f64eb8cd1c5c66fa126758942e8036a91`，456 项 source_generation `186e76435e7dc470175190622e4f3658eaaad4298e6fab214e08110d0e9112b0`。逐文件输入与三项历史冻结指纹、角色/预算、逐动作窗口见 [机器可读计划](plan.json)。

## 恢复检查与冻结复核

- [ ] 在指定研发工作树根执行。借用相邻 worktree 的解释器，设置 PYTHONPATH=src:.、PYTHONDONTWRITEBYTECODE=1、MUJOCO_GL=egl。核对模块 __file__、平台、Python/MuJoCo/OpenCV ArUco/NumPy/Pillow、Renderer/EGL 与可用空间。已有 MuJoCo 3.3.7、EGL llvmpipe GLContext 和约 130 GiB 空间记录，只作为进场依据。字体、相机位置、渲染后端和噪声保持既定设置。核对普通用户可创建输出、OC1 单调时钟、SQLite、worker/租约/guard/急停及 Phase 5 的同版排队证据。使用受限本地仿真环境，关闭外部模型、网络服务、硬件端点。
- [ ] 只读检查真实主机任务/子进程、现有 claim、作业存储和指定输出（包含悬空链接），保留时间与已有进展。若已运行，监控原进程；若已结束/中断，先按原 claim 和输出重建，仅执行读回与封存。已有痕迹但状态不明时停止启动。保留所有文件，不清理、不改名再启动、不建登记副本以取得第二次机会。
- [ ] 验证完整 HEAD、上游及登记文件 SHA、canonical digest、source_generation 和 release_reference.source_generation。以当前 read_protocol、_check_protocol_sources 和独立的 456 项重新枚举、SHA256/Git baseline blob 逐项比对覆盖资产及源码，另核 v10 release YAML 和清单外的公开源输入。确认没有词法链接或未登记替换。复核两份冻结 v9 协议与 inventory SHA，确保阶段报告使用匹配原件的一份。用户清单仅读。
- [ ] 检验全部九个 ID 和 seed 11921001…11921009，0001 单独 RELEASED，与 released_assignments、settings.released_assignment 完全一致，0002…0009 为 PREASSIGNED_NOT_RUN。正式输出必须不存在且父链无符号链接；指定运行根本身留给正式 CLI 创建。用独立、持久、本地忽略目录如 cache/phase6-20261122/<unique> 存日志和预检产物，避免向正式输出预写。

## 隔离单帧放行门

- [ ] 独立进程用当前 worker 的 SimulatorConfig(render_rgb=True,render_depth=True,physics_dt_s=1/240,seed=11921001,model_path=protocol["settings"]["model_path"],domain_randomization=False)，核对默认 camera_width=320、camera_height=240、model_path、grasp_profile/原件哈希；MuJoCoPhysicsBackend.initialize(config)，用 matches_calibrated_gripper(model, settings["grasp_profile"]) 复核。唯一场景为 PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC",seed=11921001)。禁止 app/worker/prepare_once/租约、登记副本/claim、教师采集、动作派发、模型和硬件。
- [ ] 以同一后端的 sensor_capture_on_demand() 包住 reset(scenario) 和 step(120)，不显式 capture。正常退出上下文只生成一个缓存同步 RGB-D 对，随后 get_sensor_frame() 只读缓存，在 finally 中 shutdown()。reset 和 step 自带刷新，以上上下文统一抑制，正常退出才真实采集。可用只读 Python 调用计数器监测 MuJoCoRGBDCamera._capture 的真实函数体，记录一次 acquisition、RGB/depth 两次 render、零 segmentation、零动作，无须替换方法。核 total_physics_steps=120、sim_time 约 0.5s；记录隔离实际编译/重置/物理/渲染支出，可与正式预算分开。该样本不复现正式每步渲染的深度噪声随机流；实际正式采集是独立证据。
- [ ] 将帧以 observation_from_sensor_frame(frame,source="mujoco_camera") 序列化，并从私有文件 model_validate 读回。核 230400 RGB 字节、76800 个 depth 值及 76800 字节二值 validity；有效像素非零、有限且为正，mask 与 depth 对应，失效深度为零。比对 PNG 解码 RGB、<f4 depth 与 mask、checksum、scene/episode/frame_id、采集时间、相机内参/外参及 calibration_version=f33940579c533afe（协议 geometry.camera）。
- [ ] 将同一读回 observation 与 NativeGeometryRegistration(protocol["geometry"]).pose_marker 传入 detect_pose_marker(...,corner_refinement="SUBPIX",diagnostics=...)，匹配 v10 bootstrap 的 region_policy。核 DICT_4X4_50、marker_size_m=0.075、侧向 r593 资产、status=OBSERVED、唯一 observed_marker_ids=(7,)、registration_hash 与 observation checksum、四角/5 个深度窗/尺寸及平面校验，并记录 reason、最短边与 residual。不得使用实例掩膜/真值替代检测，不改阈值重拍。检查正式 claim/输出仍无痕迹。任一门失败保留日志和样本，正式消费 0，向 Astra 请求新轮次。

## 单次正式启动与监督

- [ ] 仅在上述门全部通过、工作树/协议/余量及未消费状态即时复检后，由一个监督进程执行 formal_command 一次。用户已提供本组一次授权。向现存 Phase 5 权威 registration 目录执行；由同一 CLI 内置 prepare_once 排他写 claims/0001 的完整 assignment 文件并创建作业、取得一次租约。不得预调用 prepare_once、复制/准备新协议或重试。输出根为正式 CLI 的 --output，stdout/stderr、进程标识和退出码放私有兄弟目录。
- [ ] 维持原 Guard、OC1 截止、SQLite 身份与租约、SafetyShield PRE/POST/TERMINAL、真实模拟状态与急停、严格来源及原始采集。控制器相对派发物理步计时，墙钟为步骤诊断，独立任务总期限 1800 s。先确认磁盘余量至少 32 GiB、RSS 上限 8 GiB、原件 16 GiB、guard 500000、max_attempts=1，全部角色及资源上限见 JSON；不得扩大配额或禁用安全机制。8 个窗口及 settle 合计 12960 步，8 动作各自允等号。禁止额外组、模型请求/载入/生成、paid 和硬件。
- [ ] 记录同一 PID/进程组和 UTC/单调起止；约每 30–60 秒只读观察存活、RSS、磁盘余量、输出大小与 raw 增量，避免反复遍历所有帧。关键变化给出进展。不可另起 worker 或刷新租约。留足运行/清理时间；已有运行交给现有代码执行终止、急停和资源释放，发生安全/预算越界依现有停止机制处置并保留现状。中断后优先重新连接原进程，不据短暂静默推断死亡。非零退出码、缺 receipt、仅输出无 claim、claim 后失败均保留，禁止第二次启动。
- [ ] 记录 startup、collection-body-result.json、最终 collection-result.json、runtime.db 终态、owner_closure、worker_snapshot、attempt/lease、source_generation、physics/render/controller/teacher 数量及 raw bytes/RSS/guard。优先引用实际原计数，记 EXACT/LOWER_BOUND/UNAVAILABLE、部分执行/未发生的区别。记动作尝试、派发、返回、已完成计数；原始失败顺序与清理错误分列。

## 冻结后离线核对和交付

- [ ] 进程终止后先冻结产物状态。校验 inventory 中每个相对普通文件的字节数、SHA256、无逃逸/链接，记录缺失、额外、重复、不可读；核登记字节和全部 frozen v9 摘要前后一致、claim 恰一份且 assignment/application_id/output/protocol canonical SHA 与 startup 对应。全量 raw、日志/命令、私有本地清单、运行数据库及 claim 原位保留；对 SQLite 的分析采用只读一致性快照/只读访问，含现存 WAL sidecars。不得修改原始条目以通过检查。
- [ ] 正式 --verify 使用 verify_command，写全新私有读取目录。另用 read_native_full_horizon_group(registration,assignment_id=FIRST,root=output)、reconstruct_native_full_horizon_registry(registration,roots={FIRST:output},group_sink=...) 对照 CLI 的 groups.json、diagnostics.json。使用调用者指定的原 authoritative root 和同一来源；完整验证可能消耗显著墙钟和内存，串行执行并监测。保留三个入口的结果或原异常、每组 issue/reason、source/horizon/geometry/lifecycle、实际动作/帧和未知量。若原件缺失，报告缺项、可读边界及 null，不补造。其余八组必须 NOT_RUN。
- [ ] 用原动作边界与回执和原动作 PRE/POST/TERMINAL、Shield/tracker 时钟核对在线与离线。可按可得原件只读重算前缀，区分记录字段比对和真正重算。核 assignment/source/original_plan、step/skill、frame/observation/feedback 校验和、版本、绑定、各时钟域、租约更新、Shield 全量上下文/决策/原因及 controller deadline 与 terminal 相对 dispatch；有 TERMINAL 才查末 POST 复用。仅报告具备原证据的部分。完整路径要求 8 动作与全体边界，17 准入、16 次独立 Shield、27 条 tracker 时钟仅在真实完整轨迹才比较。冻结 v9 的 1 动作/2 准入与 Phase 4 保持独立。
- [ ] 分别报告进程结局、采集完整性、离线重算和正式研究资格；CLI 固定 native_qualification=UNKNOWN，登记总分母 9。单一 teacher 尝试即使完整也只能列出实际 group_score/qualified_group_score 与诊断，不推为整组资格、联合界或硬件证明。部分失败/偏差记真实输出及阻断原因。新根因、范围扩大或计划外失败须由 gpt-6.2-astra 先出下一轮修复计划；独立只读核验和阶段交付继续。
- [ ] 仅将本轮 plan.{md,json}、验证汇总 validation.public.json、step-report.public.md、stage-summary.public.md 和确有必要的脱敏派生证据逐个 stage；原 claim 含绝对输出路径，留在本机，不 stage，公开材料可列其 SHA/相对位置。现存未跟踪用户清单保持原样；只发布摘要/指纹，完整 raw、DB、绝对主机日志、SDK、凭据、权重和图像未上 Git。验证计划输入、冻结原件、本轮文件可读性、git diff --cached --check、暂存路径。提交并推送 research/harness-candidate-v10-phase2-20261121，在最终回执核对 HEAD、上游及 ls-remote 三个完整 SHA，明确本地原件交付边界。

## 执行命令

在研发工作树根运行。正式调用前完成前两道门。

```bash
MUJOCO_GL=egl PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. ../harness-candidate-20261118/.venv/bin/python -u scripts/collect_native_calibration.py --collect-once --protocol artifacts/research/process/20261004-ced-development/astra-rounds/round-v10-phase5-20261122/registration --assignment-id native-p0-v10-20261121-0001 --output experiments/results/phase-v10-formal-20261122
```

读回目录所在的 PRIVATE 指向本轮独立私有证据目录，verified-registry 子目录在运行前应不存在。

```bash
MUJOCO_GL=egl PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. ../harness-candidate-20261118/.venv/bin/python scripts/collect_native_calibration.py --verify --protocol artifacts/research/process/20261004-ced-development/astra-rounds/round-v10-phase5-20261122/registration --output "$PRIVATE/verified-registry"
```
