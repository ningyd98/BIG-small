# 急停快照与接受命令的时序补充

v2 离线工具第 150 行要求最后一条 guard 记录 estop_engaged 为真，第二次派生因此退出。冻结生产 _close_execution_guard 先调用 _guard_failure_record 并登记 FAILURE 快照，再调用 emergency_stop；只有后者抛错才填 stop_error_type/stop_error。正式原件中这条快照是 false，随后提交的 command_seq=151 在物理步 2040 被接受，命令为 emergency_stop、interval_id=operation-7605、effective_from_step=2041；COMMAND 7605 与 CONTROL 7606 的 END 均无错误。缺少后续独立物理状态帧，不能声称已在 2041 步观测到效果。

仅在新的辅助副本及新输出中替换这一断言和对应输出标签，分别核对并报告前置快照实际布尔值（允许先已急停时为 true）、实际 guard 类型和步号、命令同 episode/seq/type/step 与接受标志、两次操作的对应 BEGIN/END/错误及是否有 stop_error。拒绝缺/错序/错类/未接收命令或带停止错误，不能把 false 当执行失败，也不能替换成无依据的后态 true。保留 v1 语法首错与 v2 原脚本、stderr、空派生，其余时段与像素核验不变。允许只读核对 schema 和拆分标签，按父计划双读新输出、核原 SHA 并列出首拒与 visibility 缺口；不重新执行物理、模型、收集或组资格流程。
