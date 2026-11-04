# R431 独立 Astra 收口审查

**结论：原 R429-F1/F2/F3 的七个已定义反例已修复并有 RED→GREEN 证据；本轮仍不能声明全部收口。** 新发现一项 P2：畸形首行会提前终止原始失败扫描，遗漏后续合法失败。另有已单独规划 R432 的 mypy 静态失败，不能将当前三项静态结果写成全部通过。

## 独立性与版本边界

复用现有实际 gpt-6-astra reviewer，未参与实现；本次是对自己先前 R429 独立发现的闭合复核，不是新建会话。本轮只读计划、源码、测试和保存的证据，未运行测试/反例/产品/SQL/Git/网络；仅新增本 R431 报告及同名 JSON。R429 旧审查报告和所有历史原件保持原样。

当前 reader：`2e9605ef5bc9fba5f0a61c9f69d1fe6900111dc74958cb32f4ac57dec0726b5e`；当前测试：`59373c64838862d1bacd0823fd234a4fbd7b2be07c4032916fdbc984f00f6690`。两者与 pre-green-pins 实算一致。R431 plan 的 34 pins、intake 的 23 pins，只有明确允许的 reader/test 逻辑路径发生授权变化，其余匹配。RED/GREEN 运行清单各 1347 个独立路径，无重复逻辑路径；当前 GREEN pins 全匹配，RED 只有 reader 改为修复版本，测试 RED 后未改。HEAD/分支沿冻结计划上下文，按禁止 Git 的边界未重新查询。

## F1–F3 闭合判断

**F1：已关闭七例范围中的 COMMAND/CAPTURE 分母缺口。** 新 `complete_inventory`（459–568 行）逐操作读取完整 command_records，形成带 operation_id、command_seq、完整 payload 的有序 returned/recorded 列表并要求相等及唯一序列；没有再假定每个 COMMAND 仅一条记录。额外或 rejected/emergency 返回保留 operation ID 和原 payload。全部 CAPTURE D event 的 acquisition ID 与 frame/allocated 列表逐项对应，并对每个成功直接 frame 重建 sensor/RGBD/state/camera/pass 证据；缺 frame 原事件生成保留 ID 的 missing marker。derived capture 明确 unsupported。旧 membership 检查仍作为局部核对存在，但新完整清单检查覆盖其遗漏。

**F2：已关闭两个原区间时序缺口。** 新 `legacy_time`（570–656 行）读取 ClockTupleV2 tee，验证同 legacy domain、连续独立 sequence、mono bracket 顺序、每个区间 start/end 的唯一精确映射；通过 operation ID 将 legacy operation 与 D 事件关联，分别核对两域顺序，没有跨域 ns/sequence 数值比较。父 purpose 的起止必须包含子 operation，before capture 必须早于 attempt 开始，attempt 与后续 HOLD/WAIT 顺序且均早于 terminal capture。原过滤后恒真 preopen 断言已移除。

**F3：已关闭截断 ActionResult 与 bool attempt 错误接受。** `_action_result`、`_record_values`、`strict_records`（213–457 行）执行 identity-free 字段和语义验证，复用 RawV3 纯规则，不伪造 RawEpisodeIdentity、owner 或证书。完整 ActionResult 必须具有全部模型字段、严格 bool/int、aware 且有序时间、mapping 等；action attempt 严格拒 bool。可辨识坏行保留原始内容及位置并产生 INCOMPLETE，原始分配计数没有删除。

**COMMAND 源码事实纠正已落实。** R431 计划明确旧“COMMAND 缺 physics_state 因而不能 MARK”判断错误；新 fixture 的 COMMAND END 同时含 physics_state/command_records，正例自检该状态，reader 还将它与同一步物理原状态联接。此项是形状/源码事实修正，未证明实际 live COMMAND 签发，更未交付真实 full-H producer。

## 保存验证记录复核

RED：8 STARTED，setup/teardown各8 PASS，call为7 FAIL+1 PASS。逐项 JUnit failure message 均为预定 `STRUCTURALLY_COMPLETE != INCOMPLETE` 断言，七项 reasons 在该时点为空，完整正例通过；不是 fixture/import/资源错误。GREEN：91 STARTED，setup/call/teardown各91 PASS，JUnit tests91、failure/error/skip均0，pytest42.199秒；supervisor43.040308秒，exit0、reaped=true、errors/source_drift/remaining_live/ports_after均空。

新负例测试要求具体结构原因和保留分母；extra rejected command 要求原 rejection marker及 operation_id；缺 frame要保留未表示 acquisition/operation ID。时序负例同时重建 tee 与序号，未借 tee 错配掩盖 containment 失败。完整正例仍明确手写 SOFTWARE_ONLY，dispatch120/return121/terminal123、execution1+HOLD2，UNKNOWN/UNAVAILABLE/NOT_PROVEN 不变。未扩大到真实模拟、硬件或全 suite。

当前 R431 保存静态结果为 Ruff check=0、format --check=0、mypy=1。mypy三条错误集中在 legacy_time 局部名 pair 被用于 ClockTupleV2 和 list；父任务已将它交实际 Astra R432，只允许 alpha-rename、严格 AST 等价及静态复核。这里不重复列为新实质发现，不声称 R432 已完成；若之后修复，应另保存其结果和最终源码 hash，不改这份原 R431失败记录。

## 新 P2 — R431-F4：一条坏返回中断扫描，后续原失败没有保留

定位：`src/cloud_edge_robot_arm/research/native_completion_horizon_originals.py:671–678`，相关 415–457、1361–1380 行。

`retain_failures` 在一个无逐行异常隔离的循环里调用 `row.get()` 与 `result.get()`。若前一 action 的 returned_result 是 list/scalar，这里抛异常，外层按整个方法捕获后进入 strict_records；剩余 actions、intervals、backend 行不再扫描。strict_records 会记录畸形行，但仅作字段/语义验证，不会把后续形状合法的 success=false/ABORTED 原动作加入 original_failures。其他阶段也没有补回这些漏项。

最小有界提案（**未执行**）：从本轮完整 fixture复制，第一条 action 保持 error=None、把 returned_result 改为 `[]`；追加一条形状合法的 RETURNED action，独立 span-2/record_seq、完整 result.success=false、error_code及action.error为 `R431_LATER_ACTION_FAILURE`，并给 allocated_action_ids追加span-2。当前静态路径会保存第一条畸形内容，却漏掉第二条原失败标记。最终仍然 INCOMPLETE，分母可为2；问题是失败审计不完整，不是成功或执行权威逃逸。

R431计划明确要求“独立行失败不阻断其他原件失败保留”，因此这项不能用91PASS代替。下一实际 Astra应先限定逐行扫描与保留策略，再用一个组合反例验证 malformed原行和later合法失败都留在original_failures，保持allocated_action_count=2及UNKNOWN。只改新测试fixture，不修改原件；不需要全套重跑、真实模拟或延长timeout。原始F1–F3七例的修复结论保留，不因本项发现把过去GREEN改称失败。

## 最终交付判断

本报告确认原三项实质修复及相关测试证据，但暂不授予“所有原件失败均保留、整体阶段已完成”的结论；R431-F4需下一实际Astra规划，R432静态结果需另行收口。精确 rational kernel、旧整数/UTC/e/v、旧 recorder/guard未在本次范围中改变。actual/full-H producer、硬件、校准及formal native仍NOT_STARTED/UNAVAILABLE/UNKNOWN。

提交/推送及local/upstream/remote SHA核对由父任务在后续满足交付条件时完成，本审查没有执行这些动作。声明范围仅覆盖这里固定的源码、计划和已有结果。
