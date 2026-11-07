# Fresh whole-change review — R439–R449

Reviewer: `/root/review_full_execution_calibration`, fresh context, no model override. Base/current HEAD: `8534419b7e22396985f66d1b0f2714fe8e16e5fb`. Read-only, no tests/probes/engine/render/model calls, no worktree/index/HEAD/gitlink mutations.

## Reviewer completed report

审查结论：**当前代码不宜放行首个 actual 组。** 发现 5 项需要修复的问题；其中真实背景像素会直接触发 reader 拒绝。

**Strengths**

- 完整 horizon 保留原 controller 结果，早成功后保持已有目标，失败不补样；LIFT 与 RELEASE 尾部明确分开。
- 私有应用通过真实 SQLite worker/lease 执行，原 OC1 任务起点在 enqueue 之前，单 assignment、单 attempt 与禁止重试的边界清楚。
- B/R/E 顺序及独立 B/E bootstrap 已落实；历史 tracker 重放使用记录的实际判断时间，live exact-type 门拒绝 archive adapter。
- canonical UNKNOWN、教师实验许可、物理结果和 native 资格保持分层。R449 原始证据确认 86 PASS，静态检查 rc0；历史失败仍保留，未冒充完整回归通过。

**Critical**

无。当前范围是有限教师仿真采集，没有发现直接授予 native 或硬件权限的问题。

**Important**

1. **[P1] 真实背景 ID 会被错误判为实例原件缺失。** `native_full_horizon_originals.py:587` 要求全部 instance IDs 都出现在标签映射中，但真实 `simulation/mujoco/camera.py:135` 将背景记为 `-1`，并明确从标签生成中排除 `-1`。注册相机视野大于有限桌面，真实三 pass 帧会包含背景，从而被拒绝为 `instance label original missing`，无法完成几何与 horizon 重建。现软件相机夹具人为提供 `{-1: "background"}`，掩盖了差异。应保留真实背景表示，仅要求非背景实例具有真实标签，不能补造标签。

2. **[P1] RESET 期间记录失败后，仍可能开始物理推进。** `native_collection_application.py:1186` 在安装执行 guard 之前调用 `reset()`。RESET 内的隐式 CAPTURE 若发生原件写入失败，backend 会保存并吞下 observer 异常；`backend.py:381` 只有在 guard 已存在时才把异常锁存为下一次拒绝。应用没有在 RESET 返回后检查 recorder/backend 的失败记录，随即进入 `step(120)`。因此已知 source 失败之后仍会产生新的 physics；一次性写入故障恢复后甚至可能继续整链。进入首步之前必须验证 RESET、隐式采集和 recorder 来源均无保留失败，并保证这些失败使最终结果降为 PARTIAL。

3. **[P2] reader 没有重放命令到实际控制目标的关系。** `native_full_horizon_originals.py:413` 仅验证控制方程内部一致性；命令循环也没有重放 `effective_from_step`、初始目标、joint clipping、gripper targets 或延迟队列。`control_interval_id` 未被交叉验证。这样，改变 HOLD 内 applied target 并同步改变方程输出后，即使目标已偏离原命令，新 reader 仍可能接受 source/horizon；普通文件哈希不能替代这种语义验证。原 `raw_episode_v3.py:1316` 已有对应重放。应在保留 legacy UTC UNKNOWN 的同时保留这些物理一致性检查。

4. **[P2] 操作与 guard 完整性只在两份冗余列表之间比较，未绑定必需物理记录。** `native_full_horizon_originals.py:483` 比较 `operational_events` 与 `backend_operation_ledger`，却不要求它们覆盖每个原 CONTROL、PHYSICS、COMMAND 和 CAPTURE；`active-checks.json` 可以为空，guard 检查只要求最后一项是 `CLOSED`。同时删除两份列表中的同一操作，或缺失实际终止命令，仍可能通过该阶段；`physics()` 只是检查存在的 STOP 的 parent，没有要求实际 STOP 存在。应重放必需操作/guard 日程及其身份、步骤、顺序，并要求正常关闭的真实 `hold_current_joints → emergency_stop` 原件，不能以 CLOSED 标签代替。

5. **[P2] render 计数依赖后续记录成功，失败时会少报已发生的 render。** `native_full_horizon_recorder.py:268` 先调用会写 blobs 的 `super()._on_boundary()`，随后才在第 281 行增加 pass 数。如果三个 render 已成功、但原件写入失败，这三个已发生的 pass 不会计入；应用仍把旧值写成 `BEFORE_SHUTDOWN` 的 render 总数。camera 在中途 render 异常时也不返回完整 pass 列表，此时不能把未知数量当作零。应把已返回的真实 pass 计数与可失败的持久化分开，并明确记录失败采集的已知下界或 UNAVAILABLE。

**Minor**

无单独提出的样式问题。

**Recommendations**

上述问题应按 AGENTS.md 交给实际 Astra 制定限定修复计划。针对 reader，应增加通过实际 recorder 数据形状贯通的 CPU 原件图检查，覆盖真实 `-1` 背景、删除 guard/operation、改变控制目标及写入失败计数；不需要为此启动 renderer。修复后必须重新冻结 source generation，保留现有失败与验证原件。

**Declined-to-judge**

- 实际抓放成功、marker 全程可见、真实 wall/RSS/render 成本：本审查禁止 actual，现软件证据不能确定这些结果。
- 九组件有限校准、P8 native 正链与正式研究验收：明确属于后续里程碑。
- GPU 服务占用及 R450 环境释放条件：由 ROOT 独立处理，不改变上述代码问题。
- 两个历史脏 gitlink、提交推送及远端复现包完整性：不在本次只读代码审查范围。

**Ready for first actual run? No.** 首组真实帧存在已确认的 reader 兼容性阻断，且来源失败停止与独立一致性验证尚有缺口。当前应继续保持 actual NOT_RUN、native UNKNOWN。

## ROOT disposition

五项均接受进入下一轮实际 Astra 规划；不在计划前修改产品或追加验证。原运行结果保留。四项 declined-to-judge 中，实际结果和 Git 交付由 ROOT 后续执行与核验，GPU 按 R450 处理；九组件/P8 是既定后续里程碑，两个历史脏 gitlink 保留不动。此前推送已经完成，本轮尚未提交或运行 actual。
