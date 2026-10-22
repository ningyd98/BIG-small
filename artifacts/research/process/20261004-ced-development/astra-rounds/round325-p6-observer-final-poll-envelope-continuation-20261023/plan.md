# R325：最终完成轮询独立存储的元数据接续

> 实际模型 gpt-6-astra；仅规划。ROOT 保持独立验收责任。

**原始失败：** R324/reviews/red-acceptance-continuation-actual.json，7cc722 exit1 line29，完整保留。R324 optional linkage 错误要求 `polls` 非空且末项等于 completion；真实格式中 polls 只存中间轮询，最终完成轮询独立存于 completion。原 RED 不存在需要重跑的行为失败。

**真实 envelope：** initial34772c/session90330，polls=[]，completion.kind=poll、session90330、chars为空，内层2f7b40/exit0等于顶层native。原 child1、attempt1/retry0保持。ROOT红键RESERVED1/0、AUTHOR SPENT1/0；其他两键HELD0/1。

## 唯一逻辑替换

从 R324 冻结失败 invocation.arguments.cmd 派生，将下列两行（唯一一次）：

```python
 assert actual['polls'] and actual['completion']==actual['polls'][-1]
 for poll in actual['polls']:
```

替换为：

```python
 for poll in [*actual['polls'],actual['completion']]:
```

循环内原 kind/session_id/空 chars 检查保留；前面的 initial invocation 和 `completion['actual_tool_return']==native` 保留；无 session 的原直接完成分支不变。既不要求中间轮询非空，也不要求完成项重复出现在 polls 中。后续 JUnit、150 pins、原始文件、资源、DB/archive、cleanup、CAS 条件全部保留。

## 已做的只读检查

原失败脚本已全文阅读。714cab 仅运行其读取/核对前缀：内存应用上述替换，在 accept 字典前截止，移除 save/full 函数定义；没有执行写入、ledger 修改、产品代码、SQL 或测试。其现有 RED 全部读取断言通过：150 pins、64 常规文件、2 DB/archive、284 attempts/283 原 recorded initialized/284 cleanup、唯一预期 JUnit 失败。真实 envelope 全体已查看，acceptance/settle 输出仍 absent。这是规划输入核对，不代替 ROOT 独立验收。R324 原规划护栏失败 6718e8 仍如实保留，不改称成功。

## 一次 ROOT 接续及边界

- [ ] ROOT 复核本轮输入 SHA、输出 absence 和原 ledger 状态。
- [ ] 仅上述 count1 替换；可在原 ap=save 之前追加 R325 plan/observation/本次失败 provenance，保留原 R324 provenance。
- [ ] ROOT 读完整修正命令后执行一次 metadata continuation，预期 exit0；exact arguments/actual 存 R325/reviews/red-acceptance-continuation-actual.json。按原 CAS 接受合法 RED 并结算 ROOT 红键；AUTHOR及其他键不变。
- [ ] 后续原 GREEN/SELECTIVE 可复用本字段读取模板，仍逐项核对各自真实 envelope/证据；不得假定 future chunk/session/结果。

新增 runtime/tests/SQL/product/observer 修复权限均为0；不重跑 RED、不 reset、不修改旧失败或原数据。observer 修改继续等待 ROOT 实际合法 RED 接受。新失败/输入漂移/已存在输出保存现场后暂停，不自动重试、不放宽标准。独立 fresh 工作继续；本轮不晋升 T2/P6/native/formal。
