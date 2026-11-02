# R397 步骤报告

按实际 Astra 计划，仅补正 R396 诊断 driver 的拒绝停止机制：独占首拒绝 marker、finally 无条件 os._exit(78)、父进程实时 marker 检查和三来源拒绝优先分类；加入 READY/模式/poll/成功边界防御门。产品代码、原输入、模式顺序、allowlist、采样、运行预算未改。

修后 driver 27301 bytes，SHA256 `8a35abf5bfcf78bfde8aa1dd40d345fefcb5f7e955e5bbe1f4307809c8f267bb`。AST 解析通过，R396 35 项输入 pin 全部一致。原 driver 与 ready=false 审查已冻结保留。未导入产品、未执行 helper/测试/探针/诊断/SQL/网络/信号；行为次数仍为 0。

独立 delta 审查结果：R396-I1 已静态解除；C0/I1/M0，ready=false。新增 R397-I1：部分写入的诊断日志未经容错解析，可能抢占拒绝分类。已停止相关修改并交实际 Astra 规划 R398。原审查将完整冻结到 R398，未启动 R396 唯一运行，600 秒时钟与 Git 配额均未使用。
