# 单候选回归与三次 MuJoCo 开发试次的原件诊断方案

> 执行者按已授权分工采用 GPT-6.2 Sol 和项目测试先行流程；方案由本轮指定的 GPT-6.2 Astra 制定。完成时保存原失败、每步结果与阶段总结。

**目标**　在同一候选上对齐 11 月 17 日 Harness 计划与 18 日实现。交付能读取真实归档并复算三个视觉判断的软件、正反例、安装与回归回执，并据实判定动作资格及 B0 入口。

**架构**　只读实验脚本从原清单校验输入，用候选的生产视觉函数重建并解释当前帧判断。软件、协议回放、历史真实模型与正式资格各用自身的分母及来源。工具不接入运行控制链。技术依赖为 Python、OpenCV、NumPy、RGBDObservation、pytest 及原 wheel 工具链。

**依据**　候选的 `docs/plan.md`、11 月 8 日工作包路线、11 月 18 日真实模型方案和 `artifacts/research/process/20261118-real-model-harness/`。本地输入指纹见同目录 `input-manifest.json`（141 条，SHA256 `6c0305c48fd50ed945662935b0f0e6744f3a219bad3754a66d2a28a5cfdba96e`）。包含候选源码、历史分母、三个失败和 44102 对照、原帧四件套、运行清单及旧 wheel。归档根可按相同字节迁移。

## 冻结基点与已有失败

合并候选 `3ca2f6415b330d38ddc2d834c5f788a56c0d9517`，tree `9733f48fad24e368004aeafd5592109c96b0355b`。父提交分别是 11 月 18 日实现 `3dd6669d8b079e94aba30b97d6a0427370ecd3bd` 和 11 月 17 日计划 `de982ad3d2b11782aac803ecddc33ed776ae6775`。保留原主目录未提交工作。实际运行由早于候选的三组字节产生；44101 属 pre-camera-binding，44102/103/104 属 post-camera-binding。不得把候选上的离线复算冒充原程序重新运行。

| 原试次 | 已核实的拒绝位置 | 本轮可证伪的解释 |
| --- | --- | --- |
| 44101 | 持物 MOVE_TO_REGION，step-05/sample-0100 为已接受参考，0101 主视角及 view-01、view-02 均为 17.49999999999933 s 的不同原帧，控制器最终返回 region_current_corner_anchors_insufficient | 两个备选已被实际取样。逐视角复算标记与区域的先后条件、三个当前角点要求，记录首个失败谓词；不能推定三个视角都以同一原因拒绝，也不能从没有的第三备选推断可恢复性。|
| 44103 | 已释放并稳定 7.508333 s；横向 RETREAT step-08/sample-0021 接受，0022（30.929166666665232 s）因 marker_depth_not_planar 停止，此时没有同刻备选归档 | 复算已登记标记的四角/中心深度及拟合平面偏差，区分中心与角点是否超过 0.002 m；前帧作对照。正确拒绝和物理放置成功可以同时成立。|
| 44104 | before 绑定的两次原回答均为 POINT，(515,817)/(405,298)，像素 (164,196)/(129,71)。planning-stage-01 为 REQUEST_MORE_OBSERVATION，原因为 initial RGB-D identity/extent unavailable: target_depth_incomplete；0 云、0 动作 | 该字符串由 tracker 的共享深度检查返回，须区分哪个选中实体的掩码中有无效/非正/非有限深度。压力条件标签不证明遮挡成因；几何拒绝也不能归为模型 ABSENT。|

动作资格的独立证据取自 R595 的 phase-summary.md。唯一获释的教师试次归档 3,389 帧，独立 reader 完成读回，合格 0/9、准入动作 0/8，九项分数和联合界均为 null；运动后的颜色身份与原 8 秒墙钟均未通过。资格审计须查后继是否实际释放新组及结果，继续区分局部软件修复与合格教师原件。

固定修后 2/2，含旧失败 2/3；新 seed 1/4 完整、2/4 独立物理成功；原七例 6 云、26 本地生成、费用未知。44102 是跨 seed 正对照，另用两个失败前的连续成功帧。实验原件来源包括 `native/varied-*/{result.json,component/episode.json,planning/planning-stage-01.json,evidence-manifest.json}`，逐项哈希以清单为准。

## 1. 实施前置与并行边界

- [ ] 确认 HEAD 等于基点或为仅增加方案、证据和计划同步的后继，`git diff --exit-code 3dd6669d HEAD -- src tests configs pyproject.toml` 在产品修改前通过。按清单的 root/path 逐项重算大小和 SHA256；不匹配时保留证据交 Astra，暂停依赖该输入的工作。使用选定候选的 Python 导入位置；实验证据、SDK、模型、凭据保留原地。每轮新输出目录必须位于旧归档以外。
- [ ] 可以独立进行全库用例收集、路径/依赖准入、计划日期与实际交付对齐，及以历史 `verify_native.py --raw-root <旧 real-harness 根> --output <新文件>` 对七例复算。回放和 wheel 依赖实现后最终冻结。共享渲染/GPU 与敏感的 100ms、600s 时限测试独占执行；不要用并发制造时限异常。
- [ ] 角色和动作边界按现行配置。保留 Molmo2-ER、研究云 gpt-6.1-sol、OpenCV、当前可见标记、已登记的相机和控制器、SafetyShield。固定两备选/同一物理步、RGB-D/外参/帧 ID 绑定、100 ms、2 mm、至少三个当前角点以及横退拒绝条件。本轮 0 次新真实模型加载/生成/云请求，0 真机；原费用和额度不因合并、回放或历史未耗尽而新增授权。
- [ ] 在 `docs/plan.md` 的现行摘要加日期和证据链接，区分 H0/H1 软件安装、已观察正常链、开发泛化和待验动作资格。对齐原计划与阶段总结即可，保留历史章、原协议、未提交原稿及暂缓公开推送裁定。

## 2. 可交付实现与预期 RED

- [ ] 新建 `scripts/diagnose_native_harness_stops.py` 和 `tests/test_native_harness_stop_diagnostics.py`。提供 `--archive-root <real-harness-20261118> --input-manifest <本轮清单> --output <新 JSON>`，用 Python 从候选仓加载。输入为四个登记试次及各自受信清单。输出列清 seed、原来源组、观察 ID/校验和、原记录与候选复算、逐视角/实体数值、已接受对照、worker/物理结果及未知项；绝不改写 raw、读取凭据或发出动作。避免复制控制器或重造分类器。允许为取得生产判据精确数值在对应视觉函数局部提取纯测量 helper，或新增可选诊断收集器；生产默认入口、判断顺序/数值和所有返回语义须字节级数值等价。不需要修改默认路径时保留其代码。
- [ ] 先写焦点测试并保存缺少新工具/接口的预期 RED。最少覆盖有效绑定、配对字节被改、跨帧/跨 episode 或错误标定绑定、已存在输出或位于源目录的输出。损坏小型临时副本，不触碰原件。证明测试实际调用生产判断，改动期望值应能让测试失败。实际归档正反例依赖路径可显式传入；默认无 raw 的单测使用小型可公开 fixture；正式本轮验证必须提供原件。
- [ ] 复用 `sol_molmo_offline_regression.load_observation` 的四件套重建与 `FrozenCase` 的逐文件校验模式。校验 archive 索引 SHA、被消费文件 SHA、RGB/深度/有效掩码与原 observation checksum、生产内外参摘要；绑定 episode/场景/帧 ID/标定/同物理时刻。可以从项目原数据读取原生模型回答与正确规划阶段来初始化追踪。不得依赖实例分割、模拟真值或历史派生的 PASS 标签做视觉判断。历史归档只做静态测量，不能修改生产时钟或把历史帧作为当前可执行命令。
- [ ] 44101 用 `component/frames/post-cloud` 和同回合生产规划 binding 初始化 OpenCVTargetTracker，依据 `servo.py` 顺序复算标记与 `measure_servo_region`。记录每个可测视角的实际角点支持数及其它先决失败；未到达步骤写明。0100 及 44102 的对应成功帧作正例。实际过门必须来自本视角；重复帧、变更时间或不匹配校验值应失败。
- [ ] 44103 用与 `OpenCVServoFeedback._marker_grasp` 完全相同的 family、refinement 和验证优先顺序，列出具体 registration（含真实选择的面）、中心及最大角点正交残差(m)，呈现原先共面失败与上一帧成功的差异。若多个注册面参与，记录各面的原判断与最终选择。保持 0022 拒绝。不存在的同刻正例不得补报。
- [ ] 44104 绑定原 prompt/回答/图像哈希，用已归档的正确点位重走 OpenCV 初始化，分开记录对目标、目的地的已执行检查和拒绝；数出导致失败的选中掩码深度无效像素，区分 valid_mask、有限值、深度正值并说明计数重叠。若某实体因先前拒绝未曾运行，独立离线测量须明确区分。44102 的 before 作为同入口有效对照，比较几何是否可用，不以首个规划文件 outcome 直接定义成功。
- [ ] 每项输出独立区分原拒绝、候选复算和可证实根因。不一致要保留并依照候选/原运行 SHA 判断版本漂移或新问题；不能预设要变绿。只有证据表明可在原门限和授权动作阶段改善观察时，才将**单个**已证实成因连同失败及成功帧提交下一实际 Astra 方案。三个失败各自保留结果；本轮不扩横退重观测、不补第三视角、不填深度。

## 3. 单候选最终验证与验收

- [ ] 首先运行 `python -m pytest -q tests/test_native_harness_stop_diagnostics.py tests/test_servo_region_support.py tests/test_servo_camera_framing.py tests/test_pose_marker_evidence.py tests/test_embodied_harness.py`。使用新增 CLI 在四个真实归档上离线复算，要求三类终态、已有正对照、测量数值及来源可独立检查。输入指纹不变；如已授权改动某个被钉住的候选源码，应将它列入 pre/post 差异，不得将已计划源码变更误判为原件失真。
- [ ] 记录候选最终代码 tree 或受控完整源码清单，执行 `python -m pytest --collect-only -q` 并在同一代码上按项目既有 CPU/EGL/专用运行时分区完成收集到的测试。先验核对分区覆盖每个 nodeid，每组记环境、命令、起止时间、退出码、JUnit 及 skip 原因。默认不开放真实付费/真机的 opt-in；有原始数据、正常准入且无需付费的节点实际运行，其他阻塞单列。超时节点保留原限，原 600 s UTC 两节点应在同一 pytest 调用中顺序执行；原 `fixed-01` 协议重放在真实原件与独占渲染就绪时使用原有哈希和网络/模型禁用守卫。不要把工具自己的小回归计作全库。
- [ ] 在最终同源码候选通过现有构建入口 `python -m pip wheel --no-deps --no-build-isolation . -w <新 dist>`，记录 wheel SHA、来源文件与 wheel 内 Python/JSON 一致性，在仓外清洁 venv 从受信本地依赖安装，清除 PYTHONPATH 和凭据，核对导入位置、pip check 以及 `bigsmall-harness` 的 --help、--version、validate、doctor、doctor --source-checkout、prepare --source-checkout --output、evidence。旧 wheel 仅作历史参照。最终报告将绿色、失败、环境阻塞各自列清。
- [ ] 按现行路线逐条查阅最新证据，记录实际组 ID/来源、独立 reader、九组与联合界、三处 native 消费与 Memory/SQLite 正链、预算与隔离。完整动作资格 P6 A→B→C→P7/P8→D 与受控正常链有各自证据。仅当前置具备，原样进入四周期 0.5/1/2/5 秒、独立 120 个 selection 组的 B0 评估；阈值静态 ≥90%、整体 ≥80%、安全违规 ≤1%。本轮只做资格审计，若仍缺数据，明确首个缺项、证据所有者和原受限入口。基础先导另 120 组及 INITIAL 继续按原顺序，既有 development seed 均不得转入 selection。保留正式 NOT_ACCEPTED、合格新增 0 和实机 NOT_STARTED，直到相应独立原门真正通过。
- [ ] 步骤报告汇入阶段总结，附失败证据、实施差异、可复算命令与新结果路径。本地按明确路径提交，暂缓公开推送。遇新的根因、范围扩大或非预期失败，先保存原始命令与失败并交实际 Astra 另拟方案，独立任务继续。已有依据的正确保护停止也可成为终结论。
