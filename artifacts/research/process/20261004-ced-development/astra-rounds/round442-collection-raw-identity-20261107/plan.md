# R442 RawV3 采集适配 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: 沿R439 executing-plans inline。只改本轮新collector文件，不扩旧RawV3类型/enum或改变既有实际额度。

**Goal:** 修复尚未运行的新collector RawV3身份、purpose及流式帧适配错误，保持原始字段语义和完整可重建字节。

**Architecture:** 旧RawV3仅作为兼容原件结构，新operational envelope持有TEACHER_COLLECTION语义/真实私有能力与D来源。使用具名字段、明确hash基底和严格帧重建，不靠scope字符串授权限。

**Tech Stack:** 现Python、RawV3、OC1；本规划0产品修改、0测试、0physics/render。

**Spec:** R439–R441计划，现raw_episode_v3.py和VisualRawRecorderV3合同。

## 原始静态冲突

新 `native_full_horizon_recorder.bind_collection_source` 构造source_kind=`TEACHER_COLLECTION`，但旧RawEpisodeIdentityV3 Literal仅SOFTWARE_ONLY/ONLINE_CED/GROUND_TRUTH_TEACHER，故尚未运行就已知不兼容。其位置参数又把asset_sha写到scene_hash、source_generation写到asset_hash、protocolsha写到config/model字段；即使碰巧都是合法SHA，也不是正确语义。

同一旧结构适配根因：T1内部runner使用FULL_HORIZON_HOLD，旧recorder.purpose只接受SETTLE/WAIT/VERIFY_ADVANCE/HOLD/TERMINATION；fake测试允许不说明真实base兼容。流式_record_frame当前把完整ENCODED_FIELDS表写入metadata，即使源值为空/缺失，也可能暗示不存在的blob；instance数据缺失默认空数组也需保留“未提供”与“实际为空”的区别。

原代码片段和输入SHA在intake；上述均静态发现、尚无执行失败。R439已有T1和T2 RED证据保留，不因本轮重新分配次数。

## 精确身份映射

仅新 recorder/应用/collection模块构造适配，使用RawEpisodeIdentityV3的**keyword参数**，不再按位置：

|字段|绑定来源|
|---|---|
|attempt_id|`attempt-`+digest({实际当前SQLite唯一open attempt完整源记录, lease_id, 原lease acquisition身份})；冻结原始基底并保存|
|assignment_id|预注册的唯一assignment ID，首组native-r439-0001；与实际job assignment一一join|
|assignment_hash|digest({registered_assignment:协议中该组完整原记录, simulation_job_assignment:真实job不可变assignment字段})；不是全protocol hash|
|episode_id|同唯一backend真实RESET episode，与original.owner_identity一致|
|source_kind|GROUND_TRUTH_TEACHER，作为旧schema“离线有真值标签的教师资料”兼容类别，**不表示动作由truth生成**；新envelope必须明确控制参数来源PIXELS_PROPRIO_REGISTERED_CONSTANTS、truth用途OFFLINE_LABELS_ONLY、source_scope TEACHER_COLLECTION|
|owner_identity|私有live应用核验当前worker/lease/attempt/backend后签发的original.identity；不能从caller描述授活权限|
|scene_hash|旧raw_recorder_v3._digest(实际本次已观察RESET `_reset_metadata['scenario']` 完整payload)|
|asset_hash|实际本次RESET `_reset_metadata['asset_hash']`，并与R440 outboard_v3 SHA/实际文件复核一致|
|config_hash|旧raw_recorder_v3._digest(实际本次RESET `_reset_metadata['config']` 完整payload)，含显式model_path/dt/render/camera配置|
|role_bundle_hash|新教师角色descriptor的原digest，即original.role_bundle_hash；保留其无云模型、非线上角色资格的语义|
|model_snapshot_hash|None；本角色无模型，禁止protocol/source_generation/全0代填|
|source_hashes|实际完整recorder.source_hashes，与original.source_hashes一致并按原base复核|
|clock_domain_id|该recorder原 `_clock_domain_id`；旧MONOTONIC/UTC descriptor原样。新BOOTTIME domain另存operational envelope，禁止混用|

`simulation_job_assignment`字段沿现base.bind_worker_source使用job_id/run_id/batch_id/backend/scenario_id/control_mode/seed/manifest_id/reproducibility_hash/draft/manifest；把实际组映射保存在source-binding，reader同基底重算。model=None在GROUND_TRUTH_TEACHER原schema合法，ONLINE_CED则要求完整模型，不能假称ONLINE_CED或SOFTWARE_ONLY来躲过来源要求。

该legacy类别不单独证明真实teacher来源；新reader必须额外强制每个物理action存在同源像素/本体grounding（旧RawV3仅对ONLINE_CED强制，不能利用该差异省略本采集器grounding），并独立校验私有应用的原件链、assignment/lease/RESET和D事件。无新envelope/确切控制来源说明则UNKNOWN/infinity，不按legacy标签升格成truth驱动成功或native。旧UTC未知保持。

## FULL_HORIZON_HOLD 适配

新NativeFullHorizonRecorder覆写purpose上下文管理：仅输入`FULL_HORIZON_HOLD`映射到`super().purpose('HOLD')`，返回同一个原interval ID；其余输入直接交base原校验。不改旧_PURPOSES、不放宽未知字符串、不改T1已测runner/fake行为。

在新envelope/receipt保存`semantic_kind=FULL_HORIZON_HOLD, raw_kind=HOLD, interval_id, action_span_id, registered_horizon_hash, dispatch/return/terminal steps`绑定；分配发生在推进之前。reader既检查legacy HOLD也检查该语义映射与fullH窗口，不能把任意历史HOLD当完整padding。失败仍保留partial interval和原动作结果。

## 流式帧完整性限定修复

- 仍用单一base callback形成原frame，然后新子类spool。保存**每个字段实际状态**：缺key/None/有效encoded string分别保留；metadata中的encoded_fields只列实际成功写入blob的字段，null留在原observation payload，observation_payload=None不得构造空RGBDObservation。不可在reader自动补缺原mask/图片使坏样本通过。
- 成功frame来自base的规范RGBDObservation序列化，三个encoded字段应都有有效值；保存blob后用base64.b64encode检查能逐字符恢复原规范字符串，保存原字段字符串SHA。非规范输入可原样保留字符串作为额外原件，不能悄悄规范化；本collector非规范/不完整frame一律留失败不合格。所有非图像metadata原样保留；还原后`model_dump`与原frame payload完整相等，包括checksum、camera、capture、source，不只校验图片字节。
- instance_ids按原顺序/有符号little-endian i32完整保存；instance_labels保留原映射、ID/背景标签不伪造。另保存`instance_ids_present`/`instance_labels_present`/原count及`instances_available`。成功全组要求真实count=width×height、原标签与实际IDs一致；缺失/空数组原样记录为缺失，不能用0填充。instance数据只离线使用，不进入grounder。
- camera_state_payload、joined_physics hash、pass_state_hashes、input_role、source_acquisition_id和transform字段全部保留，不丢到仅observation_id/checksum的live小索引里。live索引可小，独立reader必须从完整原source-frame+blob重建，不调用base.build_records直接把缩减payload当完整RawV3。
- 帧source metadata本身、所有实际blob和partial写入也纳入inventory；blob/source metadata任一步失败，已分配acquisition与已写文件保留，frame_source缺项、observer/audit失败使该组incomplete/infinity。禁止重写、补采或遗漏分母。无需在本轮创建另一数据格式/第二记录器。

## 文件、验证和验收

允许只在R439新 `research/native_full_horizon_recorder.py`、`native_collection_application.py`、`native_calibration_collection.py`、`native_full_horizon_originals.py`及对应已允许新测试内实现。应用文件目前尚不存在，不假定recorder_source已实现；本表明确它必须供应的原始数据，缺少就创建该已计划接口，不能以假SHA代填。旧raw_episode_v3/raw_recorder_v3/资产/tracker/worker schema不修改。

- [ ] 原bug片段冻结后，以keyword构造身份，来源基底真实完整落盘。协议/role/scene/config/asset/model各自独立，reader逐项重算。
- [ ] 未运行的T2 GREEN增加真实base类+fake backend软件fixture：identity构造及bind_source成功且modelNone；source_kind非法仍由旧类型拒绝；交换scene/asset/config或用protocol作model被新校验拒绝；role/owner不符拒绝。没有MjData/renderer/真实physics。
- [ ] 同T2 GREEN验证FULL_HORIZON_HOLD→唯一HOLD interval、semantic receipt关联、任意新kind拒绝、异常原件保留；不用重跑T1。
- [ ] 同T2/T3已有GREEN新增帧roundtrip：成功完整RGB/depth/mask/instances/labels/camera等全payload一致；None/缺field/缺instance、blob篡改、missing source-frame、mid-write失败、缩减live索引无法冒充原件；每分配frame都进入分母。独立reader不能信teacher/source标签或finite caller分数。
- [ ] 保持R440精确deselect及R441 UNKNOWN语义；继续原t2-green、t3-red/green、最终回归/static、一次fresh review和原唯一0001actual/read。无额外测试阶段、RED重跑、physics/render额度；若发现别的新根因停止相关修复再Astra。

本修订验收是新源与旧原件结构兼容且身份/帧语义真实，不是完整H实际成功、有限校准界或native资格。当前实际计数仍0。自审已检查legacy source_kind语义不渗透控制、no-model保持None、hash字段不可互换、purpose不扩enum、streaming缺失不被合成数据掩盖。
