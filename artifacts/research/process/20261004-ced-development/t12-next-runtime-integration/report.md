# 步骤48：监督、完整效果及 pilot 运行入口

日期：2026-10-05。开发主线仍为 T12/18，T13 并行；边缘模型后置。本步是运行代码与软件验证交付，`formal_accepted=false`，整体研发继续进行。

## 已落地的代码

1. 持久监督 ledger 接入 memory/SQLite 与实际 worker。监督相机、provider 和 WAIT 都有独立占用/完成接口；原始任务时钟、周期、截止时间和已用配额保留，丢失 pending 不重放。owner 线程登记观测和 PLAN_PENDING 后，provider 使用不可变来源，不读取 backend；调用前后严格核对当前 publication、完整原计划、真实 lease/config、事件取消及来源。返回在原子动作边界消费。来源变化停止，只有经独立来源检查的真实 TTL 过期回复可以丢弃。
2. 完整 HOLD/TERMINAL 原始条件接入普通验证路由。保留全部 completion criteria；LIFT 检查 object_held/object_lifted/object_stable，object_held 同时需要视觉身份、深度与正确夹持反馈。历史 grounding 仅允许验证已在原有效区间内启动的 typed completion，不授予新动作权限。监督 REOBSERVE 由同一实际执行器返回后必须取得的 owned AFTER_EFFECT 新帧完成，不增加配额或重用旧图。
3. pilot 接入真实 SQLite job/lease/attempt，来源在 initialize/reset/settle 前建立，使用同一个 backend、capture、SkillExecutor 和 recorder。保留全部 SceneSpec、网络/扰动安排、四个周期和原始监督/等待选项。显式 MJCF 使用实际 XML 字节 SHA。工厂在任何 backend setup 前严格校验选项，非法值不能经默认值或转换制造授权。
4. recorder 修复 SENSOR 分配被干净帧替代的问题：一次实际采集保留 clean SOURCE，固定变换产生 derived ONLINE，逐字节核对 recipe 与源码来源；失败分母保留且拒绝干净回退。

局部报告：[持久监督](../t12-worker-supervision-claims/report.md)、[完整效果](../t12-full-effect-requirements/report.md)、[pilot](../t8-pilot-worker-integration/report.md)、[工厂选项补充](../t12-worker-factory-integration/report.md)、[扰动录制](../t8-raw-derived-transform/report.md)。本目录只保存有界源摘要和验证记录，没有再复制全仓快照。

## 测试及修复

| 检查 | 实际结果 |
| --- | --- |
| root 24 文件合并 CPU 回归 | 744 passed、1 failed、3 skipped、2 deselected；452.27 秒 |
| 最后失败修复后的执行/监督/旧监督相关回归 | **39 passed，53.90 秒** |
| 最后审计缺陷的合格 RED | 2 failed，0.50 秒；原日志保留 |
| 独立审查该修复及原来源/上下文反例 | 5 passed，0.50 秒 |
| 完整效果局部相关回归 | 337 passed、4 skipped，54.48 秒 |
| pilot 最后来源/终态修复回归 | 49 passed，16.06 秒 |
| 工厂/lease handoff 最后回归 | 54 passed，35.99 秒 |
| 派生录制定点回归 | 4 passed，0.70 秒 |
| 持久监督 producer 最后来源修复 | 6 passed，42.37 秒；此前完整 owned 79 passed，143.05 秒 |
| root Ruff / format / mypy | 7 文件 Ruff/格式、3 source 类型检查通过 |

以上套件有重叠，不能相加。原合并运行不是全绿：唯一失败是 SQLite 监督回复在两次检查之间跨过5秒有效期，正确丢弃但漏记 `reason`。两条定点 RED 还证明非 TTL 错误停止前会先写错误 DISCARD 记录。修复将记录移至独立过期确认后，补确切原因和 claim；非 TTL 错误继续停止。最终39项相关检查与独立5项检查均通过，未重跑整批24文件或宣称全仓通过。

独立审查另发现并关闭：pilot 启动失败遗留 lease、已结束 attempt 被覆盖，以及来源变化被丢弃、旧 PLAN_PENDING 可进入 provider、错误 reply context 被按迟到丢弃。历史发现、原失败与修复后的精确源 SHA 均保留在 [源审查](independent-source-review.md)和[运行审查](independent-runtime-review.md)。这是两个明确范围的复审，不能替代历史组件或整体方法验收。

原始日志与可复核命令、退出码见 [verification-summary.json](verification-summary.json)；精确源摘要见 [source-hashes.json](source-hashes.json)。Ruff/mypy 的旧配置提示和已有 AnyIO 依赖警告保留，不作为新代码失败。

## 实际活动与剩余前置

本步没有实际 Max/远端模型调用、新动作实验或 renderer 调用。一次早期排除表达式未排除既有 render-disabled 被动后端测试，实际发生2个被动物理步及2次已有被动控制更新，新增运动命令为0；后来合并检查明确排除该测试。这2步单独记账，不覆盖第47步的8步历史。其余 camera/provider/完整执行回归使用合成软件来源，不计物理成功。

真实 Max 来源及费用、OpenCV 完整目标范围/几何运动界/连续效果、风险校准、完整机会与200教师故障、合格四周期 B0、INITIAL/METHOD/FINAL 和实际恢复验收仍未完成。SOURCE_ONLY 读接口不授动作权限；多数据库前后校验不是跨库原子事务。原生证据缺失时动作仍停止；完成软件接口不能解除研究门。边缘型号继续后置。

自动审批曾拒绝一份可能把 provider 调用前校验改为忽略当前 publication 的补丁，理由是会削弱旧帧来源授权。该补丁未执行；本步最终实现保留调用前、调用后的严格当前来源校验，拒绝项通过该更严格实现解决。
