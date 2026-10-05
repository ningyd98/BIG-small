# T12 实际 worker 链路接入（第47步，2026-10-05）

本步实际修改运行代码，完成真实 job/lease/attempt 来源协调、持久首次采集与规划 claim、预算/原截止时刻保留、完整原始计划登记、普通验证路由及 raw-v3 recorder 接入。状态为 `IMPLEMENTED_CPU_VERIFIED_RESEARCH_NOT_ACCEPTED`，开发主线仍是 T12/18，T13 并行，边缘型号后置。

## 实际改动

- `SimulationWorker` 在初始化前查当前租约和唯一开放 attempt，固定真实任务时钟及源清单；reset 后采用实际 backend episode。OpenCV 配置需要明确角色、持久 event 仓库和机器人身份，默认 LEGACY 保留。
- 新 `VisualWorkerRuntime` 在调用采集/模型之前持久占用 claim，返回后重查来源；遗失 claim、过期、取消、源漂移、重启重放和普通重观测重复扣费均被拒绝。完整原预算和绝对截止时刻在计划晋升事务中保留。
- OpenCV 路径保留原始完整合同、安全、时域和重试策略；不调用旧 `grounded_contract` 删 HOME/改约束。普通验证使用 checkpoint context，native 使用独立完整 action context。绑定在持久路由后失效，SafetyShield 前及 SkillExecutor 前重新绑定和原生复核，执行器保持唯一。
- 新 recorder 在 reset 前开启，包围已有 reset、settle、采集和唯一执行器返回/异常；计划登记后绑定真实仓储、actual attempt、场景、资产与配置。失败与缺测保留分母，审计故障不阻止已有 stop。配对 UTC 的外部不确定度仍缺，因此 UTC 映射和连续运动不认证。

## 验证与报告

最终合并 **539 PASS / 3 skipped / 1 deselected，225.29 秒**，见 [CPU 日志](final-cpu.log)。Ruff 10 文件、format 9 文件、cold mypy 5 源码通过，见 [Ruff](final-ruff.log)、[format](final-format.log)、[mypy](final-mypy.log)。这不是整个项目套件，重叠测试不相加。3 个 skip 属于现有后端专用范围；排除项是已有实际渲染测试，先前缺 DISPLAY 的失败保留在工厂报告。

真实内存/SQLite 仓储的完整软件停止路径各执行 1 次替代规划、3 张合成观测、2 次已扣预算重观测，0 动作、0 完成步骤，截止时刻不重置且 retry pool 不返还。它证明代码组装和预算路径，不能证明 Max、真实相机或物理任务成功。

局部报告：[工厂接入](../t12-worker-factory-integration/report.md)、[原始记录器](../t8-raw-v3-recorder-runtime/report.md)；协调器44项测试包含于合并套件。ROOT3 的[独立审查](independent-execution-review/review.md)另有90项 CPU 和4次真实仓储探针，范围仅为软件组装。审查发现可选 supervision/wait 绕过持久 claim；已在 policy 构造时拒绝这些尚未实现的配置，LEGACY 周期基线保留。该拒绝是临时缺口处理，监督持久调用仍属于必须完成的后续研发。

本步没有新远端模型调用或动作实验。已有 render-disabled 被动测试累计8个真实物理步（委派3×2及合并套件1×2），含8次已有被动控制更新、0运动命令；另一个已有渲染测试尝试因 DISPLAY 缺失失败，没有有效帧。软件 COMPLETE raw graph 的121步为替代物理，不能加到真实步数。源清单、活动口径和失败见 [机器记录](verification-summary.json)。

## 仍须完成

真实 Max 来源/调用、端侧几何与连续运动证书、完整 HOLD/TERMINAL 原始条件映射、持久监督 claim、研究 pilot 的真实 worker 入口、风险校准及机会/教师故障/INITIAL/METHOD/FINAL 尚未完成。当前缺证时 native 保持 UNKNOWN 并停止，不能凭软件通过放行动作或勾选主任务。recorder/coordinator 及较早冻结依赖仍有独立组件审查待完成。

[本次环境复查](../environment-availability-step47.json)只读 key 存在性与公开模型名称，没有读取密钥或完整 profile：4个相关环境 key 均缺，两仓库仍只有0/10个 profile且无 Max profile。因此本轮没有声称已完成真实云规划。无需在聊天中提供密钥。
