# R422 下一轮研发进展与测试总结

本轮恢复测试前置契约：原22项失败全部在新scope执行到原目标断言并通过；完整计划内47个唯一GREEN节点全部通过。生产代码零修改，只补共享RuntimeSpy的非local声明与安全helper的completion关键字接口，新增3项真实消费者契约测试。

| 验证 | 结果与边界 |
| --- | --- |
| 修复前 | 原22+新3共25项预期前置FAIL；23缺mode、2拒绝completion；setup/teardown全PASS |
| 修复后 | 47 STARTED，setup/call/teardown各47PASS，JUnit无FAIL/ERROR/SKIP，无重试/INCOMPLETE |
| 原目标保护 | 22节点、19函数完整AST不变；逐原节点RED/GREEN与断言证明在final-integrity.json |
| 权限与安全 | 假owner、伪造观测、未知mode、UTC租约撤销、未知action反例保持拒绝；真实post盾拒绝原负超速 |
| 来源与资源 | 406个src字节全不变；1310基线仅2旧测试变，另新增1测试；72stage自然回收且无source漂移/owned残留 |
| 静态检查 | 两旧文件diff-check及新contract文件Ruff/format通过；未治理全项目旧静态债务 |

归档时另外发现纯测试不一定创建basetemp：额外复制脚本在red-001的目录存在断言失败，尚未复制或改变原件。该采集假设问题已单独交实际Astra R423计划；原72阶段测试证据不受影响。目录inventory为16存在、56不存在，归档实施结果另见R423步骤报告，不重跑测试或造缺失raw目录。

本轮采用精确47节点和现有环境，未执行全4751/5580，也未重跑已交付P0的42项。原全量长测35FAIL和1INCOMPLETE仍为历史记录，不能直接减去22推断新的全量通过率。软件fixture/真实仓库owner验证不代表真实模型、RGBD相机、控制器或正式研究验收。

下一轮按原顺序拆分5项租约失败：先区分嵌套public mutation注入、双连接事务DB locked、跨进程Queue.Empty，保存child退出/stderr与owner时序；必须先由实际Astra按新证据限定计划。之后再决定生产Phase11软件入口意图并复验Phase12原2FAIL+1INCOMPLETE。UTC性能、API语义、事件复现与静态治理仍未收口。

详细执行裁定、步骤、原始失败及47项验证见step-report.md、validation-summary.json、final-integrity.json和本轮plan.md/json。完整raw/DB只在本地保留；精确选择性Git证据包不能代替完整远端复现。最终fresh Astra审查与交付SHA回执单独记录。

R423归档收口：实际Astra11输入复核后，一次执行校验16个实际目录的create-only副本，459文件/17,266,800 bytes匹配；56缺失仅记录ABSENT_OBSERVED，不推断历史或造目录。72 validation树和原件身份/内容不变；清单及完整raw/DB local-only，未重跑测试。详见R423 step-report.md。
