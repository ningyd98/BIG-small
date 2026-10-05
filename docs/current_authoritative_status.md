# Current Authoritative Status

## 2026-10-04 云、边、端持续研发

当前按[ced.research.v2总计划](superpowers/plans/2026-10-04-cloud-edge-device-research-roadmap.md)持续实施，边缘模型型号后置。已独立审查的软件范围包括角色/wire绑定、原生三值条件、T10提交与硬停止、共同基线/模式CAS、规则成本边界、视觉修复候选、stage/activation/start接口、持久恢复及完成/预算消费者、运行组合、Max角色局部修复、T8先导/完整资源冻结补修、INITIAL来源审计、完整分配/统计/复现及只读研究页。实际风险来源、owner登记和方法接入继续实施，不登记整体完成。

尚未记录经独立验收的Max真实调用、native几何/运动界或连续效果证书；JOINT/LOCAL_RECOVER及真实INITIAL/FINAL保持关闭。新100组开发采集与1组教师故障原始来源不能替代完整机会/200组证明。研究页面的4200条软件BLOCKED记录不计物理结果，formal_accepted=false。历史限定DONE与原始失败保持原口径。每步报告和审查见[阶段总结](research/process/continuation_20261004.md)，操作入口见[复现说明](research/reproduction.md)，未满足门见[结果与限制](research/results_and_limits.md)。

用户选择增加可见姿态标记并保留顶视相机与控制器。独立开发v1资产/检测已通过73项CPU及源/原始帧hash独审；同一物理相机的320×240严格识别UNKNOWN，新640×480单帧OBSERVED。第二版本保留原红色边缘，17份源与77项CPU独审通过，新的实际静态帧识别ID7并看到红色边缘；完整目标关联和连续/校准/native证书仍缺，不自动切换默认配置或抓取profile。一次开发搬运的147份产物/完整raw重建独审通过，离线物理评分成功，但全部9个动作后边界标记UNKNOWN，不能以物理成功代替视觉可观测性。

阶段总结已到第51步：源冻结后唯一逐步实测在step10被data数组一致性保护终止，原120步settling未完成；13次camera调用（setup1/bootstrap1/逐步11），10帧保存、1失败、0教师动作，原attempt保留且不重跑。十份成功前缀仅为OBSERVED，不证明完整horizon。动作参照新模块29项及含旧范围的93项CPU通过，root独立29通过；来源/参数/完整时长重建已实现，但无界/VALID/准入。真实日志揭示ACTUATOR登记upcoming步n，原reader n-1误关联另行修正；逐数组诊断准备中。主线T12/18、T13并行，真实Max、基本/连续来源、风险及INITIAL/METHOD/FINAL未验收，边缘型号后置。见[本步报告](../artifacts/research/process/20261004-ced-development/t7b-continuous-visibility/report-step51.md)、[阶段总结](research/process/continuation_20261004.md)与[Git记录](research/process/git_delivery_20261005.md)。

## 2026-10-04 夹爪修复应用到全项目

默认模型工厂、HTTP/WS工作台、Linux启动环境、模型探针、离线评估与smoke/pilot开发配置已统一到 `mujoco_upright_box_v2` 和[当前共享冻结](../artifacts/research/process/20261004-gripper-project-migration/model-probe/model-frozen.json)。沿用已安装的Qwen3-VL 4B Q4_K_M；真实双图探针4/4，冻结来源验真通过。显式active profile及环境选择仍优先，冻结缺失或来源漂移时拒绝规划。API启动和采集不提前加载模型，能力接口在模型解析前标为UNRESOLVED。

默认在线20例全部保留：2成功/18失败、正常2/12、0环境阻塞、2误完成；50,310物理样本独立复算一致，3例硬关节限位违规。实际工作台完成1次模型调用和8动作，语义引用正确绑定v2，但因硬限位违规如实FAILED。以上证明配置迁移与链路可用，在线质量仍未达标，不升级正式G1或T8。大回归702通过，13项来源清单测试夹具修正后的相关52项全部通过；前端30测试及类型、构建、lint通过，独立迁移审查无开放问题。详见[全项目迁移报告](../artifacts/research/process/20261004-gripper-project-migration/acceptance.md)。下文T5及各模型冻结保留原验收时点；当前默认冻结以本条为准。

**整体计划修订（2026-10-04）：** 当前后续开发以[云、边、端总计划](superpowers/plans/2026-10-04-cloud-edge-device-research-roadmap.md)和[ced.research.v2设计](superpowers/specs/2026-10-04-cloud-edge-device-research-design.md)为准。云端Max规划、端侧OpenCV/RGB-D证据补强，边缘型号按用户要求后续调整，近期采用规则/成本provider。新增T3b/T7b为READY；T8a证据/筛选、T8b先导冻结、T12a规则和T12b选型分别登记。该修订只改文档，未切换生产配置、部署OpenCV或运行新模型，不升级既有实验状态。

## 2026-10-04 T5 脚本教师夹爪修复

修复手指闭爪内间隙64mm与60–70mm采样方块不匹配，并将开爪目标保留1mm硬限位余量。当前源码实跑原20例为19成功、1无接触负控正确失败，正常19/19、安全违规0；另预先固定40新随机场景为39成功、1搬运碰撞安全失败，正负控分别成功/失败。两批逐条校验及场景配对审计通过，历史7/20证据原样保留。661项大范围回归及最后87项相关补测通过，独立审查无开放实质问题。

当前资产使用 `mujoco_upright_box_v2`，已有本地Qwen3-VL 4B双图探针4/4的新冻结；旧v1冻结只对应历史资产，不能用于当前源码。实测仅限60–70mm直立方块，未重测T7/T8在线成功率或升级正式G1。详见[完整修复报告](../artifacts/research/process/20261004-t5-gripper-fix/acceptance.md)与[新模型冻结](../artifacts/research/process/20261004-t5-gripper-fix/model-probe/model-frozen.json)。下文各历史条目保持原验收时点。

**2026-10-04 后续研发更新：T17a `DONE`，T8 `IN_PROGRESS`。** [T17a验收](../artifacts/research/process/20261004-t17a-workbench/acceptance.md)包含真实 EGL/Chromium 三条路径；518 项相关回归、定向 Ruff/mypy 和前端检查通过，最后摘要修复另有58项补测通过。T8 v1 全120例仅为诊断；修复后互斥新120例全部结束，5成功、静态4/40，279,482物理样本与1950帧载荷独立复核一致，成本少记/在途均0。当前2秒周期候选未过质量门，初次冻结退出3、没有发布协议。固定机会/恢复证据尚未完成，G1—G5及C1/C2未成立。详见[第二批报告](../artifacts/research/process/20261004-t8-foundation/foundation-v2-assessment.md)与[逐步阶段总结](research/process/continuation_20261004.md)。

本文件记录当前实施状态与历史分支基线；论文、答辩和 README 必须同时说明证据版本与验收范围。

## 2026-10-04 T7 更大视觉模型候选与归一化坐标复测

按用户指定顺序筛选 Qwen3-VL 8B Instruct Q8_0、Llama-3.2-Vision 11B Q5_K_M、InternVL2.5 8B，统一使用 `normalized_1000`；原 T7 已采用此坐标系。Qwen 8B 固定双图探测 4/4 通过，显存足够，无需 Q6_K 回退；原 T7 的20例闭环仍只正常成功2/12，缺失目标误操作1/4。Llama 当前后端架构和双图契约不兼容，未下载完整权重、未测性能；InternVL 原生 BNB INT8 实际运行，但固定定位0/4及开发筛选0/16，未进入独立闭环比较。

冻结另60个新场景、40目标存在/20目标缺失，两Qwen配置共120例全部保留。Qwen3-VL 4B/8B 缺失目标误操作 16/20 与 11/20，正常成功 4/40 与 0/40；定位 P90 10.31/33.52 mm（覆盖 40/40 与 28/40），墙钟 P95 10.64/10.42 秒。 API账单费用均0元/任务，总费用因无机器单价而未测。独立复算226,006物理样本、999帧、349动作，valid=true、errors=[]；包含本轮筛选的2090份历史RGB摘要无重合，配对初始RGB/depth一致。

8B误操作率差值的配对95%区间跨零，且正常成功率和条件定位结果较差，不支持替换默认模型。原4B/8B分别新增3/1例缺失目标误完成，全部扣除成功计数。此为探索性实际部署栈比较，非正式G1；T7仍限原开发DONE，T8/T17a仍READY、T6b仍TODO，生产配置未替换。详见[完整候选报告](../artifacts/research/process/20261004-t7-larger-vlm-candidates/acceptance.md)、[冻结协议](../artifacts/research/process/20261004-t7-larger-vlm-candidates/independent-60/protocol.json)与[物理复核](../artifacts/research/process/20261004-t7-larger-vlm-candidates/independent-validation.json)。

## 2026-10-04 T7 失败复测与独立探索性比较

新增[完整报告](../artifacts/research/process/20261004-t7-retest-comparison/acceptance.md)：原样复跑历史 v2 的20例，逐例状态、失败原因、动作数和模型调用数一致，仍为2成功/18失败；4个目标缺失案例全部执行动作，误操作4/4，不能由0误完成推断0误操作。独立复算有效，覆盖34,288物理样本、154帧、52动作。

冻结60个新场景（40目标存在/20目标缺失），Qwen3-VL 4B与Qwen3.5 4B同场景配对共120例，初始RGB/depth一致、全部保留、无环境阻塞。目标缺失误操作为17/20（85%）与0/20；正常任务成功为6/40（15%）与0/40，全分配为6/60与0/60。定位P90为11.60与32.57 mm，有效覆盖40/40与7/40；端到端墙钟P95为11.64与8.44秒，失败惩罚P95均120秒。本地API费用均0元/任务；用户无机器计费单价，电费与折旧总费用未测。

Qwen3-VL新增1例误完成：缺失紫块请求经重观测后抓放其他颜色方块，在线/物理层成功但语义任务失败。Qwen3.5全部停在规划阶段，0误操作不能解释为可靠任务能力。独立重放136,673物理样本、781帧、212动作，定位/分母/配对与来源审计valid=true、errors=[]。此为原开发分布的新独立探索集，不是正式G1；两候选均不满足G1任务门槛，不形成成本收益结论。T7仅保持原开发DONE，T8/T17a仍READY、T6b仍TODO；模型、控制器、阈值和历史证据均未改动。

## 2026-10-04 T7 在线视觉闭环开发验收

T1/T2/T3/T6a/T4/T5 保持各自限定范围的 `DONE`；T7 当前为 **`DONE`**，最终 runtime 竞态、证据发布修复与454项回归已通过。T8、T17a 为 `READY`，T6b 仍为 `TODO`，最终质量门已关闭，后续任务尚未实施。本地日期已为 2026-10-04，过程证据仍保存在 [20261003-t7-visual-closed-loop](../artifacts/research/process/20261003-t7-visual-closed-loop/)；最终汇总见该目录已发布的 `acceptance.md`。

已实现相机/动作共享 backend 与 episode、动作后新帧、PASS/FAIL/UNKNOWN 条件验证、SafetyShield 前后检查、有界模型请求及验证预算、三种执行 scope 和独立 DATASET_GENERATION 作业。默认仍为 RGBD/VISUAL_PLANNING，采集、规划和数据生产均不声明物理任务成功。HTTP/WS 共用模型工厂，研究运行使用独立空 profile 数据库；具体使用和范围见 [RGB-D 闭环说明](rgbd_visual_closed_loop.md)。

`smoke-20-v2` 与 v1 使用相同的 20 个预分配场景，全部保留：2 个正常场景成功、18 失败、0 blocked、0 false completion；正常层为 2/12，全分配成功率为 2/20（10%）。[独立复算](../artifacts/research/process/20261003-t7-visual-closed-loop/smoke-20-v2-validation.json)核对 34,353 个物理样本、154 帧、52 个动作，返回 `valid=true, accepted=true, errors=[]`，开发 smoke gate 通过。该结果限当前 MuJoCo 资产、直立有色方块，**不是正式 G1 验收**。v1 全 20 失败及其 34 份源码快照、22,147 样本、105 帧、33 动作完整保留，[v1 复算](../artifacts/research/process/20261003-t7-visual-closed-loop/smoke-20-v1-validation.json)为 `valid=true, accepted=false`；diagnostic-03 已取得在线与独立物理成功。

T7 在新 [model-probe](../artifacts/research/process/20261003-t7-visual-closed-loop/model-probe/) 目录重新执行真实双图探针 4/4 并冻结。共享 `vision/capture.py` 的合法更新使历史 T3/T5 来源绑定与当前源码不同，旧冻结包只代表原验收时点，不能作为现行源码冻结。T5 历史 12 份来源已按 [preservation 清单](../artifacts/research/process/20261003-t7-visual-closed-loop/t5-prerequisite-preservation.json)归档，其中另外 11 份源码及物理判据未变；历史数据和验收未被覆写。

95 项 runtime 回归、277 项前置回归是阶段证据，不是最终总数或最终质量门。真实一组数据作业已 COMPLETE/SUCCEEDED、0 模型调用、`task_success=false`；源码审查和运行终态检查已通过。T6b 的 10000 组未运行，无新正式研究结论，未连接或驱动真实硬件，未 commit/push。以下条目保留各自历史验收时点。

## 2026-10-03 本地 Ollama 与 Qwen3.5-4B

按用户优先要求，Ollama 0.35.1 与 `qwen3.5:4b` 已完成本机部署。魔搭 Q4_K_M 语言权重和 F16 视觉投影通过固定 revision、大小与 SHA-256 校验后导入；安装包与官方发布摘要一致，全部大文件通过 `enp7s0` 物理网卡大陆直连下载。服务重启后，中文文本、VINS 真实 RGB 图片、OpenAI 兼容接口和 NVIDIA GPU 推理检查均通过，状态为 `LOCAL_OLLAMA_QWEN35_TEXT_VISION_ACCEPTED`。API 仅监听 `127.0.0.1:11434`，关闭云端功能，用户登录后自动启动。见[部署说明](local_ollama_qwen35.md)与[实际验收](../artifacts/research/process/20261003-ollama-qwen35/acceptance.json)。该单图部署检查不替代 T3 的 RGB-D 规划验收；当前 T3 已另用 Qwen3-VL 4B 完成限定验收，以下历史 Phase 11.2 / Phase 13 结果保留原口径。

## 2026-10-03 T3 小模型优化与限定验收

T3 为 `DONE`，限当前资产、5–10 cm 高竖直刚性方块的真实双图空间规划。复用已安装的 `qwen3-vl-candidate:4b-instruct` Q4_K_M，改用显式 `normalized_1000` 坐标协议，提示中写明 JSON schema 与完整技能顺序，并从米制深度估计顶面、支撑面及已标定夹具的 TCP 偏移；通用来源和未配置资产默认拒绝该标定。未训练权重、未下载新模型。固定 S01 的1冷3热请求均通过双图传输、严格契约、目标/目的实例命中及几何门槛（4/4）；RTX 4070 Ti SUPER 实测冷请求3857.666 ms，热P50/P95为1483.330/1516.045 ms，设备显存采样峰值5740 MiB，非流式TTFT未测。

已发布[模型快照](../artifacts/research/process/20261003-t3-small-model-optimization/probe/model-frozen.json)及绑定实际请求、有效参数、源码/资产SHA的 sidecar，只读 `--verify-frozen` 通过。额外独立开发场景保留固定分母和拒答失败，精确计数、原始记录及复现命令见[优化验收](../artifacts/research/process/20261003-t3-small-model-optimization/acceptance.md)。模型曾高置信误认机械臂部件，实际被深度门禁拦截且零动作步骤；不能宣称模型完全可靠拒答、对象中心精度、G1或在线抓放成功。T3 验收时 T7 为 `READY`；2026-10-04 已完成限定开发验收并为 `DONE`，当前新冻结包与闭环验收见上文，T8为 `READY`、T6b仍为 `TODO`。

此前失败记录保留如下，属于优化前快照：

T3 软件路径已有双图消息、严格结构解析、缩放像素到米制深度映射、模型配置快照与错误几何阻断；相关 62 项合并回归及定向 Ruff/mypy 通过。真实 `qwen3.5:4b` 在固定 320×240 同步 MuJoCo 帧上 4/4 次完成双图 GPU 请求和严格解析，但红方块目标、绿色目的区域均为 0/4 像素命中；一次原生 640×480 诊断也双双未命中。冷请求约 4401 ms、3 次热请求 P50 约 1257 ms/P95 约 1271 ms；非流式 TTFT 未测。另从魔搭官方固定 revision 经 `enp7s0` 直连下载并 SHA-256 校验 Qwen3-VL 4B 两份 GGUF，导入为独立候选；4 次双图请求均返回合法 JSON，但完整技能契约及目标/目的像素命中均为 0/4。两候选定位不合格，均未产生 `model-frozen.json`，T3 及依赖它的 T7 真实闭环不可升级。详见[Qwen3.5 探测摘要](../artifacts/research/model-probe/summary.md)与[Qwen3-VL 候选实测](../artifacts/research/process/20261003-t3-vl-candidate/acceptance.md)。

## 2026-10-03 T4 真实 MuJoCo 物理技能

T4 为 `DONE`，只覆盖当前 Franka-like MJCF 单刚性方块、固定离线目标，不代表视觉定位或完整在线任务成功。Jacobian IK 经关节执行器和真实仿真步执行。控制器 v2 在成功运动后锁存当前关节，避免闭爪阶段残余目标续动；一次有界载荷补偿仍保持 5 mm/5°、速度、加速度及超时门槛。同场景实测闭爪 TCP 漂移 79.32→8.45 mm，载荷下最终误差 4.66 mm。v2 正例显式增加 0.5 秒 post-lift 持位，真实物理六类验收 6/6 PASS、4358 步；无额外持位的 5/6 失败原件保留。见[v2 因果复验与协议边界](../artifacts/research/process/20261003-t4-physical-skills-v2/README.md)及[验收结果](../artifacts/research/process/20261003-t4-physical-skills-v2/acceptance.json)。原[首轮验收](../artifacts/research/process/20261003-t4-physical-skills/acceptance.md)仅对应当时源码与协议。

T4 为形成真实夹持而修改机器人资产，`scene.xml` SHA-256 从 `6a793870…` 变为 `182fb2bc…`。已验收 T6a 的 100/1000 组记录明确保留旧 SHA，仍是旧资产的历史静态感知证据；其 `SceneSpec` 不能直接在新资产 `apply_scene`。T5 从新资产生成独立场景并记录新哈希；后续若要把 T6a 数据用于新资产一致的研究运行，须另建版本并重新生成/验收，不能覆写旧记录。

## 2026-10-03 T5 离线教师与独立物理评价

T5 为 `DONE`，验收范围是当前资产上的 **20 episode 离线教师冒烟**。教师仅用离线真值形成显式动作目标；在线机器人不读取评价器真值。每个物理步的不可变快照用于独立判定：抓后抬升至少 50 mm、连续稳定夹持至少 0.5 秒、释放后在目标区稳定至少 1 秒，安全扫描还覆盖落稳前的步骤。成功运动与脚本完成均不直接算任务成功。新版数据位于 `datasets/rgbd-teacher-smoke-v2`，20/20 真实执行并发布，7 `SUCCESS`、12 `FAILED`、1 `SAFETY_VIOLATION`；仅 7 条标 `execution_verified=true`，固定正例成功、无接触反例失败，13 条非成功轨迹完整保留。只读[逐条验证](../artifacts/research/process/20261003-t5-teacher-validation.json)复算协议/资产及文件 SHA、56,994 个连续物理样本和 104 个动作帧，返回 `valid=true, accepted=true, errors=[]`；跨 T2/T4/T5/T6a 回归 251 项通过，独立复审通过。见[完整 T5 验收](../artifacts/research/process/20261003-t5-teacher-accepted/acceptance.md)。

首批 `datasets/rgbd-teacher-smoke` 是旧规则诊断产物：正常的干扰物-桌面支撑接触被误报，且抬升以落稳前悬空约 8 mm 的位置为基线。它未被覆盖，也不作为当前验收数据；新批使用教师/评价/控制器源码 SHA 和规则版本指纹，旧目录不得静默恢复混用。唯一安全事件按现行保守规则记录手指短暂超限约 0.11 mm；自碰撞只声明已检查的 33 对几何体。7/20 是开发冒烟结果，不是正式 G1 成功率或在线视觉闭环结果。T3 后续已完成限定验收；当前 T7 已实施且为 `DONE`，开发 smoke 与最终454项回归均通过，T6b 还等待 T8 预算和全量数据验收。

## 2026-10-03 RGB-D 分阶段改造

用户已授权按[代理执行计划](superpowers/plans/2026-10-03-rgbd-evidence-research-roadmap.md)启动实施并重建过程文档。首批 P1 的 T1 来源审计、T2 同步 RGB-D 采集已完成并通过独立审查；当时88项合并回归通过，真实采集100个桌面点的最大高度反投影误差为2.728 mm（门槛5 mm）。后续 T3 真实VLM、T4/T5 物理技能和离线教师另见上文；视觉驱动的在线抓放及新正式实验结果仍未验收。

本轮过程记录统一位于 `docs/research/process/`，启动基线位于 `artifacts/research/process/20261003-phase1/`。历史 Phase 验收保留，以下 Ubuntu 快照不自动升级为新研究方法的验收。软件契约通过、真实图像采集、真实模型调用和物理任务成功分别记账。

后续 **T6a 静态数据工厂为 `DONE`**。共享数据契约、原子恢复/来源与分组校验、四个CLI已实现；124项数据测试、123项旧路径回归、定向Ruff/mypy（18 source文件）及[独立代码审查](../artifacts/research/process/20261003-t6a/final-review.md)通过。真实100/1000个独立组均完成生成、校验、导出与离线重建：100组为35正例/65负例、train/calibration/selection/test=80/5/5/10；1000组为301正例/699负例、800/50/50/100。见[最终验收](../artifacts/research/process/20261003-t6a/acceptance.json)。T5 已另用新资产完成离线教师冒烟；T3 已完成限定模型验收，当前 T7 为 `DONE`，T8已就绪。T6b保持TODO，10000组与教师整合未运行；T6a 的静态感知记录不作为动作成功证据，也不改变真实VLM、正式研究结果或硬件状态。

## 2026-10-03 第三方真实 RGB-D 数据部署

新增三套真实数据已接入应用统一 reader、索引、CPU 0/2 worker、预览和离线回放，均为 `SELECTED_RGBD_VERIFIED`：IndustryShapes 370 对、6 场景、771 实例，全部保留官方 classic/test；MicroAGI01 108 对，按日志时间一对一配对，最大差 4.918 ms，不宣称采集同步；VINS-RGBD 973 对，RGB/depth header.stamp 精确一致，原 RGB 帧号 973 无配对深度并保留记录。共 1,451 对，全阶段离线转换，新增网络字节 0。原 748 件约 927 MiB 下载仍遵循 enp7s0 大陆物理直连。Industry 原 test 另 553 帧缺镜像文件；VINS 缺 CameraInfo 和已核准深度单位，`depth_m=None`。所有源均未升级机器人动作、点云几何或完整原库验收。详见[读取器验收](../artifacts/research/process/20261003-additional-rgbd-readers/acceptance.md)、[统一入口](rgbd_additional_readers.md)及[下载阶段证据](../artifacts/research/process/20261003-full-rgbd-download/acceptance.md)。该数据接入本身不改变 T3/T4 的真实研究验收状态。

第三方离线数据工具使用独立 `.venv-data`，数据根目录为 `$HOME/datasets/BIGsmall`。按用户“精选集先用”授权，魔搭 `Voxel51/graspclutter6d` 固定 revision `f6d801ce94dbeaf1a40c19006b741cba7675a101` 的 43 个文件共约 754 MiB 已通过大陆物理网卡直连下载与上游 SHA256 校验。10 个场景、40 帧 RGB-D、669 个实例掩码完成实际校验，5 个场景预览及 CPU 0/2 worker 接入通过，独立变体 `graspclutter6d_curated` 为 `CURATED_RGBD_VERIFIED`。缺相机 K、RGB-D 对齐证据、采集时间、动作与官方 split，几何和时序仍未验证，不能用于可靠点云或完整官方抓取评测。软件数量及复核见[精选实际验收](../artifacts/research/process/20261003-curated-rgbd/acceptance.md)，使用见[精选说明](rgbd_curated_quickstart.md)。

原 RoboMIND 固定 revision `be28d59219430dc8796f221f7fc4c23e113d6a4e` 的真实 `h5_franka_1rgb` 两任务需 68 个分卷、671.31 GiB，超首轮 10 GiB，仍为 `BLOCKED_BUDGET`、目标轨迹 0；HF gated 条款未代接受。另实际检查的小例 ZIP 只有 RGB，标为 `REJECTED_RGB_ONLY`，不计 RGB-D。原 GraspClutter6D 固定 HF revision `973a567efa2f8047e5a40c9113a672e8215bcc1b` 的 195.528 GiB 完整归档仍无已核准大陆源，为 `BLOCKED_NETWORK`，约 3.24 GB 断点保留。原两目标均为 `NOT_VERIFIED`，精选验收不升级它们；见[部署说明](rgbd_datasets_deployment.md)与[完整目标记录](../artifacts/research/process/20261003-external-rgbd/deployment-report.json)。该工作不增加正式研究结果、模型训练、闭环抓取或真实硬件验收；历史研究进度与以下 Ubuntu 快照保留原口径。

## 2026-10-02 Ubuntu 当前快照

项目全部按 Sim2Real 模拟设备路线开展，真实设备阶段禁用。部署与证据索引见 [Ubuntu 交接报告](handover/ubuntu_deployment_report.md)。Core、Dashboard、MuJoCo、ROS2、MoveIt 的本机验收 PASS；Isaac 和 Sim2Real 为 WARN（实际仿真已运行，全参数应用和严格配对未接受）；Phase13 真实模型 BLOCKED；Phase12 full 和 Thesis 为 WARN。

干净 `d571e1b0` full 原始实验保留 5,580 行、5,040 runtime-completed、540 blocked-before-runtime，验收为 PHASE12_REJECTED。360 条 MoveIt 阻塞来自 Phase12 adapter 当前固定禁用，180 条模型阻塞来自未配置真实服务；原摘要的固定环境标签不能用于判断本机是否安装了 Isaac。`da299bd9` 修复了 repetition 丢失，并在独立目录重分析；180 对中 120 对满足旧标量统计规则、60 对含安全停止，full 仍拒绝，verifier-gated authoritative thesis run count 为 0。该统计不满足公平物理配对条件，不形成跨引擎性能结论。

`b35e5390` 的正式工作台验收为 PHASE11_1_SIMULATION_RUNTIME_ACCEPTED / PHASE11_2_SIMULATION_AI_CONSOLE_ACCEPTED，37 E2E 包括实际 MuJoCo；local_model_runtime_accepted=false。原论文历史 466/74 与 35 references / 28 figures 可复现，和新 full 数据分别保存。

## 历史分支基线（保留原验收口径）

下表是此前分支的 verifier 状态，并不将其自动升级为当前 Ubuntu 的全物理 DR、公平配对或真实模型验收。

| Capability | Status | Verifier | Evidence | Hardware Claim |
|---|---|---|---|---|
| PCSC / ETEAC / AUTO | ACCEPTED | `scripts/verify_phase8_2.py` | Phase 8 artifacts | 不涉及真实硬件 |
| MuJoCo simulation | ACCEPTED | `scripts/verify_phase9.py` | `artifacts/phase9` | 不涉及真实硬件 |
| Isaac / cross-backend | `PHASE9_2_ACCEPTED` | `scripts/verify_phase9_2.py` | `artifacts/phase9_2` | 不涉及真实硬件 |
| MoveIt Runtime Dry-Run | `PHASE10_MOVEIT_DRY_RUN_ACCEPTED` | `scripts/verify_phase10_2a.py` | `artifacts/phase10` | `sent_to_hardware=false` |
| Dashboard Console | `PHASE10_2B_CONSOLE_ACCEPTED` | `scripts/verify_phase10_2b.py` | `artifacts/phase10/phase10_2b` | 不涉及真实硬件 |
| Level 0 framework | `PHASE10_LEVEL0_FRAMEWORK_ACCEPTED` | `scripts/verify_phase10_2c_level0.py --fake` | `artifacts/phase10/level0` | fake/framework；真实 Level 0 未开始 |
| Simulation Workbench | `PHASE11_SIMULATION_WORKBENCH_ACCEPTED` | `scripts/verify_phase11_simulation_workbench.py` | `artifacts/phase11/verification` | 不涉及真实硬件 |
| Simulation Runtime | `PHASE11_1_SIMULATION_RUNTIME_ACCEPTED` | `scripts/verify_phase11_1_simulation_runtime.py` | `artifacts/phase11_1/verification` | 不涉及真实硬件 |
| Model Control Center | `PHASE11_2_MODEL_CONTROL_CENTER_ACCEPTED` | `scripts/verify_phase11_2_model_control.py --ci` | `artifacts/phase11_2/verification` | 不涉及真实硬件 |
| Simulation AI Console | `PHASE11_2_SIMULATION_AI_CONSOLE_ACCEPTED` | `scripts/verify_phase11_2_model_control.py --ci` | `artifacts/phase11_2/verification` | `dispatch=false` 的 planner dry-run |
| Local model runtime | NOT_ACCEPTED | `scripts/verify_phase11_2_model_control.py --ollama` | 无真实本地模型 accepted evidence | installed_model_count=0 |
| Ollama runtime | NOT_ACCEPTED | `scripts/verify_phase11_2_model_control.py --ollama` | `ollama_runtime_status=SKIPPED` | 不涉及真实硬件 |
| Phase 12 smoke suite | `PHASE12_EXPERIMENT_SUITE_READY` + `PHASE12_THESIS_ASSET_PIPELINE_READY` | `scripts/verify_phase12.py --smoke` | `artifacts/phase12` smoke artifacts plus `artifacts/phase12/verification_phase12_1/phase12_smoke_status_correction.json` | 90 rows at `7b4c9af` are `SYNTHETIC_PIPELINE_SAMPLE`; original smoke summary retained and superseded；不涉及真实硬件 |
| Phase 12 validation suite | `PHASE12_VALIDATION_EXPERIMENTS_ACCEPTED` + `PHASE12_VALIDATION_ANALYSIS_PACKAGE_ACCEPTED` | `scripts/verify_phase12.py --validation --artifact-root artifacts/phase12_2_clean/validation` | `artifacts/phase12_2_clean/validation` | clean provenance；540 rows，466 runtime-completed rows，74 rows blocked before runtime；不涉及真实硬件 |
| Phase 12 full final evaluation | NOT_ACCEPTED | `scripts/verify_phase12.py --full` | 无 full accepted artifact | full profile required before final thesis conclusions |
| Real robot validation | NOT_STARTED | 无 | 无 | `highest_real_hardware_acceptance_level=NONE` |

硬件边界：

- `real_controller_contacted=false`
- `hardware_motion_observed=false`
- `hardware_write_operations=[]`
- `real_robot_validation=NOT_STARTED`
- `highest_real_hardware_acceptance_level=NONE`

禁止声明：

- `BIGSMALL_REAL_ROBOT_PROJECT_ACCEPTED`
- 真实机械臂运动实验完成
- Level 1-6 验收完成


**T7 最终验收（2026-10-04）：DONE。** 最终 EGL 回归454 passed、1项已有依赖警告，30个源文件Ruff/mypy通过；独立runtime审查无开放P1/P2。真实worker复查1次模型调用、4动作后因抬升保持不足如实FAILED，归档无错误且终态一致。20场景仍为2成功/18失败，未扩大分母；非正式G1。T8/T17a为READY（未实施），T6b为TODO。详见[完整验收](../artifacts/research/process/20261003-t7-visual-closed-loop/acceptance.md)。
