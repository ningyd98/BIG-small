# R414 工作台数据库前置与未启动队列交接计划

实际规划模型：**gpt-6-astra**。本轮承接用户一次全量长测授权，只修运行前置，不改产品/测试、不新增已开始节点尝试。精确输入 SHA、七节点顺序及步骤见同目录 plan.json。

R375原始同序对照已证明：模块共享 `SIMULATION_RUNTIME_DB` 覆盖测试的 `tmp_path/artifacts`，持久WebSocket事件可跨test污染；原6P1F在只移除该env后7P。当前源码仍有同一优先级和replay链，R413 prepare再次为073注入共享DB。规划时073仅有预建资源目录、没有启动证据；实施前必须再查。当前050及其后独立任务继续。

- [ ] 复核pins、原parent PID/starttime/session与073未启动状态。在R414写block-intent，然后在原073目录**排他新建** `result.json`，明确 `BLOCKED_PRECONDITION_R414_DB_SCOPE / launched=false / pytest_attempts=0 / returncode=null`，链接本计划与后继；不造invocation、child退出、JUnit或cleanup。写后复核无竞争。
- [ ] 让原队列自然推进。冻结run_one发现073已有result后会在Popen前拒绝，并使parent自然退出；保存原真实退出/错误文本，分类EXPECTED_HANDOFF，不算pytest失败。不发信号、不改内存或旧spec。
- [ ] parent真实结束且前一stage清理/source成立后，按冻结402 specs原序生成resume-manifest。所有已有invocation/result/STARTED的任务保留原账，绝不重入；事件不确定则不猜。唯一073替换为新id `py-module-073-r414-db-scope`。
- [ ] 在R414创建新spec和小resumer。deepcopy073，fresh目录及外置basetemp，仅 `env.pop('SIMULATION_RUNTIME_DB')` 改变语义；MODEL_CONTROL_DB、绝对DASHBOARD_ARTIFACT_ROOT、R235/R223及其余env/argv/七nodes原序全保留。反向归一化证明唯一差分，静态检查后不另开helper审查链。
- [ ] resumer用importlib加载冻结R413 run_batch.py，直接调用原execute，不更改其ROUND或函数。原run_one允许登记新id规范spec，原supervisor/清理/exit-first保护照常；其余从未invoked阶段仍用原spec/原id续行。新073完整模块仍用原未消耗1800秒额度，清理及未STARTED尾部规则继承，不重置其它额度。
- [ ] 验证new073原序7P/exit0/R235/source/cleanup，或忠实保留失败。文件级盘点实际DB路径，不能开旧SQLite。总账仍4753唯一node，原073只是未启动管理阻断，七个节点只按后继实际一次结果计数。既有结果及4个Chinesechecker失败不改写。

只追加原073管理result、新id spec、恢复原队列正常追加输出和R414新证据；不修改R413原plan/prepare/driver/stages/spec073，不移除其它模块或browser/Phase12的SIMDB。若073已启动、发生竞争、parent未结束或清理/来源不成立，停止受影响交接，不打断当前pytest或偷偷重跑。

最终交付窄继承R413：可精选本轮小计划/交接/步骤/关键结果；大raw/DB保留本地，无新Git次数。计划自审覆盖了未启动证明、真实parent退出、环境唯一差分、源保护与唯一账本；目前没有实施交接或运行测试。
