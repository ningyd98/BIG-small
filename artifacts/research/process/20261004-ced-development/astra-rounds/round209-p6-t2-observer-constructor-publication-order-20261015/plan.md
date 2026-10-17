# R209 — 构造观察器先完整注册，再公开给采样器

实际规划者：gpt-6-astra（/root/astra_status_plan）。仅计划，待 ROOT 审核。

已独立确认静态顺序缺陷：add 在 worker_refs.append 后才登记 objects 和 resources。已启用的 profile 可在 append 的 c_return 事件采样新对象，访问尚不存在的 objects[id(worker)]。现有 RLock 允许同线程回调重入，不能使尚未完成的登记原子化。没有实际 T2 异常或测试失败。

唯一 Sol 只调整 _b_t2_observe 内 add：在同一 guard 下完整构建记录，先写 objects，再向 resources 追加同一记录，最后才将 worker 暴露给 worker_refs。保留重复身份检查、全部 transitive/partial-init 构造记录及真实初始化状态。禁止吞 KeyError、缺映射跳过、关闭 profile 或伪造 cleanup。无需修改 sampler、poll、consumer 或 schema。

ROOT 审核8个输入后，作者先独占保存完整204335字节 before-test，再做上述最小调整；新 diff/report 写本轮 implementation，R208历史原件不覆盖。ROOT普通文本/字节门须证明 add 以外全同、168003旧前缀及19产品/211保护不变、runner31818/13304…与角色不变，并联合全文审 R208 producer/consumer。门通过后才继续 R204 七正文准备。

新增执行/测试/静态/Git槽均0；T2 RED/GREEN两角色仍各0used/1remaining且HELD。18/64、并发2、broker1/heartbeat1不变。原R208尚未被source gate接受，不能把本轮源修正称测试通过或T2 ready。

精确输入SHA、修改区、归档输出与门禁合同见 plan.json；新问题或范围扩大立即保全STOP，不重试。
