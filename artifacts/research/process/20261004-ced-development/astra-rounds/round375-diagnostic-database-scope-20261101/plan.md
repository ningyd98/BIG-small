# R375：诊断运行的数据库作用域对照

实际规划模型 **gpt-6-astra**，2026-11-01。只制定新artifact环境适配与一次复验计划；不改产品、测试、旧runner或正在执行的continuation。

原 `test_phase11_simulation_workbench_backend.py` 模块6通过/1失败，18.016秒；最后websocket测试403行期望 `run_state` 却收到 `job_created`。原invocation为整个模块注入单个SIMULATION_RUNTIME_DB；service优先使用该env，websocket又优先回放持久runtime事件，因而有充分静态证据怀疑此前测试job事件跨测试流入。**这是runner作用域假设，尚非已确认产品缺陷。**

已核对完整模块7个测试、工厂及服务：_client/_app均设每测试tmp_path/artifacts，唯一直接service构造也使用该路径；create_app不立即构造workbench DB。移除SIMULATION_RUNTIME_DB后，只有artifact_root恰为相对`Path("artifacts")`才回退历史data，而这里为绝对tmp_path。保留stage级绝对DASHBOARD_ARTIFACT_ROOT兜底、独立MODEL_CONTROL_DB及其他防护；最终测试内部多app仍共享该测试自己的目录，不再添加额外隔离。

**唯一变更与命令：** 在R375新目录创建小型独立环境adapter，按原invocation迁移输出/cache/resource路径，然后只删除SIMULATION_RUNTIME_DB键；不编辑R374任何冻结文件。使用plan.json的完整原7节点及原顺序（静态AST与原invocation已逐项一致），一次完整模块pytest。不能只跑失败节点，也不再重复原错误环境作RED。

**前置：** 等当前continuation-v2全部终态且所有子进程已清理，再串行运行；不打断当前session40005。复核19个直接输入SHA与原R373源清单、dirty候选未漂移。新目录必须不存在；不安装、不调用付费模型/硬件、不传sandbox_permissions。

**额度：** child60秒，TERM5秒，清理总15秒，outer90秒；一次、零重试。必须在原报告预留截止 `2026-11-01T10:18:46.463857+00:00` 前仍剩至少90秒才启动。原8小时墙钟和最后15分钟报告保留不变，不退款group05旧失败。若续跑太晚则NOT_RUN_BUDGET，只保留待证假设。

**验收：** 同7节点同顺序7通过、无失败/error/skip、exit0、无timeout、源不变；保留完整stdout/stderr/events/JUnit/时长/退出/清理。进程结束后只读列举产生的simulation_runtime.db，确认位于各测试basetemp/artifacts下，而非共享stage runtime DB；不假定每测试都会建DB。原DB与日志原样保留，不把新结果覆盖原6通过/1失败。

对照通过且路径证据符合时，只能报告“修正runner数据库作用域后，该完整模块在此次对照通过”；不能报告已修产品缺陷或排除所有顺序问题。任何新失败不修、不重试；其他本轮问题不纳入。仍不代表全流程/真实闭环/正式研究通过，不改变旧UTC600秒边界。

派生汇总可追加R375新尝试及环境身份，仍保持4732唯一节点计数，同时列出R374原失败；不得以新通过覆盖旧结果。数据库只需文件路径/hash清单，注明相邻WAL/SHM；不直接用SQLite打开或checkpoint原件。若后续确需内容读取，先复制已静止DB及已有WAL/SHM到新artifact、记清单和快照局限，仅对副本读取。
