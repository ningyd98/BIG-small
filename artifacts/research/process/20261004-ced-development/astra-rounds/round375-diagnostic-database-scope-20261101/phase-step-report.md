# R375 数据库作用域单次对照步骤报告

结论：本次限定同序模块对照通过，原失败保持。实际gpt-6-astra的[计划](plan.md)记录原始失败、19项直接输入SHA、根因假设、环境差分、前置和60秒/90秒双层上限。[首轮adapter审查](adapter-review-01.md)要求补足finally清理、证据解析失败保留和真实外层监督；限定实现完成后，[第二轮审查](adapter-review-02.md)为READY。

## 原始失败与限定修改

R374工作台模块原为6通过、1失败，WebSocket首个事件期望run_state，实际job_created。runner设置模块级SIMULATION_RUNTIME_DB，服务优先使用该值，覆盖测试自己按tmp_path创建的数据库位置。对照保留原7节点顺序、断言和依赖，只移除该环境覆盖并将全部输出路径迁移到新的R375目录；MODEL_CONTROL_DB、DASHBOARD_ARTIFACT_ROOT及R223前置继续独立保留。

原continuation在07:05:18Z已完整记账且父进程退出，91份子进程清理完成；R375外层在07:05:36Z才启动，没有与上一批重叠。19项计划输入和1050源码文件在执行前匹配；原八小时墙钟与报告预留仍有效，没有重置额度。只执行一次，不重试。

## 实际结果

原序7节点全部通过，0失败/错误/跳过，源前后0漂移。内层exit0，17.487450秒，node_order_matches=true、comparison_acceptance=true；[内层回执](implementation/workbench_module_without_runtime_db/result.json)与[JUnit](implementation/workbench_module_without_runtime_db/junit.xml)保留。外层exit0，19.925086秒，无超时、错误、信号或活进程残留，launcher已回收，见[外层回执](outer-run/result.json)。

进程结束后只做文件路径/大小/SHA256盘点，没有连接原始SQLite。实际生成6个simulation_runtime.db，全部位于各测试的persistent-basetemp子目录/artifacts下，没有阶段级runtime/simulation_runtime.db；附带WAL/SHM按现状记录，未checkpoint或改写。不是每个测试都必须创建DB，因此不要求7个数据库。见[数据库路径清单](implementation/workbench_module_without_runtime_db/database-path-inventory.json)。旧默认历史数据库及整个文件系统没有做穷尽审计。

## 验收与边界

内层结果、外层清理、同序节点、源码和数据库路径证据共同满足本轮限定验收。可表述为“修正runner数据库作用域后，此次同序完整模块对照通过”；不能表述为产品Bug已修复、所有顺序均等价或全流程通过。原R374的6通过/1失败不改写；R375仅在4732唯一节点清单中追加7项尝试，其中原失败节点恢复通过，分母不增加。

本轮没有产品/测试/golden修改，没有新的模型或硬件调用，没有正式研究验收。总体结论见[R373阶段总结](../round373-full-workflow-rerun-20261101/phase-summary.md)。
