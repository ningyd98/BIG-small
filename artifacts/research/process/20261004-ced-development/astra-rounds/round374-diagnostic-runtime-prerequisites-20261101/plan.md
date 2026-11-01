# R374：运行前置与诊断编排恢复

实际模型 **gpt-6-astra**，2026-11-01。仅修本轮artifact运行前置/编排，产品、测试断言及golden不改。当前用户已切换danger-full-access/approvalnever；后续工具**不得传sandbox_permissions**。

**已知：** R373普通组01–03均900秒超时，无JUnit、源无漂移；定位到最后setup结束节点不等于根因。组04的九例确认缺R223资源变量，源码还要求`BIGSMALL_R223_CASE_ROOT`；finally中的缺变量可能遮住更早错误，不能宣称只补env便一定通过。旧父进程仍在旧sandbox祖先下只是环境线索；挂起的capabilities测试自己已设临时artifact root，不能归因全局扫描或宣称历史DB已经污染。

1. **安全停止旧编排。** 重核验父/子PID、启动时间、命令、祖先和PGID（68429/143025只是线索）。先SIGSTOP准确父进程阻止发下一阶段，再TERM准确子进程组、5秒后必要时KILL，总清理15秒；确认所有本任务后代已结束。随后对停止父进程TERM并CONT令其退出，原工具/session能reap则reap。不得只杀父留下独立session子进程，不得pkill。写新R374中断回执，不覆写原结果；自然已结束则尊重真实终态。
2. **补确定前置。** 所有新pytest阶段预建非symlink R223 resources/cases目录并设置两个变量。保持R158/R235兼容env、插件和原golden。普通API也在导入前设置新MODEL_CONTROL_DB、SIMULATION_RUNTIME_DB、DASHBOARD_ARTIFACT_ROOT；这是防止默认写入的隔离改进，不是污染定论。测试自身monkeypatch仍有效。
3. **一个新环境实节点，最多30秒。** 新工具直接启动原 `tests/test_phase10_2c_level0_contract.py::test_dashboard_has_no_level1_or_hardware_write_route`，全新输出/DB/env，源码不改。通过只说明新进程可完成，sandbox与旧测试顺序仍未区分。若仍挂，允许一次15秒纯FastAPI/TestClient健康请求（不导入产品）；若原节点通过而需定位顺序，最多10个原先紧邻且完成节点+目标的一次60秒前缀诊断。可跳过条件诊断，不再做长考古。
4. **立刻优先完整UTC/T3。** 新runner读取原源清单和原batch-start，新目录输出；先UTC memory、UTC sqlite，再另七T3节点，原3600/600秒上限不变，已真实运行项不重复。旧父已载入代码，改旧文件不能控制它；复制成新runner，仅改env、阶段路由、终于清理和小模块限时。不要再次prepare或重置原8小时墙钟。
5. **精确补跑和继续覆盖。** 九个R223确认缺env节点仅一次300秒修前置重跑，排在至少一个完整UTC尝试启动之后。其余已失败节点不随意重跑；从未启动阶段依原预算继续。普通API可拆成新进程60秒段，其他普通模块最多300秒且不超过父stage剩余额度，避免混组每次再等900秒。原01–04从未开始的尾部另允许各300秒、合计1200秒续跑，排除已完成/已失败/原挂起节点；不足则如实记未完成。

额外诊断child最多405秒，尾部续跑最多1200秒，均受**原R3738小时墙钟**限制，不重新计时；末15分钟仍留汇总。若时间不够优先本次完整UTC九节点，不用短合同冒充。原双backend合计600秒验收仍未被较长诊断替代。

所有stdout/stderr/events/JUnit/结果/缺失/清理均新目录保存，源无漂移才运行。覆盖仍以4732逻辑节点为分母，历史attempt和有限诊断attempt分别列示。原三个超时、组04失败和中断不抹掉。phase12/operational_windows不是纯TestClient节点，本计划不把它们统归sandbox。

直接输入27项bytes/SHA见plan.json。运行中组04已按时点复制失败行和最后完整事件到 `inputs/live-software04-snapshot.json`；**不锁定会自然追加的原事件/coverage聚合文件**。计划只由Astra读取/写入，没有信号、测试、产品或网络执行。
