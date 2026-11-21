# Phase 6 正式读回与逐条复核计划

gpt-6.2-astra · 2026-11-22 · 基线 `6a26ac812f1c215c35031a80e3848252ce3c52e7`。

已冻结权威协议/claim 与本次组原件，已有通过的 inventory 核查与首组官方诊断，匹配 456 项登记源码、当前离线解释器和足够本地读取空间。逐记录核验不需要渲染/模型/硬件/新 SQLite 作业。

## 已观察的失败与输入

- 官方 --verify 退出 0，表示写出了组与登记诊断。其首组报告明确 source_complete、geometry_complete、horizon_complete 均为 false。完整来源读回遇到 raw.failures 的 LIFT POST；raw.audit_failures、observer_failures、pending_operation_ids 均为空。
- physics 已逐项读取 24,029 个原区间、RESET＋6,240 个物理状态，随后在命令 428 拒绝。命令 1…427 分别由 attempt-1/2/3/4 负责，半开区间 [1,145)、[145,258)、[258,259)、[259,428)。428 为 hold_current_joints，429 为 emergency_stop，均在步 6240，有自己的 COMMAND interval/BEGIN/END、无 action owner，原 parent_interval_id 均为 unbracketed-operations，索引中没有该父。其 effective_from_step=6241，物理轨迹终止在 6240。嵌套 CONTROL 24020 在 STOP 的 BEGIN/END 内存在。
- 实际控制流 capture_each_physics_step → _execution_failure_scope → _close_execution_guard(error) → emergency_stop → hold_current_joints / _emergency_stop_observed / _apply_stop_control。原命令 428/429 分别是 operation-24018/24019，record_seq=41815/41818。外层 _collection_guard 此后进入 purpose-6 TERMINATION，record_seq=41819，ABORTED，原 MONOTONIC 时间显示它在两条命令结束之后才开始。raw_recorder_v3 在无 purpose stack 时如实登记 unbracketed-operations。清理操作原件存在，所要求的父区间关联缺失，不能把 purpose-6 指派为父。guard 末行 FAILURE 带同一准入异常，operations 的 clean CLOSED 谓词失败；最终 owner_closure.completed=true 是另一层资源释放。
- geometry() 在每个 allocated frame 上用默认 detect_pose_marker 单独核几何；最早报告的 acquisition-3451 为 step 2089 的 REGISTERED_PER_PHYSICS_STEP，位于 APPROACH。报告只列失败前 12 项，不能据此计算全部失败数。边界 E 上注册 SUBPIX 可用、完整几何失败、末帧颜色身份有歧义是三个独立观察。horizons、admissions 分别要求八动作、17 准入；实际仅四个 returned span/receipt 与八条 PRE/POST。metrics 依赖全组输入，lifecycle 直接保留失败。
- 旧私有 replay_recorded_pairs.py 在 audit.source() 之后无条件调用 audit.physics()。源代码足以预测在 428 终止；首次检查其运行日志尚空，应保留并记录真实退出，不能把预测作为已重算。登记 B=acquisition-123 与活动 tracker 的 E=acquisition-124，原 RGB 在 (179,119) 均为 [255,158,143]，独立重算末帧各得到两个 9 像素色块。

原始 CLI 错误文本与逐文件 SHA256 见[机器可读计划](plan.json)。

## 只读步骤与验收

- [ ] **只读核对原入口**　沿用已经完成的逐文件 inventory（55,583 项，6,578,143,222 B）与正在执行的直接入口结果。复核该清单指纹和本文所用原件。保存原失败、旧辅助脚本及最终 exit/log SHA；既有日志仍增长时仅记录时点，结束后单独封存。以具体 predicate 分别登记 source/physics/operations/geometry/horizons/admissions/metrics/lifecycle，无需再跑完整 geometry 或仿真。
- [ ] **原命令逐笔对齐**　逐个核 1..429 的 command_seq/record_seq、owner、命令自身 interval、父 interval 是否存在、command_payload、发生步/生效步。同动作四个 half-open span 对齐 1..427；从原 operational_events、backend_operation_ledger、control_sources、guard_events 对照 24018/24019/24020，分清 MONOTONIC 区间与 OC1 BOOTTIME。只报告原 parent，保留 FAILURE 终态。
- [ ] **建立受限读索引**　旧脚本和日志原样保留。新的本机派生脚本可使用 _Audit.inventory/source/physics 的原方法，在此前已经实测的精确异常处保留异常并确认 identity/original/domain/deadline 及 6241 states、24029 intervals 已由函数载入。若采用按需索引，先检查已核定 inventory 与 raw 字节 SHA，重验选用文件逐项 SHA/大小，验证原 interval ID 唯一、RESET/目标 state 链、原 physics/control 关系；不得自行构造缺失的 state/command/parent。完整 physics 门末尾的 validate_native_command_controls 尚未成功执行，保持全组 source/physics/operations 失败。
- [ ] **逐条相位和来源锁定**　从 action_span＋原 BEFORE_SUBMIT/AFTER_RETURN 两个 join＋原 horizon 与原 metadata 建立只读投影。动作 PRE/POST 帧依次为 124→3393、3393→6786、6786→7028、7028→11109。参考 B=123 与活动 E=124 各自核登记、lease、source、时间。每条仅用实际 step/skill/index/phase、span、recipe、命令区间、dispatch/controller return/terminal、原 observation/feedback/receipt 及指纹。phase 必须随 raw 顺序 PRE、POST 交替；POST 的上一 context 必须是本动作同一步 PRE，禁止跨动作或新造上下文。校验 _Audit.frame、registered camera、episode、physics/camera 对应、实际 pass 数与 guard。前后签名与 hash 不一致即停止该层。
- [ ] **最小组件复算**　验证原 Shield config/source/grounding/input/result 路径和 digest，调用原 admission_shield_v2 或逐相位原 pre_check/post_check，以原 recorded context、注册窗口、相对派发步和原时钟重算；记录仅用已存 context 重算的较窄范围。完整组件在足够原件下调用 registration_bootstraps、admission_grounding_v2、tracker_clock、registered_preview_v2、facts_at、admission_receipt_v2、admission_conditions_v2，逐行对照输出。只将方法已比对完 decision 本体后抛出的精确 recorded v2 collection stopped 异常计作该行 STOP 重现。若此层某行缺输入或前置失败，记录第一处差异和已完成行数；可独立验证仍有来源的 Shield/条件原函数与记录值，并标注依赖程度。不得 monkeypatch 判定、注入 PASS、合成时钟/链接/字段、删除尾部命令或用后相位使先前相位通过。
- [ ] **验收与交付**　公开报告列事实字段核对、Shield 独立重算、tracker 与多组件准入重算的实际分母，最多四对八行，无 TERMINAL。逐行 STOP/允许与 Shield 结论分开。固定 CLI/group/registry 原报告原样保留，UNKNOWN、空联合界及 8 组 NOT_RUN 不变。只封存本地派生脚本/日志/原输入，公开只有脱敏摘要和 SHA。任何更改原件、产品、guard/采集器/读回器或新试次均在本轮授权外。
