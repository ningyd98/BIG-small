# OC3 camera / marker / condition 接口依赖审计

状态：**STATIC_DEPENDENCY_AUDIT_COMPLETE_WITH_METADATA_PROOF_UNAVAILABLE**。本报告仅供下一轮 OC3 Astra 规划。没有实现、修复或验收新域，没有新的产品反例。产品 import、CLI、测试、backend、相机、renderer、physics、模型、decoder、网络、Git、源码修改均为 **0**。

依据 operational-clock supplement 的 OC3、clock-dependency-review §7 第3项以及原修复计划 R5。已保存 stage62 和 OC2 Task1 round63 final 只作历史上下文：Task2/3 与 RW1 的失败/预期缺件不在本审计重评；不读或强 pin 正在修复的 operational_*、worker、protocol_generation/teacher 或六根阶段总结。stage62 snapshot 内列出的根总结 SHA 是历史引用，本次没有重读这些根文件。Task1 的软件 PASS 不代表 actual prefix、当前 lease、consumer 或域验收。

## 时间来源与已存在区分

| 路径 | 已有真实接口和时间输入 | OC3 需要连接的边界 |
| --- | --- | --- |
| 相机 acquisition | `camera._capture:75` 在渲染开始取 datetime；SensorFrame 同时有 captured_at 与 sim_time_s。capture_session:84 调用 fresh capture_with_instances；backend:686 的 get_sensor_frame 直接返回 cached step frame；fresh capture:740 不推进 physics。各 pass 共享物理 state hash。 | 保留原 acquisition 身份/S 状态；新 D 来源需绑定实际 CAPTURE 事件和完整括号。读取缓存/重新包装旧图片时刻不能代替采集时刻。aware timestamp/checksum 不是 current source authority。 |
| transport | observations:23 的 frozen extra-forbid RGBDObservation 保留 datetime/S、frame/episode/calibration，并将它们纳入 checksum；observation_from_sensor_frame:215 原样携带 sensor time。 | 新 schema 必须显式携带或绑定 D bracket/domain，不能把 counter 填入 captured_at，也不能对 frozen legacy observation 任意附加字段。 |
| RawV3 source/derivative | recorder:396 clock pair 仅包围 datetime 调用；:480 分配 acquisition 后记录实际 operation BEGIN，END 保留完整 S/step、source frame；:629-690 online derivative 引用 source_acquisition_id 与 transform pins。 | 可复用 single source、实际 observed operation 和 transform join；旧 V3 descriptor 明确 monotonic/UTC、uncertainty=None，不能成为新 D actual 或校准 UTC。新记录版本沿真实 source 接入，旧原件语义保持。 |
| 外来相机 | Isaac parser:191-219 接收 remote captured_at 与 response sim_time_s；capture helper:102-128 沿原 observation contract 转换。 | 无同域源/桥接证据时不能绑定本地 D；arrival/cache read 不能冒充 remote exposure。原 5000ms 接收和 1000ms 未来规则须保持，本审计未定位/运行全部 ingress enforcement。 |
| pose marker | pose_markers:58-99 结果保留原 observation ID/checksum/captured_at/registration；没有 now/fresh source。 | detector 复用；单帧几何、rotation 和 sanity check 不构成连续运动/稳定性/未来界。 |
| marker association | marker_association:375-450 先验证注册、完整 context、角色、asset、episode/calibration/camera，再检查 `0 <= datetime_age <= 5`。:611-629 将 live 和 DEVELOPMENT_REPLAY 分开。 | 只连接 versioned freshness/source interface；replay 用原 capture time 得 age0，仍不能作为 fresh/native admission。 |
| condition | conditions:93-144 唯一 evaluate_conditions 使用传入 now 或 datetime.now(UTC)，默认 max_age5；未来或 age>5 为 UNKNOWN。递归/组合条件共享同一 now。 | 统一真实 current D 和原 acquisition D；保留唯一判据及 attributed visual fact 的 exact observation/target/pixel/boolean 校验，不增加第二 evaluator。 |

相机与 RawV3 已区分 S、host datetime、monotonic 记录及 acquisition/derivative 来源；这与“所有消费者已经使用新 D”是不同结论。现有普通载体没有 D authority/bracket；OnlineEvidenceSnapshot 还单独携带 robot_state，本身不能证明所有组件属于同一个 D event/S snapshot。

## 精确三个 native 调用点

原计划 R5 明确为 execution 的两处以及 visual_verification 的一处，而不是另造三个消费者：

1. **N1 — `execution.worker_dispatch_guard:1456-1518`**：activity/role → 当前 publication 和 exact cached grounding → observation/robot/tracker → 原 requirements → native_action_contract → `validate_evidence(datetime.now(UTC))` → 非 VALID 拒绝 → hard-stop/activity 再查。duration 来自原注册 requirement。未来 D 读取必须位于真实 dispatch 边界，并与 acquisition、grounding、publication、原预算同域；原 lease/fencing/角色/CAS 校验仍需要保留。
2. **N2 — `execution.require_native_action_evidence:1520-1615`**：OPENCV 当前 context/observation → native_action_contract → 当前 datetime validator → CLOUD_RETURN/PRE_SAFETY/PRE_SKILL route。:2099 推理后 recapture；pre-safety/pre-skill 重观测会要求重新 compilation/safety。新 D 不能让新帧/晚回包刷新原 deadline；此处 nominal duration 及 repository 的原注册 duration 需要显式同一 horizon 语义。
3. **N3 — `visual_verification._phase_verdicts:850-907`**：SQLite `route_visual_verification_if_current:2760-2818` 在 BEGIN IMMEDIATE 内读取 datetime.now(UTC)，derive_route 校验 owner/checkpoint/pool/retry/current publication，_computed_route 检查原 deadline/TTL，再使用原 requirements 构造同一个 validator 合同。EFFECT_PHASES 另校验真实 start/result/return/new acquisition 后调用 canonical conditions。新 D 应贯穿事务当前读数及纯 helper；current_publication/_execution_grounding 的隐式 datetime.now 也在闭包中。

三处都调用 `native_action_contract:17-50`，现有 factory 明确保留 geometry=None、motion=None，caller/model 的有限数值不能补成证书。validator:109-137 的 `E + v*(age+expected_duration)` 目前 age 来自 datetime；max(timeout,expected)/1000 和模型字段没有明确 D/S 类型，不能在迁移时直接把 D 年龄、S 速度、S 动作时间混加。DecisionEnvelope:80-103 及 commit validator:158-185 仍使用 created<=now<valid_until，deadline 等值拒绝。

## 可复用的窗口、source 与 horizon

- **owner_registration**：OriginalActionRequirements 留存完整动作；effective_deadline=min(task,verification,contract)；freeze_original_visual_plan 不延长原 deadline。bind_step_grounding:827-978 将 expires clamp 到原 deadline 与原 acquisition 加最小普通/condition TTL，绑定 exact checkpoint/frame/source/recipe，长 duration 需独立 fresh exact receipt。复用这组规则，统一 versioned 时间载体；不删除真实外部 UTC 有效期。
- **visual_owner / repository**：publication、current_publication、validate_grounding、monotonic_pools 已保留原 pool 身份、原截止、revision、consumed counts 与半开有效窗口。`monotonic_pools` 名称指 quota 单向消耗，不是 operational clock authority。未来要迁移其隐式当前时间，而不是用新 now 旁路原 publication。
- **effect**：visual_verification:736-847 已要求 created<=start<valid_until，以及原注册<=start<=result<=returned<new capture<=transaction now。ACK 不自动证明 start/effect；这些事件必须各自有新域源 join，不能只替换终态时间。
- **supervision / waiting**：supervision context/reply 有 exact 身份与 maximum-age；execution:1721 的 worker period cursor 仍来自 UTC task-start 差。ExperimentClock:10-38 明确用 monotonic wait duration 推进 S、分别记 wall 与 wait_sim，可复用 passive WAIT；不证明 active/render/queue 时段全局 S=D、suspend 覆盖或 future H_D。
- **native_calibration / native_references**：from_application 的固定 index/catalog/role/source 校验，estimate 的 owner/reference/policy/support 重建以及 exact reference reconstruction 已存在。native_geometry_calibration:633-681 要求完整 nominal `start_sim+horizon`，不截短到 observed success；fixed-goal motion0 仅是命令坐标不变，不是 body/TCP 速度证书。三处当前入口尚不消费 NativeCalibrationSource，不能把其存在写成有限 native 准入。
- **原 v1 校准门**：independent_utc_uncertainty_ns 的 complete UTC 原件、BRACKETED/declared uncertainty，以及 independent_components / conformal_group_quantile 的至少9独立组件、coverage .9、missing/failed 全分母、10mm 均保留。未来另立 D source/schema，不能 utc_uncertainty=0 或改旧 BRACKETED 判定。

## 真正连接闭包与不需要重造的部分

直接语义闭包是 observation/versioned envelope、action_evidence、evidence models/validator/conditions、marker_association、execution 的 capture/action/supervision 边界、visual_verification 与 SQLite transaction-current clock、owner_registration/visual_owner、supervision、verification_router/clock，以及 native calibration 的 source/horizon 路由。它是下一轮 Astra 选择精确改动范围的输入，并非本次已批准实现清单。

capture/session、camera、backend CAPTURE observer、RawV3 acquisition/transform、native reference、marker detector 都有既有复用点；不能因时间迁移就重建相机、控制器、执行器、owner 或 evaluator。是否确需修改共享 producer 接口须在 OC2 quiet 最终版接受后由 Astra 判断，旧 V3 不 retro-fit。

本限定审计的 handoff 尚未审完：startup D/source/reader、活动 worker lease/fencing/heartbeat、planner/local issue-return/request/ACK、全动作 resource/RW1/teacher/common protocol，以及全部外部 calendar/JWT/lease/跨机 bridge。不能由本报告登记完整 OC3 闭包。后续只验证新 schema 的实际接口正负链和真正变化的时间依赖/原效果预算控制，禁止全仓重复测试；本报告没有批准或执行这些测试。

## 静态证据边界与工具观察

所有结论来自源码/已保存报告静态读取。source/current authority、fresh actual、三个 consumer 闭环、restart/suspend、future H_D、geometry/motion、9独立组、G1、SI/UTC、native、formal 均未验收；formal_accepted=false，本审计 support groups=0。完整 raw/DB/远端复现包未审。

一次只读路径猜测误用了不存在的 vision/ingress.py 与 vision/external_rgbd.py；原 rg stderr 各为 No such file or directory (os error 2)，同 shell 后续既存 sed 成功，工具返回 shell exit0，没有单独捕获 rg exit。report.json 保留 exact command 和原 stderr/rg stdout；不编造 exit2、独立 raw 流或产品反例。已向 ROOT 报告，不重试这些路径、不修源。另一次 functions.exec 报告内存摘要的末行 TextEncoder 未定义，报告内容已 store、未落盘；原表达式/错误写入 JSON，不重跑该摘要，直接使用保存内容。之后附加 metadata 比较受到纳秒序列化舍入及工具输出截断影响，又产生 JSON.parse 错误；停止后仅完成不受影响的静态报告，quiet 证明保持 UNAVAILABLE。初次文件枚举输出截断，仅作 discovery，不作为完整目录分母。

## 本次静止版本输入 SHA / bytes

以下是实际读取版本的标识，长文件只审相关 excerpt/call-site；全文件 hash 不等价于全文件语义审查、source authorization 或 runtime 验收。本次不声称 metadata 静止；atime 未列入原尝试比较。初始32输入的 bytes/SHA 为精确标识；mtime_ns 经 JS Number 序列化存在纳秒舍入。附加 before/after metadata 比较输出32差异，随后输出截断导致 JSON.parse 失败，不能用作真实漂移或 quiet 证明。原命令、错误和实际可见输出片段保存在 JSON，不重跑或修脚本；若需要 quiet 补验须另获 Astra metadata-only 计划。正在修复的 scope 没有进入保护 pins。

| 文件 | bytes | SHA256 |
| --- | ---: | --- |
| `AGENTS.md` | 1774 | `8567e10635a650e2619905d6b3a6e0a885812060fecb1cdd4487bbf118593649` |
| `docs/superpowers/plans/2026-10-05-operational-clock-repair-supplement.md` | 6081 | `6bf5022020253b73f08d00adf2785e1ca86ff1e34ca389a55e6c716fcc147030` |
| `docs/superpowers/plans/2026-10-05-astra-repair-plan.md` | 38831 | `7e7514b37b7351208176c1d660771facd7dadf668eb3a5cb9de0b3c43aa50579` |
| `artifacts/research/process/20261004-ced-development/astra-repair-planning/clock-dependency-review.md` | 23219 | `0a957c9e8a5a4e19db2578ae0722b6342fefce29bf12879ebd4e72715b4bdf10` |
| `artifacts/research/process/20261004-ced-development/stage62-publication-snapshot.json` | 2747 | `7fb3fefa8c4b2b5a0fea7b9ed0d62331962185cf6c1715fca6afecf7596cd57c` |
| `artifacts/research/process/20261004-ced-development/report-step62.md` | 4318 | `5f8b4a61793bb44a5142eef8246380d31e8cdb17826e5c33bc440a57af5639ba` |
| `artifacts/research/process/20261004-ced-development/astra-repair-execution/OC2/independent-review-task1/round63/final-review.md` | 6396 | `90815eac2dcdc3f607c0be859dc54d98f8b10d16a53de0887be9641c452cae8e` |
| `src/cloud_edge_robot_arm/vision/capture.py` | 6887 | `f8121afbed70cb1ed8fa182c0b5595c54e12b88989c591878ac9987d8fe7ec7b` |
| `src/cloud_edge_robot_arm/vision/observations.py` | 11603 | `1114e6b2de4107ae516f12f8972fcb3b6f71eae7ae5a45bf93adfeb4aa673bb8` |
| `src/cloud_edge_robot_arm/vision/action_evidence.py` | 2520 | `a122df9e5e4edba513a96abeed46b3b1d9f3dff13a51df5d56cfd63388591edc` |
| `src/cloud_edge_robot_arm/vision/marker_association.py` | 26835 | `f538c6b751ab560b2523cfbe2d237f8956b092931af276bfcda744d10ee4f426` |
| `src/cloud_edge_robot_arm/vision/pose_markers.py` | 9260 | `68f9e6e0675a4b6ccdead896bd767c685fd53357591ab1fdf4d71d124c72264f` |
| `src/cloud_edge_robot_arm/vision/supervision.py` | 2486 | `8f5cab1e2beca0633465686fcd51fe594af599bf5f506f75c83d2931d5662429` |
| `src/cloud_edge_robot_arm/vision/execution.py` | 103171 | `2770da01bfe1869622b104d763c6852b621158d7aaac4004a04fadfdf2a164de` |
| `src/cloud_edge_robot_arm/vision/raw_recorder_v3.py` | 44175 | `4eabd3bf9cdf15b3942c4a740781a95c22ea684f410853c853d0336952d7a303` |
| `src/cloud_edge_robot_arm/vision/native_calibration.py` | 26273 | `0888c38f4caf4dd65c27c29315d8253a1aa8fa1a6fece0bf2b18bcc9bcedb2a6` |
| `src/cloud_edge_robot_arm/vision/native_references.py` | 11089 | `3bba0206ec529c84fdf7e4fd2592a538a4036bcba626772986cf25f5a2d99ff9` |
| `src/cloud_edge_robot_arm/vision/owner_registration.py` | 39344 | `f5e2d0f64f5e2979d0cf41cd8bfd7633fefb8fb3e6cc988aacb766b2841216e0` |
| `src/cloud_edge_robot_arm/edge/evidence/models.py` | 3448 | `0e631704afcf1544382f401434828dcf7b2d9587469049bbb4954e73070c8277` |
| `src/cloud_edge_robot_arm/edge/evidence/validator.py` | 7989 | `cb71ee7c8e05bdb751b34ce6be17c0c7fa29d7cd20fa557b240592d426552674` |
| `src/cloud_edge_robot_arm/edge/evidence/conditions.py` | 11931 | `8298f504df482fbabba720b058f2595eb0a6e1c76f9d2febff7eade01e44d8ab` |
| `src/cloud_edge_robot_arm/edge/recovery/verification_router.py` | 7069 | `31bd8bfddfc699459ca6adcd3305f867e9e8b82be5188a55b1cb82ae161063a7` |
| `src/cloud_edge_robot_arm/edge/recovery/lifecycle.py` | 41062 | `c543846d7c612c6495d6cc948216f073635b52f52c0368710459c3eb9a374c76` |
| `src/cloud_edge_robot_arm/repositories/event_autonomy/visual_verification.py` | 46472 | `2311407d8fb6e2d2f476ccd067f32fcc86e6a816914fecfbe0917e4d45d26414` |
| `src/cloud_edge_robot_arm/repositories/event_autonomy/visual_owner.py` | 28320 | `9b794f6bb1a9606839e1b71d928c3d66185cc9b6ee89dd21d9a42bbe6a9cff9f` |
| `src/cloud_edge_robot_arm/repositories/event_autonomy/sqlite.py` | 140339 | `92bc23b61ee7867547a8f4b6304d813f0caec5d3d338371b7bc1dcd1975eae2d` |
| `src/cloud_edge_robot_arm/research/clock.py` | 1365 | `9ac9da7134054f9173a410f6ab6f63f0f346e85bb3f6e48ebd31a36d8904c134` |
| `src/cloud_edge_robot_arm/research/native_geometry_calibration.py` | 29791 | `7d555c23c5d2ffcdc1a9ba5aacd4601c71e1f6691b69da56893fad6b45dc822d` |
| `src/cloud_edge_robot_arm/simulation/models.py` | 3635 | `35099db3aa50672ccc915431632fad464c62f5c64a47f393a02e560e848b26dc` |
| `src/cloud_edge_robot_arm/simulation/mujoco/backend.py` | 49867 | `b7b6026b1173448de826e53253ae74f92b6b70ea46a404e10054c5cd451a62a6` |
| `src/cloud_edge_robot_arm/simulation/mujoco/camera.py` | 7566 | `d85aa6eda7c9f658f2e3bb550c44b3462ebd65e290d5c7d9b79fa30639136e2f` |
| `src/cloud_edge_robot_arm/simulation/isaac/backend.py` | 10659 | `36d468be9eb480de31933e54df6df2148ee599e2e18900c87c3ea9b487a8d092` |

输出仅为本目录 report.md/json；ROOT 负责汇总与后续 Astra 规划。

