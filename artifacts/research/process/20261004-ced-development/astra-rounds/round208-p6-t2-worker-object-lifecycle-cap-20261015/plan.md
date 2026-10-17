# R208 — T2 worker objects 与实际生命周期分开计数

实际规划者：gpt-6-astra（/root/astra_status_plan）。仅计划；待 ROOT 全文与输入复核，不实施、不释放任何测试。

静态缺口已确认：受保护 software_factory 第172行取得并丢弃 _cpu_visual_worker 返回的真实 worker，第174行另建真正用于 poll 的 worker。runner 当前把所有 kind:worker 构造记录套用18生命周期上限。观察器另把 idle active_job_id 当成 None，而真实初始化及 poll finally 都使用空字符串。没有发生 T2 测试失败或测得泄漏。

原始作者完整返回及 ROOT 观察均按 plan.json 的完整 SHA 固定。ROOT f48b30 路径 lookup 的 exit2 保留，不重放，不声称已读 queued helper 定义。R206 有界显示修正保持原字节。

## 限定修正

- 唯一 Sol 作者只修改 runner 的 _t2_resources 与测试新 T2 _b_t2_attempt/_b_t2_observe 的资源观察/清理分类；产品、工厂、旧168003前缀及其他helper不改。
- 构造对象和 partial-init 全保留，allocation_attempts 严格等于记录数。实际对象身份、强引用和唯一键保证不合并或丢弃未poll对象。
- 新 worker_lifecycles 明确 poll_id→worker_resource_id。原 poll_once 透传一次，真实方法入口才记 entered，真实返回才记 returned_normally；保留实际返回值与异常，不把返回true说成发布成功。finally记录结束。
- 18约束施加于真实poll尝试生命周期，entered与正常返回分别统计，父64上限、各场景2/2/6/2/2/2/2、并发2、每worker broker1/heartbeat1均不变。构造对象数量不是这些上限的分母。
- 未poll对象记录 never_polled_no_owned_runtime、真实空字符串idle和未分配session/thread，不虚构close；已poll对象依据真实结束、session关闭、线程结束、TLS/连接/clock清理。未知字段保持未知，不由initialized=false推定清理成功。

详细schema、字段约束、唯一ID、计数、原有检查保留范围见 plan.json.resource_contract。完整sidecars/result/index不缩减，stdout仍遵守已批准R206。

## 执行前提与门

当前 whole test197744B/ac723e…、runner21878B/f417… 已冻结。七个T2正文/fixture报告尚未写，不能称ready。ROOT核计划及13输入后，Sol先exclusive保存两份完整before，再作上述有限修改，R208新路径保存diff/report。ROOT正常stdlib文本/hash门逐字核其他函数/旧前缀/19产品/211保护与角色、全文同时审producer和consumer。R208本身不运行任何脚本或测试；独立R204正文准备随后继续。

旧R204/R206原件不覆盖。新验证槽0；原T2 RED/GREEN各0used/1remaining保持HELD。所有实际运行仍须原R204完整源门及独立reservation；接口RED不冒充行为验证，GREEN必须真实全部正文与资源关闭。

本轮仅资源观察合同修正，不授予T2、P6B、T12、native/formal或Git验收。新失败/范围扩大立即保全STOP，不重试。
