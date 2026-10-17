# R218 — T2 writer 本地夹具表示与来源修正

实际作者：gpt-6-astra。仅计划，等待 ROOT 门控；唯一修改者为原 gpt-6.1-sol。

四项同类静态输入问题已源级核实：online 通用 dataclass 序列化产生第七字段，但严格 route 只接受六字段；Memory snapshot 的 asdict 先于真实 to_payload，并会递归至 RecoveryRecord 冻结 MappingProxy；新本地 promotion 在四字段 history.request 中，现夹具却读取 legacy promotion 键；ActionEvidenceContract 将 TTL 误放 expected_duration_s。均未运行复现，不能当作测试失败。

只改 tests/test_operational_runtime_closure.py 三函数：_b_t2_plain、_b_t2_writer_inputs、_b_t2_writer_authorization。显式六字段投影；真实 codec 优先、其余 dataclass fields/Mapping 完整递归；从实际已提交 local history.request 唯一选择 promotion.local.v1；duration 与 TTL 按冻结 requirement 分别显式赋值。保留 CPU 来源、真实 runtime/private publication、权限拒绝断言与资源分母；不编造 UTC/authority，不放宽 codec，不删数据或吞异常。具体字段与限制见 plan.json。

另外 d36f80 exit2 是 ROOT 猜错附加源码路径的独立读取错误。本轮放弃该 lookup，零重试/替代命令；后续规划仅读实际已观察/导入路径。原失败完整保留。

当前输入为 R217 实际纯移动后的252700B/d0509a55…，其 after 归档与报告已实读取pin。ROOT须先接受R217，再复核本轮输入和三函数范围。先物理保存完整before，修改后存after/limited.diff/change-report/actual。原168003前缀及三函数外全部字节固定；R218明确允许其中 _b_t2_plain 改动，因此不再以whole227116历史前缀对修正后文件作不可能的相等要求。R217旧原件仍完整保留。

ROOT以正常stdlib字节/文本/hash核三函数、19产品、211保护、runner和角色，并全文审六字段/新history/预算字段映射。七正文、节点、预算、旧源码与原始报告均不变；此后只恢复原R204最终准备。没有新增执行、测试、静态、审查、Git槽，原RED/GREEN各0/1 HELD。未来真实GREEN才证明完整路径；T2/T12/native/formal均未通过。保存后STOP。

