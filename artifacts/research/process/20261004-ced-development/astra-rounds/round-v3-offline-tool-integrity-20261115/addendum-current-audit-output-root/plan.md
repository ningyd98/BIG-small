# 当前源码审计输出根补充计划

实际规划模型：`gpt-6-astra`。**PLAN_ONLY_NOT_IMPLEMENTED**。仅路径诊断与计划，无实现、模型、仿真或589帧重跑。

独立微型probe确认：audit_child当前等价调用 `output_path(output,[manifest.root,ROOT])`，使本来批准的 `ROOT/artifacts/research/process/20261115-v4-marker-ambiguity/offline-regression/<new-run>/current.json` 被 `PROTECTED_OUTPUT_PATH` 拒绝；独立/tmp输出通过。两候选路径始终不存在。原脚本与输出已冻结，命令及SHA见plan.json/inputs.json。

根因是当前源码根ROOT与历史归档输入树采用同一种整树保护，但批准repo输出本来就在ROOT后代。另 `_PROTECTED_INPUTS.add(ROOT)` 还会使末尾_write重复拒绝，因此必须同时修正即时检查和后续登记。

限定只新增offline module与tests：新增纯helper，对source_root与ROOT先resolve。历史source_root不等于ROOT时继续保护整个历史树；当前源则保护ROOT/src、assets、scripts、tests等实际输入目录/已绑定源文件，而不保护整个ROOT。统一用这一结果进行audit_child的output_path额外protected与_PROTECTED_INPUTS.update。manifest.root、原主/Gemini、V3、baseline、astra原有保护不变，全局输出allowlist/路径解析与独占规则不变。

保留current源初始化、_expected_sources、validate_source_imports与完整来源前后校验。不能通过删除全局保护、扩大输出allowlist或跳过源码验证解决。生产源码目录仍在allowlist之外并明确受保护。

RED保留当前probe错误拒绝；GREEN新增纯路径测试：current的批准repo与/tmp新文件均允许；historical树外批准输出允许、树内及祖先拒绝；current src/assets/scripts/tests和既有保护根仍拒绝。用monkeypatch隔离保护集合，既测试即时检查，也测试登记后的末尾写路径检查。只调用validator，断言候选文件不存在，不实际mkdir/write，不计算帧。

使用固定隔离树PYTHONPATH、共享venv、PYTHONDONTWRITEBYTECODE=1、pytest禁缓存及唯一/tmp basetemp。聚焦路径测试、现有完整性/phase/fault相关软件测试与Ruff；无需网络/EGL权限提升。通过独立review后重新冻结3入口SHA，再启动原27。父任务先前11节点/599来源通过不冒充本轮修复验证。本轮不改controller、physics、evaluator、相机、阈值或原始实验字节。

实施前核对输入与已授权并行改动，追加实施receipt；原计划与失败不可覆盖。新的根因/范围扩大再次Astra。
