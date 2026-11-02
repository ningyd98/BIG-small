# R398 步骤报告

按实际 Astra 限定计划，只修诊断 post-cleanup 报告路径：先建立 sticky marker/exit78/已观察拒绝事实，再逐行容错解析 audit/boundary、marker/ready/child-outcome，检查消费字段并保留有效行和原字节。读取/解码/结构问题独立记录 reporting_errors；无拒绝但观测不完整也返回非零，不能升级根因。

修后 driver 29323 bytes，SHA256 `3919f5ed871a8ff5d9ae000e7981856a6c5c5be86ff1f8e6f0ef6dc7deee3775`。AST 静态解析通过，35 项输入 pins 相同。未执行 driver/helper/人工坏日志探针/产品导入/SQL/网络/信号。原模式、超时、cleanup、输入和配额未改。

独立 delta 审查通过：C0/I0/M0，ready=true，R397-I1 解除且 R396-I1 保持解除；审查绑定上述修后 SHA。到本步骤完成时行为次数0；随后仅允许原 R396 唯一命令，预算不重置。
