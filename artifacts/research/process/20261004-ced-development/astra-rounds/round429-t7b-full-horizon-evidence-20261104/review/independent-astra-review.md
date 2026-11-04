# R429 / R430 独立 Astra 首次审查

**结论：请求修改。发现 2 项 P1、1 项 P2；阻塞将 R429 原件覆盖门声明为已完成并作为通过交付。** 精确 rational kernel 和固定 SOFTWARE_ONLY / UNAVAILABLE / UNKNOWN 边界没有发现同等级问题，但 reader 仍有允许不完整原件集合获得 STRUCTURALLY_COMPLETE 的路径。请先由实际 Astra 制定 R431，再执行反例或修复；本审查未执行这些反例。

## 独立性、范围与版本

本次审查使用现有实际 gpt-6-astra reviewer。该 reviewer 曾审查 R419，本次为首次接触 R429，未参与 R429/R430 实现；没有新建会话，不把它称为新会话 fresh reviewer。所有结论来自本轮 plan/source/evidence，不沿用 R419 结论。

只读 AGENTS、R429 plan.md/json、四个新增文件、原始 RED/GREEN 事件/JUnit/result、静态结果及相关 RawV3/operation schema。未运行测试、产品代码、SQL、Git 或网络；仅写本报告和同名 JSON。HEAD `aecf1fd836ff08819edb053a2e87b4b2a83235b0` 是父任务及冻结计划给定上下文，审查者按禁 Git 边界没有重新查询它。

审查期间 R430 完成已单独规划的七处 E501 和一处 B905 静态修复；最终 reader SHA256 为 `2a10ca932c3c85213bc036aefce16431beb016cb9c218e16d7a0fe31024201f0`，GREEN preimage 为 `699345d11f97e6e0c70500f72b1894821707e44f27e44b6ec073a5ab07bf074a`。以下行号均按 R430 后最终文件。R430 ast-equivalence 记录仅一个邻接 zip 的显式 strict=False 差异，归一化后 AST 相同；其余三个新文件 hash 未变，三项静态命令 exit0。已知 lint 不重复列为新缺陷，也没有把 R430 的静态验证说成重跑 84 项。

R429 plan 的 12 pins 与 intake 的 18 pins 均实算匹配；GREEN 的 1327 pins 当前只有上述批准的 reader 静态变化。四个当前文件和审查输入的 bytes/SHA256 完整保存在本 JSON。

## P1 — R429-F1：COMMAND/CAPTURE 缺少原件分母的一一联接

定位：`src/cloud_edge_robot_arm/research/native_completion_horizon_originals.py:409–417`，另见 570–624、740–745、816–829。

COMMAND 仅比较“D COMMAND 数量 == legacy_commands 数量”，随后用 `payload in END.result.command_records` 证明一条 row。该 membership 不要求 END 中全部 command_records 都有唯一对应 row。追加到同一个 END 的额外命令既不增加 COMMAND operation 数，也不进入 legacy_commands replay、窗口外来命令检查或 `retain_failures` 的原始失败集合。因此在现有完整 fixture 的某个 COMMAND END 中追加第二条有效形状命令（包括 accepted=false 的原拒绝）并重打新 fixture 的 bytes/hash 后，静态路径仍满足现有全部检查；遗漏的记录可以被 STRUCTURALLY_COMPLETE 掩盖。

CAPTURE 有相同分母漏洞：`allocated_acquisition_ids` 只与 `legacy_frames` 互比，`frame()` 仅重建 sidecar 指定的 before 与 terminal；没有穷尽所有 CAPTURE D event。一个窗口内额外 CAPTURE 只要有合法 D/backend/legacy operation+interval，对应 frame 和 allocated ID 同时缺失，也不影响这两个列表相等；窗口 kind 白名单还明确允许 CAPTURE。CONTROL/PHYSICS 的完整事件集合检查不覆盖它。

有界提案（均未执行）：在当前 123-step 手写 fixture 上分别追加一个额外 accepted command、一个额外 rejected command；再独立插入一个窗口内 CAPTURE D（连同合法 backend 和 operation/interval 行，调整后续 ID/seq/token/bracket引用），但不给 frame/allocation。要求每例 INCOMPLETE，并让 rejected 原因进入 original_failures、缺失 acquisition 分母保留。新 test 原件可重新 pack；不得改任何已冻结原件。

修复规划要求：每个原 COMMAND/CAPTURE 操作及其所有返回 payload 与消费库存形成严格唯一联接，检查额外、重复、缺失、拒绝和 pending。不能通过删掉额外原记录或只统计选中的 before/terminal 达到通过。现有 UNKNOWN 权威隔离有效，但不能使错误的结构完整声明变为正确。

## P1 — R429-F2：EXECUTOR_ATTEMPT/HOLD 原区间时序没有绑定到子操作

定位：同文件 338–342、695–715、757–767、783–814、816–824。

原 interval 只要求 `start_step <= end_step` 与 `start[0] < end[0]`。后续执行/HOLD 归属依赖 step label、purpose ID 和 parent 字符串，没有把 attempt/HOLD/WAIT 的原始 start/end clock tuple 与对应子 operation 区间及 D 边界联接。`preopen_dispatch_order_mismatch` 也无法补足：window_events 本身已过滤 begin_seq > before.end_seq，随后再次比较最小 begin_seq，条件在非空时必真。

这允许原件自述“HOLD 区间开始于 terminal capture 之后”，但其 start_step/end_step 仍写 121/123，从而继续把 122/123 标作已覆盖 HOLD；或把 attempt 原 start clock 移到 before capture 之前，却仍接受预开窗口。上述只改变 interval 原 clock tuple 的反例，不需要改变物理/control payload、分母或 horizon。

有界提案（均未执行）：完整 fixture 的 HOLD start/end 改为保持自身顺序、但严格晚于 terminal 的一对原 clock；另例将 attempt start 改为早于 before capture、保留有效 end。重 pack 新测试原件后要求精确时序原因 INCOMPLETE。下一 Astra 计划需先明确 legacy clock pair 与 D 原操作之间可证明的关联；若现有格式无法证明，保守标 INCOMPLETE，不能用字符串归属补造闭包。

## P2 — R429-F3：RawV3 记录仅校验字段名，截断的真实返回仍可被接受

定位：同文件 930–940，另见 638–642、718–731；参照既有 `raw_episode_v3.py:698` 的 TypedActionSpanV3 校验。

新 reader 取 dataclass fields 只做 `_shape` 和 record_seq 验证，没有重建 typed record 或复刻其严格字段校验。action_window 对 returned_result 只读取 success、error_code、action_type 和 details.physics_steps。将完整返回原件缩减成这四项，缺少原 ActionResult 的 duration_ms、started_at、finished_at 等必要字段，仍没有一条现有检查拒绝。另一个单字段反例是 action.attempt=true：与 prereg integer1 的相等比较通过，违反原件严格拒 bool 的约定。RawV3 原 TypedActionSpanV3 本来拒绝这类输入。

有界提案（均未执行）：一例将返回内容缩成四字段（success=true、error_code=null、action_type=MOVE_ABOVE、details.physics_steps=1），一例仅把 action.attempt 改 bool true。要求按计划对可辨识动作缺件返回 INCOMPLETE、保留 allocated_action_count；严格语法错误是否抛 ValueError 由下一计划明确，不能宣称成功完整。应核对 action/command/interval/frame 所消费字段，而不把 dataclass 字段名检查当作其验证器已执行。

## 通过证据与测试不足的区分

独立解析原始记录：RED 为单项 call FAIL，setup/teardown PASS，保存的缺模块错误属于计划预期；GREEN 为 84 STARTED、setup/call/teardown 各 84 PASS，JUnit 84 tests、0 failure/error/skip、41.396 秒；supervisor 42.539 秒、reaped=true、source_drift/remaining_live/errors 空。25 新项 + 59 旧项这个事实成立；不因此证明上述尚未覆盖的路径安全，也不外推全 suite 或真实 full-H producer。

原 plan green_argv 只枚举两新和两个旧模块，但正文指定旧59。已读取执行前 progress 的旧59裁定及 R430 plan 的“R429 验证选项裁定确认”：59 为 metric10+originals35+calibration10+四旧负例。保留原计划枚举缺失的历史，不把实际 argv 称为与原枚举逐字一致；此歧义已有裁定，不另列未授权扩测缺陷。

当前完整例清楚标为手写 SOFTWARE_ONLY，COMMAND D 不是现有私有 recorder 真产物。多数反例修改后只要求 INCOMPLETE；没有覆盖 F1 的额外返回记录/缺 frame 分母、F2 的区间实际时序、F3 的严格子结构。下轮应保留完整正例并对每个新负例要求对应拒绝原因，避免一个无关缺口掩盖另一个。可以复用该小 fixture；不需要 MuJoCo、硬件、全量矩阵或放大 horizon。

rational kernel 对显式 ratio、实际 float hex 绑定、ceil、tail/wait 与 frozen 输出的实现和手算 oracle 一致；没有按声称的巨大 H 分配 range/list。reader 的步数库存遍历也以实际原件为界。producer_status、guard_status 和研究权威固定隔离正确，本次发现没有实际控制调用或生产权威逃逸；它们阻塞的是承诺的结构覆盖 gate 本身。

## 下一步边界

本报告是发现清单，不是修复实施计划，也不声称已有 runtime 反例失败日志。建议实际 Astra R431 以本报告、最终 reader、现有正例和 R429/R430 证据 pins 制定有界 RED/修复/GREEN；把 F1 的 COMMAND/CAPTURE 分母联接视为同根因，F2/F3 单列验收。任何执行或修复应在该计划保存并复核后开始。无需因 lint 再开新实质根因，也不要为审查改写旧 84PASS、RED 或源 preimage。

## 补充源码事实纠正（不改旧计划）

直接复核 `simulation/mujoco/backend.py:291–304`：`_operation_result` 先建立含 `physics_state` 的 result，COMMAND 分支随后追加 `command_records`。因此 R429 原计划关于“COMMAND 返回缺 physics_state、所以不能 MARK”的源码判断不成立，必须在新报告/R431 中明确纠正；旧 plan/证据字节保留。`research/operational_time_v1.py` 的 begin_event 也不限制为某几个 kind，仅要求非空字符串。这个静态纠正不等于 COMMAND 已经真实运行或成功签发，本审查没有做任何运行复现。

现有手写 fixture 的 COMMAND END 只含 command_records，应由 R431 规划将它对齐真实 result 布局（包括 physics_state），并审查 reader 对该实际状态原件的联接。full-H producer/guard 尚不可用的结论不依赖上述错误原因；现有 source-only recorder 的绑定限制、旧 prefix verifier 的 step120/noaction 范围以及真实执行守卫前置仍应由下一轮以正确源码事实逐项确认，不能宣称生产闭环已通。F1–F3 保留，不因该纠正自动撤销。
