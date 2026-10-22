# R324：ROOT 验收返回包装层接续计划

> 实际模型 gpt-6-astra；仅规划。ROOT 独立验收、Sol 单写者边界保持。

**原始失败：** R319/reviews/red-acceptance-check-failure-actual.json 完整保留原调用及 83c657 exit 1。原脚本把 `actual['completion']`（kind/invocation/actual_tool_return 包装对象）与 `native`（内层实际返回）直接比较。验收写入尚未到达，不是 RED 行为失败。

**实际结构：** initial 34772c 返回 session90330；completion 为同 session 的 poll，内层 2f7b40 exit0 与顶层 actual_tool_return 相同，child1、attempts1/retries0。ROOT 红键 RESERVED1/0，AUTHOR SPENT1/0；GREEN/SELECTIVE HELD0/1。150pins、284 资源/283 recorded initialized/284 cleanup、2DB 与原唯一误分类断言仍按原标准验收。

## 唯一修正与一次验收

- [ ] ROOT 复核 input-observation.json 中精确输入仍一致，原 acceptance/settle-before/settle/temp 输出仍 absent。原 RED 不重跑，不 reset。
- [ ] 从原失败 invocation.arguments.cmd 派生，唯一 `actual['completion']==native` 改为 `actual['completion']['actual_tool_return']==native`，计数恰为 1。其余 JUnit、150pins、原始文件、case、284资源、DB/archive/sidecars、cleanup、唯一断言及 ledger CAS 全部保留。
- [ ] 可在 attempts/retries 断言之后加入 plan.json 给出的 initial/poll 关联复核：有 session 则所有 poll 指向同一 session、空 chars、completion 为末次 poll；直接完成则无 polls 且 completion 为 initial。不接受只拿摘要代替 actual 返回。
- [ ] 可在 `ap=save(` 之前给 accept 追加本轮计划/观察/原失败 pins。ROOT 读完整修改文本后只执行一次元数据验收续接；exact arguments/actual 保存 R324/reviews/red-acceptance-continuation-actual.json。预期 exit0，合法 RED 独立接受并按原 CAS 将 ROOT 红键 RESERVED→SPENT，AUTHOR 不动、其余键不消费。

## 只读审阅的实际范围

原验收脚本已全文阅读，真实 result/case/summary/callback/prerequisite 的 RED 分支字段结构已核对，待写结果均不存在。本席位没有执行全部验收断言。曾对只读验收前缀做 AST 防写检查，6718e8 因把 classname 字符串 replace 当写操作而在前缀执行前拒绝；该规划工具误报如实记录，不冒充验证通过，也未重试运行该前缀。ROOT 续接仍须执行原完整验收条件，不能凭本规划直接接受。

## 后续与停止边界

原 GREEN/SELECTIVE 可沿用此次已审的 nested-return 取值及关联检查模板，但必须读取各自实际 envelope，不假定实际 session/chunk、资源数或未发生结果；原条件分支和两 once 额度保持。原 R319 observer 修改仍等待合法 RED 接受。

任何新字段缺失、证据矛盾、源漂移或写入失败都保存原件并暂停相关动作，不放宽断言或自动重跑。本轮新增 runtime、测试、SQL、产品/observer 修复权限均为 0；只允许上述 ROOT 元数据接续。R323/fresh 独立工作不受影响。元数据验收不是 T2/P6/native/formal 通过。
