# R458 — 可继承的禁止采集测试替身

实际 gpt-6-astra，2026-11-08。仅规划，不改产品/测试，不执行验证或API。输入22份完整副本与当前SHA在 `intake/input-pins.json`，包含现六源码/config/docs、新测试、原失败stdout/JUnit/result、R457计划及监督器。未重审R439历史来源链。

## 已核实原失败与根因

R457 sol-green：7 PASS/1 FAIL，pytest1.24s，监督2.003457946s，rc1、reaped、无漂移/残留。失败节点 `test_sol_role_family_profile_and_entry_binding` 第300行导入pilot；pilot定义 `class PerturbedCapture(MuJoCoCaptureSession)` 时报 `TypeError: function() argument 'code' must be code, not str`。此前测试已将capture.MuJoCoCaptureSession替换为lambda以阻止渲染，导致可继承类变成函数。静态片段已复制至intake。

该错误发生在测试制造的导入环境，尚未执行pilot入口，不能以7个通过节点宣称pilot family入口通过。原8节点预期RED仍有效；本失败原件已足够，不新增RED或重跑失败作诊断。真实API/MuJoCo/render/service计数全部0。

## 最小修复

仅允许 `tests/test_openai_sol_visual_migration.py` 中该节点的禁止采集替身改变：

- 定义局部 `class ForbiddenCapture`，其 `__init__(self, *args, **kwargs)` 立即 `pytest.fail("renderer started")`，不要调用真实初始化。类本身可被继承，实例化仍必失败。
- 用该类替换capture.MuJoCoCaptureSession，保持现probe先执行与pilot随后导入的顺序。不要移除捕获禁用保护来使导入通过。
- 若模块可能因测试顺序预先存在于sys.modules，导入后通过monkeypatch将pilot绑定的MuJoCoCaptureSession和真正使用的PerturbedCapture入口也指向该禁止类，保证旧绑定不绕过禁止采集。补丁只在本节点作用域，不能修改产品类定义或删除模块缓存。
- 保留实际resolver、probe.run_probe、pilot.run_ced_pilot的family拒绝路径，保持现有软件前置fixture；`calls == [MODEL, MODEL]`、无HTTP rows、BLOCKED/NOT_RUN、无active切换等断言不减弱。不能改成mock整条pilot入口或允许构造真实renderer。

不修改Sol请求参数、角色匹配、官方URL、产品业务语义或R457设计。当前六源码/config/docs为已实现R457输入，需按当前SHA复核。ROOT补充确认R457 formatter已执行一次；本轮另明确允许在原六源码及新测试共七个Python路径执行一次 `ruff check --select I --fix` 和必要的 `ruff format`，用于fixture修改后的import排序/格式整理，完整argv见plan.json。然后执行尚未运行的静态检查。当前未执行或发现新lint失败，不预先推测其它修复。产品差异只能是纯import排序/格式，单独记录diff/SHA，不能借此改变语义或扩大业务修复范围。

## 一次修复验证和原剩余阶段

创建新的R458 runner，沿原R413 bounded_stage，exact展开规格已在 `spec-templates` 和plan.json。不要调用会因旧失败green阻断的旧R457runner，也不改旧result为通过；新runner明确要求本轮fixture-green通过才能继续。独占新输出目录和 `/tmp/bigsmall-r458-*` basetemp，旧原件全部保留。

1. 唯一fixture-green：完整新测试文件8节点，预期8 PASS；需要覆盖整文件以发现替身/模块缓存造成的测试间影响。必须真正到达pilot入口、两次family转发断言和禁止renderer/HTTP断言。
2. 唯一adjacent-green：原R457未运行的原selector清单，argv完全不扩展，仅更换R458输出/env/basetemp。
3. 原R457未运行的ruff、format --check、mypy各一次；路径与范围不扩展。未运行前不预设会出现其他问题，也不授权其修复。

fixture child180s/outer300s，相邻240s/360s，静态120s/240s；串行attempt1，无新增probe/RED/全套/实际调用。每阶段原stdout/JUnit/events/result和source pins保存。任何计划外失败、新根因或语义范围扩大停止相关修复并新Astra。

## 验收与证据

当前源pins吻合；只有测试替身语义更正（若执行前轮格式化，另列纯格式差异）；8节点及未用相邻/静态通过。记录R458 step-report并汇入R457迁移结果，保持原sol-green 7/1失败和8 RED原件，清楚区分“修复后8 PASS”与历史状态。

本轮不运行真实API、MuJoCo、render、GPU服务或硬件，不读密钥、不改DB/active profile、不恢复旧研究协议。正式研究NOT_ACCEPTED及新source-generation要求不变。
