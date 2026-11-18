# 2026-11-18 Molmo 冻结提示绑定修复

首次四例诊断在 44102 的请求校验中退出 1。归档 `prompt.txt` 由 Molmo 的单图像聊天模板渲染并包含最后一个换行。旧诊断将它与原始用户文字比较。七个原试次的前两条请求共 14 个提示均遵循同一字节封套。 [Astra 方案](plan.md) · [首次失败回执](../round-harness-candidate-generalization-20261118/diagnostics-first-run-receipt.json)

先在合成索引内记录两个合法封套均被拒绝、裸文本被错误接受的 3 个预期 RED。修复限定在离线脚本中精确比较完整封套。测试覆盖首尾角色和边界、额外角色或图像、尾换行、互换短语和响应、错图及观测校验、不符坐标、截断上限以及不更新索引的提示篡改。生产采集和模型提供方保持原实现。 [RED 日志](prompt-red.log) · [RED JUnit](prompt-red.xml)

焦点测试 144 项通过，包含父轮的 129 项和此轮新增的 15 项。Ruff 通过。四例实际归档复算完成，两个 44102 POINT 与两个 44104 POINT 均绑定原始图像及提示，44104 仍在原几何门拒绝。44101 仍复现三视角的不同拒绝，44103 仍复现横退共面拒绝和独立物理成功。 [GREEN 日志](focused-green.log) · [GREEN JUnit](focused-green.xml) · [Ruff](ruff-green.log) · [四例结果](../round-harness-candidate-generalization-20261118/implementation/native-stop-remeasurement.json)

计划 35 项输入实施前全匹配，实施后 26 项冻结归档全匹配，候选只有诊断与测试按计划变化。新模型加载、生成、云请求和真机派发均为 0。首次命令、此次命令、退出和证据均可复核。 [实施前](inputs-before.json) · [实施后](../round-harness-candidate-generalization-20261118/implementation/diagnostics-inputs-after.json) · [验证回执](verification-receipt.json)
