# CPU recorder 离线适配器：补齐原始上下文

规划角色：项目指定 gpt-6-astra。状态 PLAN_ONLY；父轮 CPU 实验、输入静态补轮全部条件继续适用。

## 已查原始失败与根因

`measure.stderr` 的实际堆栈显示 run-01 warmup 首帧进入冻结 Native recorder，再进入冻结 RawV3._record_frame，读取 `operation["parameters"]` 时 KeyError。实际测量 JSONL 文件为0字节/0行，因此没有有效计时样本。输入静态补轮软件验证已通过；父代理/Sol 报告的242帧基线资格以已保存 preflight-before/原日志为据，本轮不把该资格误认为 recorder 适配器已通过。

检查现有工具：它已在 frame.event.parameters 保存从 source-frame.camera_state_payload 与独立原 physics state 重建的参数，却未绑定到 operation。冻结 RawV3._on_boundary 的生产构造有 `parameters=event.parameters`；其 _record_frame 读取 camera_state、physics_state，生成对应 joined hash。已检查后续 Native _record_frame 所需 capture role、实例 presence、pass_state_hashes、frame_sources、inventory 与 `_frame_aux` 生命周期。不能用缺省空 dict 绕过真实状态。

## 允许修改

只改父轮 `benchmark_original_frames.py` 与其测试及本轮报告。不改任何冻结或当前产品 src、历史 run-01、父计划、输入解析豁免、采样/身份/门限、预算、统计设计。

1. 在离线 operation 构造中按原 `_on_boundary` 合同绑定 `parameters=frame.event.parameters`。逐字段验证 camera_state 与原 source-frame、physics_state 与原物理状态/已存 joined hash 一致，operation_id/acquisition_id/interval_id/physics_step/role 对齐。禁止填猜测值、当前模拟状态或空默认值。适配器事件是从原件重建，不标成新真实 guard 事件。
2. 对完整被调用链做一次显式字段/上下文审计。operation 的 acquisition_id、row.interval_id、input_role、action（如分支实际需要）、parameters 及 recorder 序号、capture role、已发布标志、输出预算、inventory/frame buffers、frame_sources 等均列“原来源→适配字段→消费位置”。已有 `action=None`/`_last_returned_span=None` 等离线上下文只有证明所选分支不消费真实 action join 时可保留；若消费，必须从原 span/join 证据重建，无法证明即停止。无需模拟 owner/guard 时钟或真正推进操作。
3. 允许同一字段合同内的必要绑定补齐：例如 result.instance_ids/instance_labels 的键存在性必须服从 source-frame 的 instance_ids_present/instance_labels_present，不能把原来缺失的键一律补成空数组而改变 metadata；实例值、pass hashes 仍取原件。此授权仅补齐实际冻结 `_record_frame` 路径所消费的原有字段、存在性和最小上下文，不允许为了通过比较删除输出字段或扩大忽略列表。若发现不同根因或来源不可重建，停止另交 Astra。

## 先完整预检，再恢复配对

保存旧工具/异常的真实 SHA。新增定向 RED 覆盖缺失 parameters、错误 camera/physics hash、错 operation/role，以及实例键存在性不符；必须由适配器前置/独立比较明确拒绝，不能吞异常继续。

三角色（REGISTERED_PER_PHYSICS_STEP、IMPLICIT_SENSOR_CACHE_UPDATE、REGISTERED_ACTION_BOUNDARY）各选择最早的真实 acquisition，预登记其路径/哈希/role，每类 A(level6)、B(level1)各一次，共6个非计时 recorder 调用。使用冻结真实 RawV3→Native `_record_frame` 完整路径，从构造、写出到独立读回全部结束，不用 mock recorder 代替正控。正控覆盖实际后继所需的全部字段与上下文；对涉及分支缺少代表性的情形，用原帧增加必要小预检并列理由，仍不计时。若超出本参数合同，停止。

A 的 RGB/depth/mask/instances、完整 source-frame metadata 和 payload/hash 对原件严格等值；B 只允许父轮已经指定的 PNG编码及其派生 checksum/hash 差异，像素、其他文件、身份/校准/角色/状态完全一致，输出独立重算 SHA。三类结果均保留独立读取回执、文件清单、差异列表和总输出字节。预检输出使用新的唯一目录，遵守父轮输出限额，检查剩余空间；不写或替换原目录。

重跑原12项测试与新负控、工具 Ruff，重新核对父轮29+1212输入、冻结/保护清单、原始1228 inventory、实际导入。三角色6次完整预检全部通过后才新建 run-02，重新执行原 prereg、预热和原完整配对；不得续接 run-01 或将预检记入性能样本。输出文件不得覆盖。计时、CPU/内存/4GiB输出/10分钟/6GiB余盘约束、顺序、样本、四块、独立验证及零模型/模拟/真机/正式组一律不变。

## 验收与边界

本轮成功仅指冻结生产 recorder 对实际三类原帧的完整离线适配和独立读回可用；没有本轮新增物理/正式研究次数。只有之后原配对实际完成才能报告 CPU 结果，仍不能证明完整动作8秒通过。保留 run-01、首次失败与所有 RED；生成步骤报告、输入/输出/软件 SHA，并入父轮。任何下一异常按新问题处理，不以本轮 plan 进行无限循环补丁。
