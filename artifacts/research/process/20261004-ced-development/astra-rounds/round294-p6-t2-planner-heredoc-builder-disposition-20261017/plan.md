# R294：弃用规划 heredoc 边界构造器

状态：实际 gpt-6-astra 计划已冻结，仅供 ROOT 审阅。

`0b4263 exit1` 在规划脚本第 11 行的 header/tail 合取断言停止，发生于任何 mkdir/save 之前。必要物理读取 `7d2019 exit0` 确认：原 invocation 以 `PY` 结束，没有末尾 LF；失败构造器却要求 `PY\n`。这是规划元数据假设错误，不是产品或源码运行失败。

处置为 **ABANDON**：不修旧断言、不重放、不换别名、不 strip/normalize 原件、不执行替代构造器。完整失败及原 `702f9d` 作者收尾失败各自保留，后者不被本轮处置替代。

此前 `41f875 exit0` 已独立观察 C486 和新 runner 的 `def _t2_pin` 至 `def author_bytes` 完整区段均为 **17679 B**，SHA256 `8ef88c6906820c7a82a7c3bddfc2e60dc8335b4c8c3919228aa7938bf37b5af6`，逐字相等；新十段拼接等于整源。该原返回和 `514334` 完整源码读取保留在输入 packet；本轮没有重跑它们。

R293 计划尚未生成。ROOT 全文接受本计划并核对两个输入的 path/bytes/SHA256 后，才恢复独立 R293 规划：直接使用已成功的字节观察与物理原命令内容，以显式局部值保存其计划。不得继续或修复 `0b4263`，不得执行 finalizer。R293 的实际计划及实施门仍必须另行完成。

本轮只保存计划、输入观察、实际读取回执及 native 保存回执。R289 最终源、after、native、1341 检查接受、全部角色、上下文与预算不改。新增产品、测试、静态、诊断、审阅、Git、纠正读取执行额度均为 **0**。不创建 checker 或通用恢复流水线。

输入完整路径和 SHA 见 plan.json/input-observation.json：失败 packet 23232 B / e433362d…；原作者失败 packet 12189 B / 6eace31c…。验收仅为元数据处置及恢复 R293 规划资格，不表示 T2/T12/native/formal 或任何行为通过。落盘后 STOP 等 ROOT。
