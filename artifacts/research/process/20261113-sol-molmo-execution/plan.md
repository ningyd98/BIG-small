# Sol/Molmo执行阻塞攻坚实施计划

当前模型，非Astra；内联实施。用户已授权MuJoCo组件诊断且保留硬安全检查，详见execution-scope-decision.md。原需求附件及历史失败SHA留本地。

1. [x] 验证标记资产结构等价：精确原始/变体SHA，37个零质量零接触标记；原正式校准和释放许可不变。
2. [x] 主线程Molmo两阶段规划：2定位+1Sol，暂停物理重采集，2定位+完整合同校验；0云重试，旧帧不改时间。
3. [x] 实际SQLite worker组件分支：真实租约、关键代码身份、SkillExecutor、SafetyShield、当前RGB-D支持与硬安全；默认正式模式明确阻塞。
4. [x] 软件TDD及负例：原生模型/云替身仅作软件验证；保留超时、旧标记6动作遮挡停止等失败。新75mm/140mm变体8动作且独立物理通过。末尾采集失败仍评价并记失败。
5. [x] 完成限定回归、类型/风格、全仓测试尝试和一次独立审查；必要修复按根因合并。
6. [x] 最终代码真实模型复核：先跑新140mm变体一例；每新版本1load/4gen/1cloud、0重试/修复。仅真实根因修复后第二新版本，合计最多2例。固定S01，seed不是独立场景，任务120秒/16000步，不绕过停止以凑动作数。
7. 独立验证、文档和派生报告已完成。按21个精确路径提交推送；HEAD/上游/远端SHA以本地delivery-receipt.local.json回执及最终汇报为准，提交内不写入自引用SHA。

结果边界：component_success仅表示本组件诊断完整且独立physical_success；通用success=false，online_reported_complete=null，formal_research=NOT_ACCEPTED，新增正式合格组0。不能据此声称T10、G1、B0或T8已通过。原始RGB-D/DB/凭据/模型回复/权重/SDK留本地。
