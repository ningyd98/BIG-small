# R477 Astra补充计划：隔离pip检查上下文

实际规划者：`gpt-6-astra`。

**原始失败：** runtime-b离线安装后pip check列出big-small0.1.0缺fastapi/starlette/uvicorn和Pillow13不满足项目Pillow<13。原始stdout/stderr、安装报告和finalizer副本均已保留；64-wheel模型闭包成功安装不等同依赖校验通过。

**待验证根因：** finalizer由PYTHONPATH=src启动，子pip继承该变量和repo cwd，可能使src/big_small.egg-info被importlib.metadata发现。需用distribution位置证实；不能预先认定全部依赖错误都是污染。

**范围：** 仅本轮artifact finalizer/检查及B模型启动命令的子进程环境和cwd、R477原始诊断/解释报告；不改R473计划、不安装/卸载/升级包、不降Pillow、不删除egg-info、不改项目或旧venv。此计划不把完整项目运行迁入模型B环境。

**执行：** 先复核输入SHA。在B Python以原继承上下文只读记录sys.executable、sys.prefix/base_prefix、sys.path、PYTHONPATH/PYTHONHOME及big-small与B闭包distribution name/version/location，限定输出这些诊断字段，不打印其他环境或凭据。然后用同一个B解释器、已有model-cache独立cwd，构建child env副本并删除PYTHONPATH/PYTHONHOME，保留CUDA及其余必要环境；设置PYTHONNOUSERSITE=1并记录实际值。再次记录同样路径/distribution证据，确认big-small若消失对应的旧位置确为项目egg-info，B闭包全部distribution仍可见且来源为B site-packages。无需通过更换解释器或sys.path手工筛包隐藏冲突。
在该干净上下文运行python -m pip check和freeze --all，另写pip-check-b-v2.stdout/stderr、freeze-v2和独立step-02-runtime-b-install-v2.json及状态解释，保留原失败。仅修finalizer今后检查/模型子进程的cwd/env选择，不重跑安装。以后R473 B preflight/模型运行显式使用同一干净env与cache cwd；可以绝对路径调用本轮仅依赖模型包的artifact脚本，不把项目src重新注入B。产品capture/grounding若需原项目依赖继续原环境独立进程，通过已冻结图片/JSON交接，不能以清理环境为由删掉所需真实依赖。

**验证：** 对比前后解释器一致、B版本及distribution完整性、big-small真实来源、clean sys.path无repo src/用户site、所有B闭包依赖检查rc=0；核对原失败日志/source.before hash未变。成功要求干净检查与全部锁定wheel版本一致，所有真实B冲突均仍由pip报告。若big-small实际装在B site-packages、清洁后仍有冲突、或B脚本实际需要项目包，停止该路径并保存证据，另交Astra，不删依赖/屏蔽包。

**边界：** 只读诊断及一次干净检查限5分钟，计入原依赖40分钟及总3小时预算，不重置；无联网、无权重加载。此轮通过仅证明隔离模型闭包校验恢复，实际FP8加载、双图/质量按R473继续分别验收。原报告的失败在追加解释中标注其上下文，不覆写为曾经通过。

**输入SHA：**同目录plan.json的input_sha256记录AGENTS、R473计划、finalizer、镜像resolver及本轮全部原始诊断的path/bytes/SHA256；实施前逐项复核。
