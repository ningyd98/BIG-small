# R419–R421 阶段进展与测试报告

本阶段完成R418优先计划的第一轮P0：Phase11回执真实性修复、未经证明的指标资格隔离、真实软件正对照；途中另由实际Astra规划并处理SQLite连接生命周期与adapter自建模拟crashed租约归档缺口。最终定向回归42/42 PASS（pytest27.48s），两文件Ruff及格式检查通过；1309原运行源文件仅adapter获批变更，另新增测试。原全量长测与失败没有被改写或重命名为成功。

| 判定层 | 当前证据 | 结论 |
| --- | --- | --- |
| 默认MOCK+RGBD生产入口 | 三probe真实BLOCKED_BY_ENV/RGBD_CAMERA_REQUIRED；没有实际任务调用 | 外层如实BLOCKED，invoked/completed/task/authority均false |
| 测试专属LEGACY_PIPELINE | 不替换Worker、SQLite或结果；主/恢复/去重实际SUCCEEDED且task_success=true | 软件完成与任务成功true；仅此软件正对照 |
| 损坏/未确认/缺件 | 身份/hash/attempt/consistent与发布确认反例 | FAILED/FINALIZATION，不接受空集合或SQL成功替代证据 |
| 性能/质量 | 旧事件数加常量毫秒已移除；未测字段0/false占位且NOT_AVAILABLE | 论文资格false，时长/质量尚未资格化 |
| 返回时资源 | 正确空串/NULL谓词计数lease0，FD前后0，heartbeat空，DB hash一致 | 本轮新scope已收口；旧NULL-only计数结论撤回 |
| 正式研究/实体 | 未重跑5580或全suite，未接模型/相机/控制器 | 无正式研究或实体通过声明 |

下一轮继续R418顺序：先修共享RuntimeSpy与completion回调前置契约，让22个原失败节点到达目标断言；再分开诊断5项租约问题（嵌套写入、双连接事务、跨进程队列）。之后明确生产Phase11软件入口是否应显式legacy，再复验原Phase12 2FAIL+1INCOMPLETE和validation消费边界。事件复现、UTC性能profiling、API语义及静态治理按原依赖后续分轮，出现新根因必须先由实际Astra规划。

首轮不改默认输入语义，不把测试输入wrapper发布为生产路线，不让软件SUCCESS恢复研究资格。原4751长测35FAIL与1INCOMPLETE仍是历史事实，不能减去本轮针对性PASS得出新的全量通过率。真实数据、边缘模型、Isaac/ROS/CED/标定/控制器等实证缺口继续存在。

详细步骤、源hash及逐阶段原始退出见step-report.md、validation-summary.json、final-integrity.json和R420/R421报告。完整DB/raw本地保留；选择性提交不是完整远端复现包。fresh Astra审查结果与精确交付SHA分别保留，不能以清单冒充原件。
