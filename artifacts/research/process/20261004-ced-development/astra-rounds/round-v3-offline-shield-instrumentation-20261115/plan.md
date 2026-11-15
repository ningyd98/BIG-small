# V3 离线 SafetyShield 插桩补充计划

规划模型：**gpt-6-astra**。状态：**PLAN_ONLY_NOT_IMPLEMENTED**。只计划、静态读取与证据冻结；本轮没有修改源/测试、启动仿真、联网、模型或提交推送。

## 失败与独立核实

原 `offline-strict-fault-green-01.log`：**1 failed, 2 passed in 13.47s**，POST 期待 PRE→EXECUTE→POST，实际 PRE→EXECUTE→PRE→POST。原始日志在 `evidence/` 逐字节保留，退出码1。原日志没有完整argv，不能把下述建议复跑命令称为原始命令。三个原case关键JSON、replay与manifest已逐字保存；`episode-file-hashes.json`绑定三个完整输出目录内所有文件，DB/完整raw仍保留原本地边界，不宣称本计划包是完整复现包。

独立读真实POST episode确认：planning_passed=true、point=4/cloud=1、零真实推理与网络；worker FAILED，terminal为`SAFETY_SHIELD_POST_REJECTED_OR_LIMITED`；safety_checks只有PRE allowed=true与POST allowed=false，各有21个真实rule结果。首MOVE_ABOVE执行一次，controller_return_step=end_step=835，起点120，无diagnostic_settle_steps；marker_frames仅before、post-cloud、pre-00-move_above、after。PRE/HARD另外两例也已达到各自真实门禁，不再是早期规划失败假通过。

`source-revalidation.json`确认原case记录的8个生产模块和两个新增离线入口SHA全部与当前字节一致。HEAD为`3ef1e028ccd471f887eb5b8154c98c3eb9ccfb82`，测试SHA为`2831b4fffa1b40374a1af2b87bc7249715b0102792096923e91a6c502389c086`。输入路径、SHA和快照见inputs.json；无新测试或仿真运行。

## 根因与修改边界

生产 `SafetyShield.post_check` 原样 `return self.pre_check(context)`。现测试用通用wrapper分别包装两方法，原post动态调用已包装pre，于是内部真实规则评估被记成第二次外部PRE。组件真正的PRE/POST边界并未增加；不是生产多执行一次动作。

仅修改新增测试文件的 `test_actual_worker_stops_at_injected_safety_boundary`；如传递独立内部调用记录需要，最小改 `_assert_reached_safety_boundary`。不得改生产shield或loop，不mock整个shield，不用假allowed替代规则，不把期望改成四事件、不去重外部事件、不删除严格安全断言。

具体实现：

1. 在monkeypatch任何方法之前保存 `original_pre` 与 `original_post`。
2. 测试局部维护按Shield实例区分的POST委托深度。POST wrapper调用 **original_post** 前递增，使用try/finally恢复原深度，即使规则异常也不能遗留抑制状态。不要临时改回类方法，不以original_pre替代original_post。
3. PRE wrapper无论内外总是调用original_pre，原verdict必须allowed且evaluated_rules非空。若是同实例POST内部委托，仅存独立delegated_pre记录（context及contract/step对象引用），原样返回真实verdict，不追加外部calls、不注入PRE。外部PRE照旧记录并只在PRE用例注入拒绝。
4. POST wrapper获得原post的真实允许verdict，退出委托保护后记录外部POST，仅在POST用例注入拒绝。保留真实evaluated_rules；注入只改变现有allowed/decision字段。
5. 外部calls仍精确PRE→EXECUTE→POST，contract和step的`is`相同断言保留；POST有且仅有一次内部delegated_pre，context与真实POST一致且映射同contract/step。PRE/HARD内部委托为0；每个目标注入恰一次，非目标阶段不注入。完整真实规则数量不硬编码21，只检查真实返回结果非空并保留原结果。

这只修测试观测范围，原生产规则执行顺序、决策和拒绝条件保持。

## RED、验证和运行前置

先将本轮原日志与三个失败/通过case当作修订前RED证据保留；不能清理或覆盖。实施前核对inputs和plan.json中的两个函数哈希、实际导入路径。采用固定PYTHONPATH与绝对共享venv解释器，MUJOCO_GL=egl在import前设置，PYTHONDONTWRITEBYTECODE=1、pytest禁缓存、新/tmp basetemp。

父任务在与已匹配成功的相同实际环境中精确复验三个节点；若工具需要提升权限，按已有授权走require_escalated审核，拒绝则不绕过。NetworkDenyGuard始终启用、V3只读；不改图像/深度/校准/哈希/渲染参数求通过。

```sh
PYTHONDONTWRITEBYTECODE=1 MUJOCO_GL=egl \
PYTHONPATH=/home/ningyd/.codex/worktrees/v4-marker-ambiguity/BIGsmall/src:/home/ningyd/.codex/worktrees/v4-marker-ambiguity/BIGsmall \
BIGSMALL_V3_REGRESSION_ROOT=/home/ningyd/Documents/Codex/2026-11-14/x20-gpu-nvidia-smi-nvml-gpu/outputs/next-round-repair-40-20261115-v3 \
/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python -m pytest -p no:cacheprovider \
--basetemp=/tmp/bigsmall-offline-shield-instrumentation-green-01 \
 'tests/test_sol_molmo_offline_regression.py::test_actual_worker_stops_at_injected_safety_boundary[PRE]' \
 'tests/test_sol_molmo_offline_regression.py::test_actual_worker_stops_at_injected_safety_boundary[POST]' \
 'tests/test_sol_molmo_offline_regression.py::test_actual_worker_stops_at_injected_safety_boundary[HARD]' -q
```

cwd为上述隔离工作树，目录已有时用新编号。预期三个node都通过，无skip；三份episode和完整stdout/stderr/退出码独立保存。全部继续断言：两阶段规划通过、point4/cloud1、零模型load/generation/真实cloud请求、网络空、worker FAILED、component_success=false、diagnostic_complete=false和精确终止原因。

- PRE：唯一PRE拒绝，0执行/POST/actions；HARD：注入恰1，PRE/执行/POST/checks/actions均0。
- POST：原PRE与POST真实规则先允许，再注入；外部事件各1、对象引用一致、safety_checks阶段严格PRE/POST且allowed=[true,false]、1动作；无diagnostic_settle_steps，并核对end_step==controller_return_step。marker_frames必须含pre-00；不得出现任何post-动作帧、后续pre动作或terminal-stability，finally的after允许。已有更弱前缀检查不能放宽为允许后续其它索引动作。
- 旧三份早期规划失败仍须被现有负对照拒绝。先完成精确三node，再做这三个快速负对照、该测试文件Ruff无缓存及只读生产SHA核对；不以其它全绿替代三node。

出现新环境/规则/断言失败，保留新原始字节并暂停相关修复再交Astra；不会由本计划授权调生产安全阈值。

## 与并行计划协调及验收

另一Astra正在负责offline工具完整性及该测试文件其他函数/新增负例。本轮三新增文件均记录 `expected_authorized_change=true`，意为存在独立待实施计划，不能视作任意diff许可。父任务串行整合；本轮只拥有上述两个函数，不整文件覆盖，不改offline module/CLI。实施前复核两个函数切片SHA；其它已授权变动写新输入回执，列对应计划与最终SHA，原快照不覆盖。若双方触及同一函数或改变本根因，先协调/重新规划。

验证通过仅证明真实安全边界测试插桩正确；27例离线闭环仍需其原计划验收，不产生真实Sol/Molmo端到端成功率、硬件或正式研究资格。软件、仿真回归、研究验收分别报告。生成步骤报告汇入父阶段总结，保留全部历史失败和冻结原件。
