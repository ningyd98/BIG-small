# R413 全量长测步骤报告

被测分支 `research/20261004-continuation`，代码提交 `ab18abd0f82a024b62f4423c946c6585f8d18c65`；官方 real_robot 源码指纹 `3bfb7dbb8036b8389fa9a9bccdb2e961a1fd225be2d42b511539044e944995f4`。

运行区间：2026-11-03 18:11:58—2026-11-03 23:08:22（北京时间）；全流程墙钟 17783.674 秒（4.940 小时）。UTC 起止为 `2026-11-03T10:11:58.963126+00:00` / `2026-11-03T15:08:22.637110+00:00`。

实际gpt-6-astra的R413计划先于采集/运行，R414数据库前置与R415资源父目录前置均先取得独立Astra限定计划，再实施。三轮计划与冻结输入SHA保留；本轮没有产品或测试修复。

一次新采集4753唯一节点/288模块，软件4751节点各STARTED一次。最终4709PASS、35FAIL、6原backend SKIP、1INCOMPLETE，2真实数据NOT_RUN另列；全局重复STARTED=0。前后源pin和tracked开发源码一致。关键9回归及94闭环通过，UTC性能600秒合计门槛未满足。全部原失败、缺失JUnit与原075预算终止不覆盖。

R414在073零行为时管理阻断旧父，7项新scope完整PASS；R415在旧075已TIMEOUT且旧tail尚未invoked的真实目录错误后，只续38个可信未STARTED节点。原076guard为零行为，后继同4项原序。两管理slot与测试尝试分开。

非Python22步骤的实际terminal、退出码与原始日志全部汇入测试报告。浏览器42PASS+1原有SKIP，旧19项全部PASS；前端Vitest43PASS。7个静态/前端检查未通过或未进入有效类型检查。Phase12预期5580行，实际5580行，最终verifier=PHASE12_REJECTED，门控论文权威行=0；raw完成声明与内层支持单独审计。

开发验证、真实软件/仿真执行、正式研究/硬件验收分别记载。完整raw/DB留本地；精选交付不冒充完整远端复现包。测试代码基线为ab18，后续Git证据提交与fresh review/远端SHA回执独立保存。

完整结果：[研发进展](reports/development-progress.md)、[测试报告](reports/test-report.md)、[最终来源核验](postflight/checks.json)。
