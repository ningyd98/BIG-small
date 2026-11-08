# R474 Astra 补充计划：修正计划输入清单读取

实际规划者：`gpt-6-astra`；仅修正前置校验，不重写 R473。

**问题及原始失败：** R473 实施前检查误用 assert isinstance(plan[input_sha256],dict)，实际输入字段为 list[条目]，触发 AssertionError。原始失败显示 pin type list；失败发生在下载、安装、GPU运行及implementation/steps/reports创建之前。

**根因：** ROOT 一次性前置检查对计划 JSON 字段形状作了错误假设，非 R473 计划输入损坏或产品问题。

**限定范围：** 仅更正 ROOT 本轮 preflight 命令/本轮 artifact 检查脚本的读取逻辑，并在 R474 保存复核与步骤报告；R473 plan.md/json、输入源文件、旧诊断字节均不修改。不加产品测试，不安装、不下载、不运行模型作为此修复验证。

**执行：** 先核对本计划固定输入 SHA；读取 R473 input_sha256 为 list，逐条要求 dict 且 path 为非空仓库相对路径、bytes 为非负整数（拒绝 bool）、sha256 为64位小写十六进制字符串；拒绝重复 path、绝对路径及越出仓库的路径。逐项对真实文件检查存在、大小和 SHA256。另对 original_evidence 按其实际 list 结构逐项校验同样的完整性。失败时原样记录并停止，不改预期值或源文件使其通过。

**验证：** 修正后执行一次真实 preflight，报告 input_sha256 13项及 original_evidence 实际条目数、每项 expected/actual bytes/hash、路径唯一性与总结果；成功要求全部匹配且无重复路径。保存原命令失败和修正后stdout/stderr/rc。无需模拟产品用例或新增产品测试。

**前置条件及边界：** 限时5分钟、仅本地读取和artifact写入；不需要GPU或网络。R474通过只证明计划输入校验工具恢复，不证明模型兼容性/双图质量。通过后继续原R473全部阶段与已限定A/B路径，不再改写R473。若发现实际文件漂移、重复路径或新的根因，保存证据、暂停相关执行并另交Astra；不自动修源文件。

**输入 SHA256：**

- `AGENTS.md`：`8567e10635a650e2619905d6b3a6e0a885812060fecb1cdd4487bbf118593649`（1774 bytes）
- `artifacts/research/process/20261004-ced-development/astra-rounds/round474-taichu-plan-input-shape-20261108/diagnostic/original-failure.txt`：`a5c3091a909eee054e3bdbe2238160b6ebeb59d7f94ceeb0d15c30ad7fe9a95e`（102 bytes）
- `artifacts/research/process/20261004-ced-development/astra-rounds/round474-taichu-plan-input-shape-20261108/diagnostic/context.json`：`e7b453313a405ba006199dcd60cdf8d560bdd4f891604af5f2b7bbbbb1f9fac1`（416 bytes）
- `artifacts/research/process/20261004-ced-development/astra-rounds/round473-taichu-quantized-dual-image-20261108/plan.json`：`71e03d28e83b29c5b024b4e79edef57d914f6d3ec39f64faf84dce005af43573`（26464 bytes）
- `artifacts/research/process/20261004-ced-development/astra-rounds/round473-taichu-quantized-dual-image-20261108/plan.md`：`0f255cd1bfced88a0451d79f4d6d2f1d7b577515393242ba0f8188e8807663cc`（23438 bytes）
