# R327：GREEN envelope 可选标签适用性计划

> 实际模型 gpt-6-astra；仅规划。没有新的测试失败或 ROOT 验收失败。

## 事实与适用性差异

R319 session_init_green 原运行 initial78a10d/session30756、completion ef54d1/exit0，child0、5.535065558s。其 initial/completion 都完整保存 invocation 与 actual_tool_return，但不含 RED 使用的辅助 kind 标签；polls=[]，最终完成轮询独立保存。R325 模板显式要求 kind，故不能直接照搬；本轮对实际结构明确适配，不补写原回执。

## 两处校验适配

从 R325/reviews/red-acceptance-continuation-actual.json 的完整 invocation.arguments.cmd 派生，原 KEY/NEXT 映射为 `session_init_green` / `observer_selective_green`。仅改变两个标签判断（各 count1）：

```python
actual['initial'].get('kind','initial') == 'initial'
poll.get('kind','poll') == 'poll'
```

标签缺省可接受；若标签存在但值错误或为 null，仍拒绝。实际 initial argv、same session/空 chars、中间 polls 加独立 completion、nested-native、attempt1/retry0 全部保留；不把标签默认值当作伪造的新原始字段。其余 JUnit、165pins、资源、DB/archive、cleanup、源码世代和 CAS 不变。

## 实际只读核对

9a5539 已按上述三项映射在内存核对 validator 的全部 GREEN 读取断言：在 accept 字典前截止，移除 save/full 定义，未执行任何写入、产品导入、SQL 或测试。165 pins、64 常规文件、2 DB/archive、284 attempts/284 initialized/284 cleanup、JUnit 1/0/0/0、constructor RETURNED/original delegate/no _sealed 和全部原检查通过。ROOT GREEN RESERVED1/0、AUTHOR SPENT1/0；原 SELECTIVE 双 HELD0/1，acceptance/settlement 输出仍 absent。

## 一次首次验收与原流程

- [ ] ROOT 检查 input-observation.json 精确 pins 仍适用、原输出 absent、三个键状态未漂移。
- [ ] ROOT 全文核对派生命令；可在 ap=save 前给 accept 增加 R327 plan/observation/实际 GREEN 回执 provenance，保留原历史引用。
- [ ] 执行一次 GREEN 首次元数据验收，预期 exit0；完整 arguments/actual 存 R327/reviews/green-acceptance-actual.json。按原流程 CAS 结算 GREEN，并在原 HELD/sourcegate/output-absence 检查后预留原 SELECTIVE 一次；这不增加额度。
- [ ] SELECTIVE 后续验收可复用两个可选标签判断与 R325 实际 envelope 关联规则，使用其实际回执/原 unit 分支，不能预判结果或借用 GREEN 资源结论。

本轮新增运行/测试/SQL/产品或 observer 修改权限均为0，不重跑或重置任何原键。新不匹配或失败保持原件并暂停相关动作，不自动重试。GREEN 的软件证据不替代独立 fresh review、历史 overlay 或整体 T2/P6/native/formal 验收。
