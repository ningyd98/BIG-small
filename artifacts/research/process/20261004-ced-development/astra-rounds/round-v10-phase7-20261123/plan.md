# Phase 7 教师采集链软件 E2E 计划

gpt-6.2-astra · 2026-11-23 · 研发分支 `research/harness-candidate-v10-phase2-20261121` · 基线 `2ec0c98f82a6cab7fb1f9abbec37631226d3d605`。

开发目标为完整检查冻结像素可支持的 LIFT 与 r593 证据，修复可再现的停止时序与来源归档读取，贯通隔离的采集、数据库、落盘与读取。Python、OpenCV、MuJoCo 和 SQLite 沿用现有版本。原始失败和指纹来源见 Phase 6 步骤报告和本轮 [plan.json](plan.json)。以主工作区 `../../../AGENTS.md` 及本次用户授权为准。

## 事实、前置与边界

- 基线首组正式运行消耗过唯一 claim。四个返回动作、八条准入、七次 ALLOW，LIFT POST 因 object_lifted/object_stable 未准入而 STOP。Shield 同处 ALLOW。活动 E 是 acquisition-124；B 是 123。4200 派发、5155 返回、6240 终步。末帧两个各 9 像素的候选，两个 0.5 s 窗口来自不同时间段。模拟器物体高度变化 85.217 mm 属离线物理观察。深度误差界为空，本次连续区间速度界、真实身份及四分之一转动消歧有待逐帧确认。
- 11,109 个 allocated frames。默认 marker 读回从 step 2089 的 acquisition-3451 报缺失，前 12 项截断；同一帧不同 refinement、不同角色和完整几何门须独立分析。6240 步停止时 commands 428、429 各有 BEGIN/END，父 ID 为 unbracketed-operations。内部 failure scope 直接关闭 guard，外层 purpose-6 到 record_seq=41819 才开启。原 guard=FAILURE，worker=BLOCKED_BY_ENV，正式资格 UNKNOWN，另外八组 NOT_RUN。
- 在指定工作树核对 HEAD、解释器和输入 SHA。依 plan.json 的路径验证原 manifest、claim、启动与正式产物、两个 v9 协议和 16,885 项 v9、55,583 项 v10 inventory。大文件流式校验；逐帧结果用两份清单中的相对路径和 SHA 定位。旧工具包含固定基线/预算及输出路径；先阅读，仅复用只读函数或将工具适配到本轮私有目录。保留未跟踪用户清单。用独立可写目录保存日志、逐帧明细、SQLite 与新登记；EGL 可用、足够本地磁盘，物理离线分析与在线视觉输入分开。设置 PYTHONDONTWRITEBYTECODE=1、PYTHONPATH=src:.、MUJOCO_GL=egl。
- 正式仿真、正式 claim 增量、生产模型调用和硬件动作均为 0。禁止运行正式 --collect-once、用 prepare_once 或复制真实登记借新 claim 复跑八动作。允许明确标识的软件测试数据库/隔离夹具，以及为检测真实调用边界所必需的短时非正式后端测试。核前后指纹、原组/原 claim 数、原 DB 只读核对、实际各类运行与资源数量。禁止改历史原件、清理失败日志、放宽白名单或新开正式号。新根因、预算/资产/门槛变动或未预期失败先回 Astra 另轮；本计划列明的预期 RED、负控拒绝、证据不足和历史部分失败均是设计内结果。

## 实施与验收

### A　冻结全段视觉与全量 r593

- [ ] 以 partial-originals.allocated_frames 作分母，按 frame_sources/role、operation、acquisition、record_seq、episode、相机与校准、像素/valid depth/元数据和原哈希逐一对应。只允许 pixel RGB、optical-Z、valid mask、登记内外参、标记规格和真实传感器时钟进入视觉计算。物理样本、实例标签、策略/控制器反馈、动作意图不得参与身份、几何或稳定性求解；若做独立离线归因，另表列来源。流式读、独立计数，等值同一步 acquisition 各自核验，逐角色记录覆盖；不把同一步重拍当时间推进。允许安全缓存已经验证的同一输入和模式，统计保留逐 acquisition 身份。
- [ ] 覆盖包含两端的 4200…6240（2041 个预期物理步位），从调度 E 到终步，区分此前同一步采集、动作/每步/缓存帧，核 4200/5155/6240、5035…5155/6120…6240。核 source binding、色参考 B/E、单调模拟/采集时钟、同一步与乱序/缺帧/过期和原 tracker clock 之间的区别。记录原色度距离 <0.14、通道极差 >30、8 连通、面积 >=8 的全部候选数、面积、bbox、位置/深度和有效掩膜，逐步给出唯一/多/零、可追溯关联、遮挡/对称歧义、边界覆盖及不足原因。终帧重现两块 3×3。仅在每个备选解释可被事先定义的可观测约束排除、来源和误差界可复核时提出解歧。逐帧可观测不等于连续速度/角速度上界；给出身份、完整范围、升高下界、稳定性独立判定。缺采样、无校准、无区间运动界、未解对称或多可行路径时对应事实维持 UNKNOWN，不用末帧/两端插值补证。不得把离线新增帧输入说成原在线 tracker 曾消费。只有原在线可取得、读回可独立一致重算且有正负控的结论才改 tracker，否则交付定量诊断和守门回归。
- [ ] 让 detect_pose_marker 对每一已分配帧分别运行 NONE 与 SUBPIX，核全部 11109×2 条记录。列按角色、动作/步骤、同帧 2×2 交叉表、失败原因、首末、最长失败区段，区分 ID 不可见/错误/多个、角点分辨率、深度窗、平面/尺寸校验及无法细分者。记录阈值和 detector 原判定，必要时检视开始/结束/改变的原像素和 rejected candidates，只为有证据的原因命名。保留顶视 320×240、r593 ID 7、0.075 m、8 px、既有平面和几何容差/资产。SUBPIX 单帧改善须有同一可观测标记、唯一 ID 与原所有门，不能凭改善比例切换策略。若证据支持新来源代的读回策略，在新登记/回放明确其适用版本；冻结 NONE 与 SUBPIX 结果分别保留。
- [ ] 先添加针对具体候选修改的 RED 或已有规则的守门控制。包括唯一且可验证的标准目标/标记、双候选可交换、遮挡/深度空洞、边界缺帧、同一步重复或错时、校准缺失、对称旋转、伪 marker/错误 ID；校验条件逐项 PASS/UNKNOWN/拒绝。不要为了阳性稳定性虚构观测能力。工作范围为 vision/tracking.py、vision/pose_markers.py、research/native_collection_grounding.py、相应归档 tracker/reader 和对应测试，只有数据支持才更改产品。可新增一个可重跑的离线像素诊断入口及其小型软件测试，逐帧明细留本机。

### B　真实停止指令作用域与采集链

- [ ] 在 tests/test_native_collection_authority.py 或专用 phase7 测试用实际 recorder/backend、_collection_guard、内层 capture_each_physics_step，抛出与准入拒绝等效的原异常。先记录 RED，证明原 hold_current_joints/emergency_stop 的 parent 实际不存在。另覆盖正常退出、内部后端/guard callback/观测者异常、嵌套动作、termination entry/exit 或 stop 故障、重复 close。核实 stop 恰一次，先 hold 后 emergency_stop；恰当的同 episode TERMINATION 真实包住两条指令及其嵌套 CONTROL，BEGIN/END 顺序、命令 owner/父、原步与生效下一步、无后续 physics/dispatch；FAILURE 和主异常身份/traceback 及次错误被保留。purpose 自身不可用也必须立即执行安全停止并记录来源失败。
- [ ] 在实际首次关闭/急停的调用点建立 recorder 的 termination 作用域，允许在 backend.enforce_execution_guard/_close_execution_guard 和 native_collection_application._collection_guard 之间传递受限的可选上下文/通知，沿用当前无 recorder 调用者。保留后端自身的即时 fail-closed、非重入/线程/生命周期与诊断，禁止推迟制动、重复 STOP 或事后重写父 ID。若 recorder 需要支持嵌套作用域，只修改其必要部分并用之前的正常/异常/线程负控证明兼容。
- [ ] 一项软件 E2E 从明确隔离的测试夹具、真实 NativeCollectionApplication、SimulationWorker、SQLite lease/attempt、真实 run_from_worker/recorder/guard、落盘旧格式 inventory/body/final/worker snapshot 到公共 group/registry reader。选短初始化后单个确定性异常，在真实 recordable 作用域内尽早失败，避免运行完整教师或重放已消费身份；使用临时夹具的合成身份/启动授权边界或测试注入的专用 claim 替身，无正式登记或新正式 claim，不绕开待测 recorder/guard/reader/DB。明确哪一步注入、哪些实际执行；如需要分层，区分贯通失败路径和已有八步正控的构造跨度，核真实 DB 状态与落盘里计数、读回帧/动作/错误/资格一致、资源关闭与 no retry。单独用既有八动作/17 准入完整软件夹具验证成功数据路径；说明 fixture 提供和跳过的每一层。短非正式 MuJoCo 后端和单帧预检按实测登记，软件轨迹不产生正式研究资格。

### C　历史来源、登记与发布

- [ ] 先冻结基线 v10 Git 源树到本轮私有归档（git archive 2ec0c98f…，不包括 raw/DB），逐项核 456 项、固定 config/资产和 SHA。v9 使用匹配 capture-detach-round/v9-source 与 v9-protocol；另一个 v9 协议仅作独立对应关系/错配负控。当前代码中的 v10 helper 未接收 archived_source_root、CLI verify 无归档入口，读取器有硬编码 ROOT。用 RED 覆盖 live 来源变化、历史目录中多/少/改登记源码、错 config/资产/错 release/协议与归档错配、符号链接，区分无关目录与完整来源枚举范围。沿用 v9 独立枚举/重建策略为 v10 重建完整登记并核对注册路径集合、source_generation、release_reference、canonical bytes；向离线 group/registry、必要的 component/CLI verify 始终传递并消费相同已验证的 source_root。若历史算法实现与新代有行为差异，使用原版本执行比对，记录源码与实际运行版本；单纯来源哈希不能证明运行了归档算法。新增仅 --verify 可用的可选 --source-root（或等价明确名称），拒绝在 prepare/collect 等模式使用；普通在线 factory/current_sources 默认保持严格，不能由传入的协议自行定义预期文件集合或跳过验证。
- [ ] 公共 CLI 和 Python 对冻结 v9/v10 完整读取可获得的信息，前者一动作两条准入、后者四动作八条准入，分别对照 Phase 4 / Phase 6 报告，特别保留 v10 的 428/429 失败、组 UNKNOWN 和八组 NOT_RUN。必要时复用独立只读 bounded replay 逐对核原 Shield/conditions 与 tracker clock，保证历史重建与新代反事实分别报告。保存原始输出；同一次 group_sink 与独立 CLI 可复用，避免无意义重复全量解码。归档 API/CLI 变动范围 research/native_calibration_collection.py、native_full_horizon_originals.py、native_archived_tracker.py、scripts/collect_native_calibration.py 与 test_native_registered_teacher_release.py 等归档回归。
- [ ] 以修改后的最终源码在全新私有路径 --prepare-only，核协议 456 项或由新增登记路径引起的可解释增量、键集合/新 source_generation/固定资产、9 个 assignment 的默认 release 配置及来源、无 claims/attempts。标明这是研发预登记，不是新的正式运行身份授权，旧 ID 即使在模板出现也不可重试。对新 source 做隔离单帧验证（可复用 Phase 6 preflight 的 capture/校准/marker 函数，去除其仅限旧基线的启动断言，绝不调用启动脚本），核 bootstrap、渲染/物理/租约/教师次数与只读空登记 verify。只有未来获授权的新独立正式登记、不同未消费身份及其预算，方可执行正式运行。
- [ ] 本轮保存所用命令/计数、控制结果和文件哈希；公开 validation.public.json、step-report.public.md、stage-summary.public.md。保留每个 RED 原件/日志并将软件、实际隔离后端、冻结历史及正式研究资格分列。仅按明确路径提交研发分支，推送后核三方 SHA；完整 raw/DB/claim/绝对路径日志本地管理。需再计划时其余独立验证可继续。

## 验证命令

在工作树根执行。PRIVATE 指向新建本轮私有证据目录；PY 指向相邻 harness-candidate-20261118/.venv/bin/python。FROZEN10 与 FROZEN9 分别是已验证的历史源码根。R10 与 R9 是原协议目录；逐文件路径见 plan.json。针对新增测试保留修改前和修复后的同一 nodeid 输出。

```bash
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. MUJOCO_GL=egl
PY=../harness-candidate-20261118/.venv/bin/python
"$PY" -m pytest -q tests/test_opencv_target_evidence.py tests/test_pose_marker_evidence.py tests/test_pose_marker_visibility.py tests/test_native_archived_tracker.py
"$PY" -m pytest -q tests/test_native_collection_authority.py tests/test_mujoco_full_horizon_sampling.py tests/test_mujoco_execution_guard_v1.py tests/test_native_harness_stop_diagnostics.py tests/test_native_observer_failures.py
"$PY" -m pytest -q tests/test_native_registered_teacher_release.py tests/test_native_full_horizon_originals.py tests/test_native_registered_admission_replay.py tests/test_native_horizon_execution.py
"$PY" -m pytest -q tests/test_native*.py
"$PY" scripts/collect_native_calibration.py --verify --protocol "$R10" --source-root "$FROZEN10" --output "$PRIVATE/verify-v10"
"$PY" scripts/collect_native_calibration.py --verify --protocol "$R9" --source-root "$FROZEN9" --output "$PRIVATE/verify-v9"
"$PY" scripts/collect_native_calibration.py --prepare-only --config configs/research/native_registered_single_teacher_p0_v10_20261121.yaml --output "$PRIVATE/prepare-v10"
"$PY" scripts/collect_native_calibration.py --verify --protocol "$PRIVATE/prepare-v10" --output "$PRIVATE/verify-empty"
git diff --check
```

另执行 A 的离线诊断入口、B 的隔离软件 E2E、C 的新代单帧预检和独立 Python 读回；步骤报告记录研发实际采用的入口、参数与摘要。核查 tests/test_native*.py 的夹具只写临时测试资源，不启动正式运行；如单个测试依赖外部原件/预算，记录边界并运行其余安全回归。对新增和修改路径运行项目 Ruff 与既有类型检查，记录基线已有差异。本轮开发验收不要求把冻结失败改判通过，也不要求从不可观测像素证明物体稳定。
