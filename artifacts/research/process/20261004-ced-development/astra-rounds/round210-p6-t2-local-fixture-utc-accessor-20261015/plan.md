# R210 — 本地 bootstrap 夹具与 UTC 接口分离

实际规划者：gpt-6-astra（/root/astra_status_plan）。仅计划，待 ROOT 审核。

已确认同一夹具兼容根因：local definition 的 lease 明确拒绝 UTC 访问，task_started_at 转入 legacy_deadline；local transition 严格10字段不含 current_lease。当前两个 helper 仍沿用旧租约/时间构造，不能作为合法行为 RED。没有运行时失败或测试执行。

限定在 _b_t2_bootstrap_request 至 _b_t2_exercise 之前的单一区域内，只改 request 与 capture_and_unusable_plan 两函数，中间 _b_t2_transition 逐字不变。request 移除 current_lease，保留严格 local 字段、当前 CAS/hash、原 original_time 和无权 decision/transaction。

capture helper 使用真实现有签名 reserve_capture(robot_state, initial=True) → complete_capture(claim, observation, robot_state) → reserve_plan(robot_state) → complete_plan(claim, draft, robot_state)，每次读真实 runtime.bootstrap，保留真实 claim 和原预算。CPU frame 只借旧 frame 的模型数据；其 tuple 前两项不用，以None明确，第三项是真实采集调用附近的 UTC diagnostic，不从local UTC getter或单调时钟伪造租约/期限。最终episode/frame字段和checksum清空后由真实模型重算验证，PlannerDraft仍使用原 observation.evidence 与model/role来源。完整字段与顺序见JSON。

当前 runtime 尚未实现T2 local行为；上述路径依赖原R158产品实现及将来GREEN完整实证，不能靠fixture制造receipt/VALID/private权限。本轮不改runtime或T1 UTC-veto。所有transitive Memory仍计入当前观察器并真实finally清理。

ROOT核13输入后，唯一Sol先完整保存before，再改两helper并保存本轮diff/report。ROOT逐字证明区域外、旧168003前缀、runner、19产品/211保护和角色全不变，全文核schema与真实producer前置。源门后仅恢复R204七正文准备，原RED/GREEN均另行门控。

新执行/测试/静态/AST/import/probe/Git/review槽全部0；原T2两角色RED/GREEN各0/1且HELD，不重置。T2/P6B/T12/native/formal均不因本计划通过。新问题保全STOP，不试跑。
