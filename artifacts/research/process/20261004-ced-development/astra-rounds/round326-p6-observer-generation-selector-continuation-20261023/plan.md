# R326：observer 世代证明 selector 接续计划

> 实际模型 gpt-6-astra；仅规划，不修改产品或测试源码。

## 问题与定位

原 R319/reviews/observer-generation-actual.json 完整保存生成器及 d43d3c exit1，line23 的 `assert reconstructed==newmicro` 失败，发生在 after/diff/map 首次写入之前。已完整阅读同目录 observer-source-native-actual.json 中两文件 patch、真实 before/current 全差异及生成脚本。

根因是元数据插入范围少取一个 LF：真实授权 micro patch 在 synthetic-unit 注释之前新增空行，`addition_start` 从注释缩进开始，重建时遗漏该空行。不是新的产品或 observer 逻辑问题；禁止以改源码空行为方式迎合错误证明。

## 独立只读结果

dd5a06 对修正后生成器的 prewrite 前缀作只读重建，去掉 write 定义、在 after 初始化之前截止。所有 prewrite 断言通过：fixture 在 `_b_t2_observe` 外逐字不变；micro 完整字节重建相同；原 unrelated-profile 主断言不变；原 session code 在 patch 前捕获。RED gate 150 pins 中仅指定两测试文件变化，其他 148 一致。after目录、diff、map、preparation-report 均 absent。未导入/执行产品或测试，没有生成器写入。

当前两文件差异符合 R319 已定范围：透明 session init wrapper 的 ENTERED/RAISED/RETURNED 记账；移除 profile 的 `_sealed` 误判；安装真实构造 wrapper；micro 保留原 selective 断言并显式标记 controlled raising callable 的模拟检查。源码行为仍待 ROOT 审阅和原 GREEN/SELECTIVE 实测，静态一致不替代运行。

## 唯一字面修正与一次接续

从冻结失败的 invocation.cmd 派生，仅将（count1）：

```python
addition_start=newmicro.index(b'        # Explicit synthetic-unit bookkeeping only:')
```

替换为：

```python
addition_start=newmicro.index(b'\n        # Explicit synthetic-unit bookkeeping only:')
```

其余原脚本逻辑、源码字节、断言、输出位置均保持。R326 provenance 可写入本轮独立 actual/步骤报告，避免改动原生成器其他逻辑。

- [ ] ROOT/Sol 执行前核对所有当前输入 pins、before 原件、两文件差异仍一致；所有原拟输出仍 absent。
- [ ] 仅允许一次 corrected metadata generation，预期 exit0，写原 after 全字节/mode archive、diff、generation-map 和 observer-preparation-report。exact invocation/actual 保存在 R326/reviews/observer-generation-continuation-actual.json。
- [ ] ROOT 核对 map/reconstruction、原148 pins、2变更pins、各输出完整来源，再按原R319进行源码/argv审阅和新世代gate。该元数据成功本身不授权自动GREEN。

## 配额与停止边界

原 RED ROOT/AUTHOR SPENT 保持；GREEN/SELECTIVE 仍是原两 HELD once，不增加或重置任何槽。本轮无新产品/测试修改权限，无 runtime/test/SQL/Git 执行。旧失败、before、已写源码、R324护栏失败均保持。新失败或范围变动暂停相关续接并保存原始证据，不覆盖输出或自动重试。独立 fresh 审阅继续；不晋升 T2/P6/native/formal。
