# Phase 6 LIFT POST 停止的只读复核计划

gpt-6.2-astra · 2026-11-22 · 研发基线 `6a26ac812f1c215c35031a80e3848252ce3c52e7`。

首组 `native-p0-v10-20261121-0001` 的一次授权已经消费。此计划仅使用这次运行已冻结的数据和基线读取器，供阶段报告核实停止原因。

## 规划时已核对的原始证据

- 同一 teacher 首组唯一 claim 已消费。正式命令 567.965136658 s 后退出 1，worker BLOCKED_BY_ENV、1 attempt。最终 COLLECTION_PARTIAL，3 个动作通过后置准入、4 个动作 span 已返回、8 个 PRE/POST 决策；6240 个物理步、28464 次渲染（EXACT）。LIFT 后没有派发 MOVE_TO_REGION。
- 原 LIFT PRE 允许；dispatch=4200，controller_return=5155，terminal=6240，receipt.complete=true。LIFT POST SafetyShield 为 ALLOW；抓持反馈 PASS、TCP 目标距离 0.01539725840100449 m（容差 0.02 m）。控制器记录 measured_tcp_lift_m=0.1023234572038924，contact_hold_s=0.5，completion_evidence=TCP_LIFT_AND_BILATERAL_CONTACT_ONLY。
- 末帧 acquisition-11109 的两个颜色事实均为 rgbd_estimate、value=null、identity_confirmed=false、extent_complete=false、measured_values={}、reasons=[color_identity_ambiguous]。两个 verdict 均 UNKNOWN/target_identity_uncertain。object_held 为另一条 UNKNOWN，满足 POST_LIFT_HELD_INTERFACE。本次决策 whitelist_rows 只有该行。唯一停止原因按顺序为 condition_not_admitted:object_lifted、condition_not_admitted:object_stable。
- 冻结原合同 LIFT.success_conditions=[]，二者均为 DEFAULT_POSTCONDITION；合同末步显式 completion_criteria 为 object_placed 与 placement_stable。collection_unknown_row_v2 优先排除显式要求与非 UNKNOWN，随后查 collection_unknown_row 的严格原因组合。LIFT 可用的深度/连续性行先要求 verdict=[visual_fact_not_boolean]；实际 [target_identity_uncertain] 已不匹配。bootstrap.depth_error_bound_m=null 不会独立触发 POST_LIFT_DEPTH。
- 原 B 帧 acquisition-123、目标像素 (179,119)，相同色度阈值重算末帧：两个候选，各 9 像素，边界框 (171,113,3,3)、(171,124,3,3)；原算法要求恰一个候选。并行 marker/注册模型 tracker 的同帧 preview DERIVED、region FULL_NOMINAL、object_surface_visibility UNKNOWN、geometric_error_bound_m=null。此证据独立于颜色身份判断。导致像素分裂的具体遮挡/材质原因待证。
- 模拟器只读样本：step 4200 与 6240 物体中心高度从 0.03499649486802247 到 0.12021317761649529 m，增加 0.08521668274847282 m；末物体底面 0.08426971324777345 m。区间 [5035,5155] 是控制器内建保持，[6120,6240] 是终步前 0.5 s；各自物理步样本最大 |v| 为 0.03484365033834153 和 0.005277752166152889 m/s，最大 |ω| 为 0.08890672399987981 和 0.06502908788178512 rad/s。窗口不同、结论须分列。在线 RGB-D 证据没有经校准的全区间速度上界或解开对称姿态的证明。

[机器可读计划](plan.json) 列出原始运行、协议、源代码、像素输入和监督证据的逐文件 SHA256。

## 复核步骤

### 冻结身份与失败边界

- [ ] 先复核正式 claim 唯一、原件/协议/登记源码及本计划输入哈希、正式进程已经退出。将 startup、worker 的 job/attempt/lease、collection-body-result、final result、stderr 与原时钟分域核对。主线程既有 inventory/DB/官方离线读回继续独立完成，可直接引用其 SHA 与结果。只读打开原件，派生结果写单独私有目录。禁止清理、补写、替换原件、编辑产品、续租或新建正式/诊断运行。

### 原件链与两个判断

- [ ] 对照原 4 个动作和 8 条准入，按 step/skill/phase/dispatch/return/terminal、原合同、binding、receipt、acquisition、observation、source_generation 和 SHA 串联，终端为 acquisition-11109。分别保存 LIFT POST recorded facts、verdict、Shield 及 admission 原因。用基线原 evaluate_conditions、collection_unknown_row_v2/collection_unknown_row 与实际 PRE context/POST receipt、原 evaluation_at 与相应反馈重算。可利用 Phase 6 原计划中的只读前缀工具；逐项标注仅字节核对、真实重算、缺证/未复现。不可补齐缺失 TERMINAL 或重写失败投影。

### 颜色来源与标记来源

- [ ] 复核 bootstrap.json 和 tracker-clock/bootstrap.json 绑定的 B 帧；从原 PNG 拿 (179,119) 的归一化色度，按当前 OpenCVTargetTracker._geometry 的 RGB 色度距离 <0.14、通道极差 >30、8 连通且面积 >=8 再计数。记录候选面积与边界框。末帧可重复读，禁止新采帧。将 registered_preview/registered_inputs、region、surface visibility、几何误差及原 condition source 分列，只从有像素或时间证据的原件归因。

### 物理诊断与阈值边界

- [ ] 从 physics[i].post_state_payload 核对实际 step、episode、简化链 SHA 与单位，区分 object center/bottom、TCP、finger/object 接触、线速度与角速度。核初始/dispatch/return/terminal，以及两段各含 121 个端点样本的 0.5 秒窗口。报告时间覆盖、物体高度变化及各窗口峰值；诊断时可比照颜色 tracker 的 0.05 m 视觉升高阈值、0.5 s 稳定性与 0.02 m/s、0.5 rad/s 的区间上界要求，保持模拟采样、连续估计、在线条件/研究资格的证据口径。不要从两张图或末态倒推持续稳定。

### 交付与后续授权

- [ ] 报告确认/未知表、证据指纹、官方 group/registry 读回和本地 raw 可用范围。已知原因可在本轮主报告交付；公开材料不含绝对主机日志、数据库、claim 内容及图片。保持全 9 组分母与 UNKNOWN，冻结 v9 与正式 v10 原件单独保存。若用户要求改进跟踪/新增证据源或协议，另需明确研发授权、Astra 另轮方案、隔离软件正负控和新源哈希。新仿真或正式试次需用户明示其模式、组/预算及新的正式登记，当次 claim 永久保留。禁止对现版本放宽白名单、降低阈值、以物理真值替代在线证据或重试已消费身份。

## 验收

原文件与指纹维持一致；以原始记录、原条件/白名单和可用冻结输入重算逐层解释 STOP；明确在线结果、离线物理采样和缺失证据，报告剩余 8 组 NOT_RUN，记录每项未验证情况与实际读回状态。
