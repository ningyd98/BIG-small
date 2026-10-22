# R320：不存在的 conftest 输入路径接续计划

> 实际规划模型：gpt-6-astra。执行沿用 ROOT 元数据维护、Sol 单写者与独立复核角色；本轮只规划。

**目标：** 解除 R317 红门禁生成脚本的一个多余输入路径假设，继续原 R317/R318 流程。

**问题与证据：** 原调用 940025 exit 1 在 pin/read_bytes 读取 tests/conftest.py 时发生 FileNotFoundError。完整调用和返回保持在 R317/reviews/red-source-gate-generation-failure-actual.json。此文件和根目录 conftest.py 实际均不存在；两者不是 R317/R318 必需输入。tests/__init__.py、pyproject.toml 存在。不是产品、测试或 outbox 行为失败。

## 实际核对与范围

- 已完整阅读原生成脚本；100 个其余已列冻结输入的 bytes/SHA 全相同，runner 模板及逐项重建相同；save 的换行 AST 值长度为 1，不修改转义。
- 原 review/gate/acceptance/reserve-before/reserve-receipt/临时 ledger 输出均 absent。ROOT/AUTHOR 四个原键仍 HELD 0/1。
- 输入及 SHA 见 input-observation.json；不得创建空 conftest、删除实际存在的 pin、改产品/test/runner、旧计划、旧失败或增加运行预算。

## 一次限定接续

- [ ] ROOT 执行前核对本轮输入仍一致、两个路径仍 absent（含无 dangling symlink）、原预期输出仍 absent、原 ledger 未变；原 R317/R318 适用性仍须满足。
- [ ] 从冻结失败回执取原 invocation.arguments.cmd，只将唯一字面量 `ROOT/'tests/conftest.py',` 替换为空串；计数必须恰为 1。其余原脚本不变。
- [ ] 在该输入列表循环之后、`mapping=json.loads` 之前追加一个小段：对两个缺失路径断言 `not exists()` 且 `not is_symlink()`；将本 R320 plan.md、plan.json、input-observation.json 和原失败回执逐一 `add(pin(...))`。absence 记录已经保存在本轮观察中，门禁通过 pin 链引用，无须改变 gate schema。
- [ ] ROOT 完整核对修正后的文本及准确 argv，然后仅执行这一次修正元数据调用，保留 exact arguments/actual 至 R320/reviews/metadata-continuation-actual.json。预期 exit 0，按原脚本产生 R317 review/gate/acceptance 和首个 RED 的 ROOT reservation。
- [ ] 核对每项输出 JSON 可解析、required pins 保留、R320 和原失败已引用。首个 ROOT RED 按原预算从 HELD 0/1 转 RESERVED 1/0，AUTHOR 与其余键保持原状态；这是原 R317 授权预留，不是新增或恢复额度。

## 退出与验收边界

本轮只授权一次元数据接续，没有新增 pytest/runtime/SQL 配额，也不自动运行 RED。生成成功后，由原 R317/R318 角色与 gate 流程继续四个原 once 键。运行前仍由 ROOT 放行；两个 RED 未接受前禁止产品修复。出现新错误或部分写入时保留全部原件并暂停，不重跑同一脚本覆盖输出。

R319 observer 修复独立，仍需等待 R317 四键全部结算。不得借本轮修改 observer、产品锁或权限/预算/TTL。元数据成功不代表软件、T2、P6、native 或正式研究验收通过。ROOT 可按用户已有授权归档本轮步骤报告并最终显式路径提交交付；本 Astra 席位不执行 Git。
