# T7 最终独立只读审查

最终复核时间：2026-10-03T16:20:52.517485+00:00。本次 execution/evaluation/smoke 审查仅阅读源码、运行 CPU 定向测试及复算已有物理记录；未重新调用模型或 GPU。运行时 worker/SQLite 的授权修复由本代理实施，另由 execution 代理独立复审，不将自行修改部分称为独立审计。

## 结论

**T7 开发 smoke 预登记门槛通过；本审查范围没有未关闭的 P1/P2 阻断项。** 对最终 `smoke-20-v2` 使用最新 `verify_smoke.py` 独立 CPU 复算：`valid=true, accepted=true, errors=[]`。20 个分配场景全部保留，2 个 NORMAL 场景成功，18 个失败，0 个环境阻塞；复算覆盖 34,353 个物理样本、154 帧、52 次实际动作。

**这不是正式 G1，也不是高成功率能力证明。** 全分配成功率为 2/20=10%；12 个 NORMAL 场景中成功 2 个。身份/区域证据、提升与稳定性等仍会失败；所有失败留在分母中。不能据此宣称一般语义识别、通用操作或恢复性能达标。

## 已关闭发现

| 原发现 | 最终复核依据 | 状态 |
| --- | --- | --- |
| P1：技能中途取消/超时丢失动作身份和计数 | action 前写 `ACTION_STARTED`；异常路径记录 `PARTIAL_SKILL_RETURN` 与真实物理步数，只要已有物理步就计入实际动作 | 已关闭 |
| P2：模型等待忽略较短 verification 截止时间 | `bounded_model_call` 使用 episode 剩余时间与 verification 剩余时间最小值，返回后再次检查 | 已关闭 |
| P2：审计未绑定输入哈希及 case 分类 | 实际校验 assignments/config/frozen bundle/source 哈希，逐 case 比对 assignment、kind、scene_hash，门槛按 assignment 分类计算 | 已关闭 |
| P2：空或不完整条件可冒充 online completion | 审计要求最终三条件集合恰为 object_inside_target_region、gripper_released、robot_in_safe_pose，全部 PASS 且 verdict 与 event 同 observation_id | 已关闭 |
| 指标口径容易误读 | evaluation 报告现显式 `invalid_depth_rejection_denominator=all_assigned` | 已明确 |

P1 原复现为真实动作 17 个物理步后异常，`executed_actions=0` 且没有 skill return；该历史问题已由上述异常路径记录和定向测试覆盖。P2 原等待边界不会造成迟到动作，但会超出较短 verification 墙钟预算；现已取最小截止时间。

## lift 与 RGB-D 边界过滤复核

- 提升后的 hold 真实推进 0.6 秒物理时间，每 0.1 秒采集一帧；稳定性依据多帧 RGB-D 中心位移、可见顶部高度及持续时间判断。
- 每个物理步检查双指持有状态。中途接触丢失立即终止，已发生的被动观测步数保留；不会仅在最终帧检查接触。
- 遮挡或缺视觉高度证据不会以 TCP 高度替代而 PASS。RGB-D 高度低于阈值仍失败。
- 深度过滤只排除与可信深度像素相邻、位于颜色掩码单像素边界的明显深度跳变。内部深度异常、独立出现的同色候选仍 UNKNOWN，不以“过滤”接受任意越界点。
- 仍属已注册 S01 资产与初始 VLM 像素的有限颜色/几何跟踪，不构成一般实例身份跟踪能力。

## 在线、物理、语义隔离

1. 在线 tracker 消费 RGB-D、VLM 像素、本体状态及自身历史；未发现独立物理结果或语义标签作为在线条件、规划或恢复输入。TCP/双侧接触可辅助时序预测，但不代替 `target_visible` 的实际图像与深度支持。
2. 物理真值快照仅累积到独立评价器。评价器首次调用发生在 online 终止后；`INDEPENDENT_PHYSICAL_RESULT` 为末层记录。
3. episode 成功要求 online complete、physical success 同为真且无 terminal reason。smoke 其后再与 assignment 派生的 semantic success 合取，MISSING_TARGET 不因搬动其它物体而成功。
4. worker 事后语义 helper 仅针对固定 S01 资产及完整允许句式评分；红块到绿区可 PASS，其它颜色 FAIL，未列句式 UNKNOWN。该结果在 online 执行完成后才应用，不反馈到 online 路由。红/紫两种 worker CPU 成功覆盖反例已通过。
5. 路由能力集合仅 CONTINUE/REOBSERVE/STOP，未提供恢复能力时不会虚构恢复。UNKNOWN 重采样实际消耗有限重观测预算；验证状态和绝对截止时间持久到 verification-state.json，不靠新帧重新开始预算。

## 审计脚本复核

最新审计正确重算独立 physical outcome、online/physical 合取、assignment 语义标签、最终 smoke gate；并检查物理评价末层、帧数量/唯一性/时间单调性/episode 归属、RGB/原始深度哈希、真实动作计数、STOP 后不再提交动作、事件 ID 与重观测上限。

本次实际命令：

```text
.venv/bin/python artifacts/research/process/20261003-t7-visual-closed-loop/verify_smoke.py artifacts/research/process/20261003-t7-visual-closed-loop/smoke-20-v2
```

退出码 0，输出 `valid=true, accepted=true, formal_g1=false, errors=[]`。其 source 哈希全部与 v2 provenance 匹配；worker/SQLite 的后续修复不属于该 CLI smoke 的执行源，也未被当作本次真实 smoke 所验证的运行时服务路径。

## 历史结果与指标限制

`smoke-20-v1` 必须保留为失败历史：20 分配、20 留存、0 blocked、0 success、0 NORMAL success，`smoke_passed=false`。当时 CPU 审计结果为 `valid=true, accepted=false, errors=[]`，覆盖 22,147 物理样本、105 帧、33 动作。不能用 v2 覆盖或删除 v1 的分母。

`invalid_depth_rejection_rate = rejected_depth / assigned` 是全分配样本中因深度原因拒绝的占比，不是独立无效深度样本的召回率。selection 既有五例为 1 成功、4 目标命中、3 深度拒绝、0 阻塞；3/5=60% 仅表达全分配拒绝占比。未基于这些 selection 结果调模型或改评测分母。

## 验证记录

- 初始只读快照：closed-loop + online verification 57 passed；当时 P1 已另外用 CPU 真实 execute 入口复现。
- 最终 engine 定向 CPU：`tests/test_rgbd_closed_loop.py -k 'lift_hold or temporal or depth_mixing or interrupted or deadline or initial_estop'`，11 passed、17 deselected。
- worker 租约产物隔离与语义合取：新增 6 个测试从 5 failed/1 passed 到 6 passed；随后 CPU 矩阵 67 passed、1 deselected。
- expiry/cancel/recovery/retry/STARTING 过期：6 个确定性竞态反例全部先失败后通过；取消前最终 episode 尚未写盘时预算 checkpoint 的发布反例也先失败后通过。
- worker 真实 datetime event/budget 的序列化已在 JSON-safe 整体转换后通过；测试中 asdict 自身复制 datetime 的身份断言由测试作者纠正，事件和结果的 ISO 时间值及输入不变性均保留验证。
- ruff 通过；worker/sqlite_repository/repository/recovery/state_machine 五个源文件 mypy 通过。该运行时部分由另一代理完成最终独立 CPU 回归与源码复核。
- 一次 CPU 矩阵排除项拼写错误，误包含 `test_capture_works_without_model`，该实渲染测试因无 DISPLAY 的 GLFW 初始化失败；随后正确排除重新通过。没有以该环境失败宣称 capture 功能已通过，也未启动新的 GPU 验收。

## 运行时发布异常追加修复

execution 代理另复现的 P2（终态产物写入 OSError 后数据库仍 SUCCEEDED、结果 task_success=false）已在本轮授权范围内修复：只在本次成功终态发布阶段发生异常时，以原 lease/worker/status 原子条件将自有 SUCCEEDED 改为 RECOVERY_PENDING。先修正数据库和 attempt、撤下可能过时的成功产物索引，并把已执行动作及验证记录存入数据库错误事件，再最多尝试一次归档写入。持续磁盘不可写时仍保持数据库 RECOVERY_PENDING、原错误和已释放租约；不声称此时磁盘已有一致产物。正常成功及已换主任务不被降级。

新增 `tests/test_rgbd_publication_failure.py`：瞬时/持续写失败两项先红后绿，正常成功/换主保护共 4 passed。最终定向 CPU 矩阵（publication_failure、lease_handoff、lease_control、runtime_control、worker_serialization，排除实际渲染 capture）为 55 passed、1 deselected；worker/state_machine ruff 与 mypy 通过。源码已停写并交 execution 代理最终独立复核，未修改冻结 engine 或 v2 smoke 来源。

## 最终审查快照 SHA-256

- `src/cloud_edge_robot_arm/vision/execution.py`: `5e341862000de281cebfe0981acf781eb23b2cd135e8e51db93e730dbeaddb5a`
- `src/cloud_edge_robot_arm/vision/evaluation.py`: `10b7d88d65413e454cad00d6f0da8f28be1747017d6baa6e75b1be1504eedbc5`
- `scripts/run_rgbd_smoke.py`: `80f11894799187022734016061f805ebaa381957cee6dc3f9c5edf3953697e02`
- `artifacts/research/process/20261003-t7-visual-closed-loop/verify_smoke.py`: `daee92c576a047da6a93c2ace83eb0735829282f35afa2146de601dfa930ebd2`
- `src/cloud_edge_robot_arm/vision/task_semantics.py`: `209f7682b3a192880218322efbcffdad891b017edbe9ed88d53d5b0c67010b29`
