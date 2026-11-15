# 阶段3环境前置补充：真实socket守卫测试

实际规划模型：**gpt-6-astra**。状态：**PLAN_ONLY_ENVIRONMENT_VALIDATION_NOT_RUN**。本补充不修改原计划、生产代码或测试。

## 原始失败与判断

`/tmp/bigsmall-v4-execution/offline-unit.log`：`1 failed, 16 passed, 3 skipped in 0.47s`。唯一失败 `test_network_guard_stops_actual_socket_before_connection` 在已进入NetworkDenyGuard后创建socket时，被默认沙箱以 `PermissionError: [Errno 1] Operation not permitted`拒绝；尚未到达client.connect，也未验证自有审计钩子。

已读代码确认：guard拦截 `socket.connect`，先记attempt再抛 `OFFLINE_NETWORK_DENIED`；该测试只尝试字面loopback `127.0.0.1:9`，要求该异常及一个attempt。因而本轮应验证运行前置条件，**不需要修改生产或测试**。

## 最小执行计划

1. 实施前复核本补充记录的guard/测试SHA及关键代码：guard先进入、connect仍在pytest.raises内、目标未变。原始log逐字节副本在 `addendum-socket-guard-environment-20261115.evidence/`。
2. 可在用户已授权的软件回归范围内，向自动审批提交 `exec_command(sandbox_permissions="require_escalated")`，**仅复跑下面一个node**。这请求允许创建socket对象，仍必须由Python审计钩子在connect进入系统调用前阻断；不得联网、DNS、模型推理或做额外连通性测试。
3. cwd固定为 `/home/ningyd/.codex/worktrees/v4-marker-ambiguity/BIGsmall`，显式固定源码，字节码/pytest缓存关闭，basetemp及stdout/stderr用全新/tmp路径，保存工具审批结果、命令、环境与退出码，不覆盖原失败。不要设置可泛用于网络动作的宽泛prefix授权。
4. 仅 `1 passed`、exit0且测试/guard未改可接受。通过不代表整个单元文件、三个skip集成或全仓检查通过。若审批拒绝，停止该验证并说明原因，不换目标、移除guard或绕过审批。
5. 若提升后仍失败或出现新根因，保留原错，回到Astra；不能把PermissionError当通过、直接skip、mock掉connect或只触发sys.audit来代替真实socket.connect验收。

拟执行命令（**尚未由本子任务运行**）：

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/ningyd/.codex/worktrees/v4-marker-ambiguity/BIGsmall/src:/home/ningyd/.codex/worktrees/v4-marker-ambiguity/BIGsmall /home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python -m pytest -p no:cacheprovider --basetemp=/tmp/bigsmall-v4-socket-guard-escalated-01 tests/test_sol_molmo_offline_regression.py::test_network_guard_stops_actual_socket_before_connection -q
```

建议审批说明：默认沙箱在socket构造阶段阻止了这项已授权软件测试；申请只运行这个测试，使其到达现有审计守卫并在任何网络连接前抛错。不会运行模型、真实网络或生产修复。

## 全仓测试状态

`full-project-status.json`记录exit124、600秒、complete=false，输出约2%进度、5个F，未列出失败名称。结论仅为 **全仓未完成且观察到失败，原因未定位**。保留原log/status，不宣称全仓通过，不根据这些无名F修生产代码、不删测试或改标准。按父任务要求，独立阶段3工作继续；本补充不重新发起全仓测试。

## 验收边界

不扩大三个新增文件的范围，不修改任何代码或阈值；不新增网络/模型/物理执行。require_escalated仍须工具实际审批，本文不将它视为已经获批或执行。补充JSON保存输入绝对路径/SHA、原始副本、计划步骤和原计划未改哈希；独立 `.SHA256SUMS`核验此追加包。
