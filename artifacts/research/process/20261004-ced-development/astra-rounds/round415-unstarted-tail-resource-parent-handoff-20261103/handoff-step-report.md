# R415 目录前置修正与续跑交接步骤报告

实际 Astra 计划先于实施；原产品、测试、R413/R414冻结脚本和spec字节保持。

075原模块耗尽既定1800秒额度：TIMEOUT，实际exit=-15，外层1800.219674秒。原supervisor按既定策略对两个owned进程发SIGTERM并完成回收，source_drift=[]、remaining_live=[]、errors=[]。交接操作本身没有发送信号。模块14个已STARTED节点中，11项三阶段PASS、2项call失败、1项未完成；没有JUnit终态文件，因此以已保留逐阶段事件报告，不能称整个模块通过。

随后原R414 parent在创建第一个未启动尾部的r223/resources时实际FileNotFoundError，自然exit=1。此时tail仅有resources与resources-a，尚无invocation/events/child；该原目录保留不用。076管理guard也未触发pytest或管理拒绝，因为parent更早自然结束。真实父终态与错误保存在R414原日志及本轮preflight回执，不能把目录错误计为pytest断言失败，或把模块长耗时归因目录错误。

确认父PID523308/starttime16358519消失、旧owned身份全回收后，新队列保留此前1368个已启动唯一节点，只为075的38个从未STARTED节点派生600秒单node任务。原075已经开始但未完成的runtime-gap检查不重跑。076换新id/fresh路径保持同4项原序和1800秒；其余原序继续，队列共269项。

新derived_execute仅更改资源子目录mkdir(parents=True, exist_ok=True)与tail身份namespace；fresh根仍排他创建。AST反向归一化与compile验证通过，原run_one/bounded_stage、预算、环境、依赖、过滤、源保护和清理逻辑复用。初始待执行尾部同样以正确父目录准备；未来自动尾部分支的静态证明与是否实际执行分开记录。

075两项失败为F20真实回执中runner_invocation_count=0（应为1），以及paired-summary验证期望accepted实际evidence-gaps；原始失败保留在总账。F20只读源/回执分析另见R413 reports/f20-receipt-audit.json；本轮目录修正未修改该产品缺陷。

此文件是交接完成快照，后续269项此时仍在运行。最终总账固定4753唯一node、原073/076两处零行为管理slot另列、重跑已开始节点0；最终阶段完成状态由研发进展/测试报告汇总。
