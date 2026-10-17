# R275 dual 会话前置失败处置计划

实际规划模型：gpt-6-astra。仅计划；零新增运行、测试、静态、SQL、Git或审阅额度。

## 证据与结论

R268 dual 原诊断 child=1、wrapper=0，344.202564 秒结束；不是合法 RED/GREEN。完整 traceback 将失败定位到 capture helper 的 reserve_plan，经真实 publication/read scope 到 _check_ingress:471。index=0/PENDING 的 commit-loss 故障尚未设置。ROOT 已独立接受 353 项证据完整性检查。

真实 guard 合并检查注册身份、_closed、_unusable；现存 trace/侧车不足以区分最初触发条件。资源/cases 未保存撤销原因，worker 异常处理和 poll finally 还会覆盖 cleanup_reason。post-unwind 两域计数0不可当故障瞬间状态。因此不修改产品、dual helper、权限、TTL、等待或断言；既有 fail-closed 现象不等于已证明最初撤销正确。

357/356/357 是实际观测的尝试/初始化/清理分母。未触发540秒栈不证明死锁或解释旧600秒超时。所有完整输入SHA列在 plan.json 与 input-observation.json，原工具对象另存。

## R274 独立性及世代

两个 R268 槽已结束并结算，ROOT 可按原 R274 门禁串行释放 sole Sol 的五处 wait-helper/wait-test 修改。它们不触 capture helper、dual、_b_t2_exercise、observer 或产品，不能声称修复本次 dual 问题。

旧 test 254018/ed602 原字节只以 R274/before/test_operational_runtime_closure.py 与完整 manifest/base64 解释。未来 R274 派生 254132/ebf1 须由实际 after 和精确五替换证明；不将新 live test 硬比旧 pin，不重写 R268 plugin/test 来源，不做整路径豁免。source gate 不等于行为通过。

## 最小后续证据边界

下一实际 Astra 运行计划需要捕获同一真实 session 首次 invalidate(reason) 或 close/注册失效，以及 ingress 拒绝时已有原生字段和有限栈，早于 cleanup 覆盖；只旁观，不调用权限/时钟方法或干预同步。多字段快照明确非原子。

建议只原 dual 一节点、child≤600秒+cleanup15，≤64事件/session、栈≤12、输出≤128KiB，溢出明确 incomplete。该建议不是本轮执行或源码授权；下一计划须给精确源码、argv/env、持久输出、ROOT reservation、真实资源/hook恢复合同。217秒wait与344秒dual需按未来有限分组设计，不能合并推定旧超时原因，更不能退款重跑GREEN7。

## 步骤和验收

- [ ] ROOT 全文审计划及输入三字段身份，保留原失败和完整原件。
- [ ] ROOT 记录 R275 仅诊断处置；按原 R274 before/CAS/source gate 决定独立源释放。
- [ ] 需要进一步实际取证时，由下一真实 Astra 计划单独明确有限授权；本轮不构造或执行观察器。
- [ ] 保留 R158 GREEN7 和两个 R268 槽各已花费事实，fresh12/Git及 T2/T12/native/formal边界不变；冻结后 STOP。
