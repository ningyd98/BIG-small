# R431 Full-H 原件精确关联修复 Implementation Plan

> **For agentic workers:** 使用 superpowers:executing-plans inline。已授权继续研发；仅下列两个文件及本轮证据，遇计划外失败回交实际 Astra。

**Goal:** 修复独立评审 F1–F3，使 STRUCTURALLY_COMPLETE 不再接受缺少 COMMAND/CAPTURE 分母、错误父子时序或畸形返回原件。
**Architecture:** 保留入口 `audit_completion_horizon_originals_v1` 及现有输出形状；扩充内部严格校验和全量关联，保留每个原件分母及失败。以七个独立反例和忠实手写正例验证。
**Tech Stack:** 现有 Python、RawV3 校验规则、ClockTupleV2、R413 supervisor/R235 plugin；无依赖变更。
**Spec:** 本轮 intake/observation.json 与 R429/review/independent-astra-review.md/json（pins 见 plan.json）。

## 证据、根因与范围

HEAD aecf1fd836ff08819edb053a2e87b4b2a83235b0，研发分支 research/20261004-continuation。评审证据为静态路径发现，尚无执行反例；保留 R429 原 84 PASS 与 R430 三项静态 PASS，不能将它们外推为已覆盖本轮缺口。

F1：COMMAND 仅作单行 membership、CAPTURE 仅比较 frame/allocation 列表，遗漏 END 中额外返回和没有 frame 的操作。F2：purpose/attempt 的实际 clock 未与子操作或 preopen/terminal 关联。F3：只验字段名/record_seq，缺完整字段类型与语义，bool==1 和截断 ActionResult 可被接受。

**纠正旧事实：** backend._operation_result 先建立 physics_state，COMMAND 再追加 command_records；此前“缺 physics_state 因而不能 MARK”的判断错误。begin_event 也接受非空 kind。这只是静态源码事实，未实证 live COMMAND 签发。本轮报告明确纠正，旧计划不改。真实 producer 仍未交付，依据是 source-only bind 限制、旧 step120/no-action verifier 范围以及尚缺真实 full-H 执行守卫，不能重复错误原因。

允许修改仅：`src/cloud_edge_robot_arm/research/native_completion_horizon_originals.py`、`tests/test_native_completion_horizon_originals_v1.py`。精确 rational kernel、另一个测试、RawV3/clock/backend/recorder 实现及所有历史原件不改。实施前复核全部 pins 与 intake/source-originals；后续两项允许变更使用新阶段 pins，不篡改 preimage。不得伪造 RawEpisodeIdentity、私有 owner 或证书来调用旧验证器。

## Task 1：忠实正例与七个预期 RED

- [ ] 在现有 test source fixture 保留 dispatch120/return121/terminal123、原 1+2 execution/HOLD、原几何/控制/owner 数据。COMMAND END 添加实际布局的 physics_state=该步骤原 state；既有 CAPTURE result 已保留 sensor/pass 数据，不把测试称为真实录制。
- [ ] 改 fixture clock builder 为独立 legacy MONOTONIC counter：每次区间开/闭产生唯一 ClockTupleV2 payload 并追加 legacy_clock_pairs；采用新 synthetic legacy domain，不混用 D domain。父区间先开、子操作各自开闭、父后闭；settle 在 before capture 前闭，before capture 后才开 attempt，attempt 闭后开 HOLD，HOLD 闭后终态 capture。按真实调用顺序分配全局唯一 sequence 和有序非重叠 mono brackets，所有 interval tuple 与 tee 精确相同；不要再用 D seq 充当 legacy pair seq。UTC 原字段保持 aware UTC，但不以 UTC 大小证明单调性。测试辅助函数只造软件原件，不调用被测审计器生成期望。
- [ ] 新增参数化 `test_review_counterexamples_require_incomplete`，恰好七项 ID（见 plan.json），都先断言 INCOMPLETE，再断言精确原因、原分母未缩减，最后 UNKNOWN/UNAVAILABLE/NOT_PROVEN。沿用正例 `test_complete_handwritten_originals_keep_unknown` 并增加 tee、COMMAND state 的 fixture 自检，不新增无关测试节点。
- [ ] F1a/b：在最后 HOLD COMMAND 的 END.command_records 追加 distinct seq=3 的形状完整命令，分别 accepted=true 与 false；不加 legacy_commands 行。拒绝 joint_target 需按 RawV3 去掉 applied_target_positions_rad，reason=`R431_REJECTED_ORIGINAL`。其他字段合法，不改旧原件。期望 `command_result_inventory_mismatch`；b 必须 original_failures 含原 rejection 完整记录/operation ID。
- [ ] F1c：在 HOLD 的122、123物理步间插入合法 CAPTURE，backend BEGIN/END、D event、legacy operation/interval 和 clock tee 齐全，D 与各 ID/引用分别一致重编号；其 sensor/physics/camera 内容来自该真实形状步骤。故意不加入 frame 和 allocated_acquisition_id。期望 `capture_event_inventory_mismatch`，original_failures 保存缺失 acquisition 的 operation ID；allocated count 仍忠实为2，不把缺件假造为已分配。
- [ ] F2a/b：分别将 HOLD start/end 移到 terminal 之后，或 attempt start 移到 before capture 之前，其他 step/目的/控制不变。**同时更新对应 tee 并一致重排 legacy pair sequence/引用**，保持所有 pair 本身合法、全局有序和精确相等；防止只因 tee 错配掩盖真正 containment 缺口。期望分别 `purpose_clock_containment_mismatch`、`preopen_attempt_clock_order_mismatch`。
- [ ] F3a/b：仅截断 returned_result 到评审四字段，或 action.attempt=True（prereg 仍 int1）。期望 `invalid_action_result`、`invalid_action_attempt`；allocated_action_count==1，保留可辨识原动作和错误，不以顶层 ValueError 代替。
- [ ] 一次 RED 跑七反例+原正例共8项。预期 setup/teardown全部PASS，正例PASS，七反例仅在 coverage 应 INCOMPLETE 实为 STRUCTURALLY_COMPLETE 的断言失败；不接受 fixture 异常、解析失败或无关理由作为 RED。保存失败后才改产品。

## Task 2：严格原件门与单次 GREEN

- [ ] **内部严格字段层。** 新增私有 helpers（名称由实现者统一），在读子记录前逐条校验，无 fake identity 构造。复用 RawV3 的 `_integer/_identifier/_number/_sha/_snapshot/_sources/_transform/_owner_decode` 等纯校验，必要时局部显式实现 identity-free 规则。整数严格 type=int（bool 拒绝）；数值有限；ID/hash/string/mapping/list/enum/nullability 严格；五类 record 的所有字段均检查，不用 Pydantic 默认值补失字段。区间 kind/disposition、全套 end 字段一致、clock tuple 四项类型、非负 step/sim、error 均检查；physics 的两 snapshot/IDs/hash；command 的 type-specific exact keys、accepted/after_emergency_stop 严格 bool、vectors、seq、effective step与拒绝语义；frame 的完整 RGBD/camera/hash/source/transform/input_role 字段；action 的 attempt/command range、完整 owner/grounding/compiled、disposition/error。
- [ ] ActionResult 必须 exact `ActionResult.model_fields`、success bool、duration_ms 非负严格 int、aware started/finished且不逆序、details mapping、physics_steps 严格非负 int、其他字段按实际模型验证，禁止缺字段默认填充。TaskStep/owner payload 复用现有纯 decode，但不授能力。可识别列表子记录 malformed/缺字段→新增结构理由并保存原行+索引/ID于 original_failures；记录未从原始列表删除、分配计数不变。根 JSON/顶层schema/原文件hash 等原 ValueError 合同不变。独立行失败不阻断其他原件失败保留；派生索引可排除无效行但其缺口必须使 INCOMPLETE。
- [ ] **COMMAND 完整一一关联。** 从每个 COMMAND END.command_records 取有序原返回清单，按 `(operation_id, command_seq)` 与 legacy_commands 的 interval→event 精确双射；验证每个 payload 全字段相等、全局 command seq 唯一有序、无重复/多余/遗漏。不要假定一 operation 恰好一 command，允许源格式真实多个，但都必须进入库存与后续 replay/归属。BEGIN/END/legacy interval 的 step、episode、参数保持现有核对；COMMAND result.physics_state 必须完整 snapshot 并等于同一步原状态。原返回里 rejected/error/after-emergency-stop 以及无法映射记录都保留，不能仅遍历 legacy_commands 保留失败。
- [ ] **CAPTURE 完整一一关联。** 穷尽整个原件中所有 CAPTURE D 操作（含窗口内额外 capture），按 operation_id/acquisition_id/interval 精确关联 backend、legacy_operations、frame 和 allocated list。成功直接采集必须恰好一条原 frame；重复、缺失、pending、额外、源ID不一致均INCOMPLETE，并保存缺件 marker含 operation/acquisition ID。全部成功 frame 都执行既有 sensor字节/RGBD/state/camera/pass 重建，不只 before/terminal。当前支持域仅原直接 capture；derived transform 若不能按已有完整来源规则证明则明确 unsupported+保留，不能套到一次物理 CAPTURE 或把它删掉。allocated counts 仍报告原实际列表；缺项另在 original_failures 记录，禁止伪造分母。
- [ ] **同域时间关联。** 用 ClockTupleV2.from_payload 验证所有 legacy_clock_pairs：同一 legacy domain、sequence唯一按源顺序连续、mono bracket 有序非逆，interval tuple 必须精确映射到库存中的唯一 pair。每个实际区间 start/end 使用不同 pair；legacy_operations 的 row 是同一 interval 的别名引用，不能重复计为新时钟事件。额外合法 RESET/read tee 可以存在，不能仅因未被区间使用而删去。对每个 parented operation（含 COMMAND/CAPTURE/CONTROL/PHYSICS），要求父start严格早于子start、子end严格早于父end，seq严格顺序及前者mono_after<=后者mono_before；unbracketed-operations 不是伪父区间。所有 step目的关系继续独立核对。
- [ ] before CAPTURE的legacy end < attempt start < attempt end；attempt/HOLD/WAIT各原区间顺序与原控制阶段一致并在 terminal CAPTURE legacy start 前结束，尤其 return后才开始额外 HOLD/WAIT。preopen条件用这些原 tuple，移除原过滤后恒真检查。操作 ID 将 legacy operation 与 D event 绑定；分别在 D域核对 event order/原 receipt，在 legacy域核对 MONOTONIC顺序，两种顺序须对应，不比较它们的数值 ns/sequence。UTC只验证/保留，不能借跨域加减产生 containment 证书。
- [ ] 保持所有 authority 固定字段和输出结构。除七个已命名新理由外，其他严格字段错误采用稳定 `invalid_<record_kind>_record:<id/index>:<field>` 理由；临时无法继续计算的派生步骤保持 None/空诊断与INCOMPLETE，不把异常转为成功。全部原字节hash和失败分母仍可检查。
- [ ] 一次 GREEN 按 plan.json完整列出的原84节点选择（新 reader测试文件本身现含额外7项），预期共91项全部setup/call/teardown PASS，无skip/drift/遗留进程。不得把新测试文件再加一次重复跑。随后三项聚焦 Ruff check/format --check/mypy，用 R430相同四文件/两源 argv，各一次60s，全部0。

## 运行前置、阶段 pins 与验收

RED/GREEN 使用不变 R413 supervisor、R235 startup/event plugin，独立 fresh目录和basetemp，各 timeout_s=600、attempt=1，显式 --junitxml。沿 R429现有环境，不跑全套、不安装、不调用模型/网络/硬件/MuJoCo。

input_pins 是本轮**实施前输入**证据，不能无区别并入已修改源码的运行冻结表。实现 wrapper 从不变 R429 intake/runtime-source-baseline.json 的1317项开始（409src原环境）；确认两可变新文件不在其中。将所有历史 plan/preimage/snapshot 路径原 SHA作为不可变证据；两可变逻辑路径单列 phase-source-pins：RED=原 reader SHA+新增fixture/7tests SHA，GREEN=修复reader+同一已冻结测试SHA。其余新kernel/test保持旧SHA。运行manifest每逻辑path恰好一条当前phase pin；不得覆写baseline/旧manifest/plan输入pins，不得冲突后以字典后值覆盖糊过去。记录 preimage→phase的授权映射；phase开始后任何漂移均失败。

本轮计划、wrapper、测试及原件快照在执行前冻结。保存每阶段spec/前置pins/stdout/stderr/events/JUnit/result及静态输出，步骤报告把软件修复、实际运行、正式研究分别列明。验收仅=三个评审缺口关闭+91软件PASS+静态PASS；所有 live/full-H producer、实际控制/校准/正式资格仍 NOT_STARTED/UNAVAILABLE/UNKNOWN。旧 source-only真实前缀与旧UTC/e/v语义不变。

新根因、范围扩大、RED偏离声明、GREEN/静态失败、超时、pin漂移须立即暂停相关修复交下一实际Astra，保留原始失败，不重试/加时/删测试。完成后按用户已授权明确路径提交推送并核对local/upstream/remote SHA，不动受保护dirty gitlinks。planner只写本轮计划，不实施或跑测试/Git。
