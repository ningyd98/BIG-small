# R401 — operational fence 总时限后的限定续验

实际模型 gpt-6-astra。最终冻结日志修正早期描述：memory call **PASS（138.021秒）**、teardown PASS；sqlite setup PASS，无 call终态，combined stage于180.041秒被正常回收。source drift0、R235 accepted、无自有遗留。不能称 memory死锁或据此认定SQLite回归。

只允许两段：① sqlite单节点一次240秒+cleanup15秒，原argv加 `-o faulthandler_timeout=15`，既取全线程栈也允许长fixture自然完成；② 原先未到达的另外三个node（含原参数）一次90秒+cleanup15秒。均用新R401输出目录，0retry，不重跑已通过memory、不改原180秒失败或断言。15秒栈是观察，不自动证明死锁；240秒仍未终态则保留UNKNOWN，无下一次尝试。

仅窄改R399 run_stage.py读取本轮两个stage overlay和输出目录/前置。原worker_short_green可在冻结failed fence干净回收且先前独立阶段真实通过后按原配额运行；native_queue_green仍需worker stage真实通过。各段串行，原R399计划及1800秒时钟持续不改。

最终guard验收必须汇合：原memory有效call+teardown PASS、新sqlite自然PASS、其它原node每参数自然PASS，且同一产品/测试pins和干净清理。明确是分段证据，不把原combined TIMEOUT重写成PASS。全部guard与原其它验收通过、终审完成才交付；产品新根因修复须下一Astra轮。

本轮不改产品/测试，不新增通用driver/helper审批链。预算含在R399剩余wall；Git及网络配额不增加。保留全部原失败、栈及阶段记录，DB/raw留本地。
