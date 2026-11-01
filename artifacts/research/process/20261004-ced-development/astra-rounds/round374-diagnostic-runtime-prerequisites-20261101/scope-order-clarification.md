# R374 执行前顺序解释：相同额度内提高未启动覆盖

实际解释者：**gpt-6-astra**，2026-11-01。只读复核并写本解释；未运行测试、修改产品、发信号或改旧manifest。

**允许，不需另开修复轮。** R374已经允许将同组未启动尾部拆成有限模块进程，目标是恢复覆盖；它没有要求维持原模块字典序。尚未消费续跑额度前，对完全相同的候选集合做组内稳定置后，属于既定诊断编排范围。它既不重试已开始节点，也不增加/跨组转移额度。

只批准下列最小顺序变化：

- `pytest_software_01`：把第一项 `pytest_software_01_remaining_01`（`tests/test_phase12_2_runtime_authenticity.py`，51个未启动候选）移至该组第35项；其余子项相对顺序、ID、内部node顺序、timeout和全部字段原样保留。
- `pytest_software_02`：把第一项 `pytest_software_02_remaining_01`（`tests/test_operational_windows.py`，31个未启动候选）移至该组第38项；其余子项相对顺序、ID、内部node顺序、timeout和全部字段原样保留。

其余十组及组间顺序不改。不推测其他模块“更快”而再次排序。原证据只能证明这两个模块各有一个节点占住旧混组直至900秒超时；不能证明余下节点都会超时。置后是避免其余模块再次失去执行机会的有限覆盖安排，报告必须注明“按已观察阻塞风险稳定置后”，不是性能排名。置后模块仍保留在分母，余额不足时记NOT_RUN_BUDGET，不能省略或算通过。

## v2 冻结与验证

保留 `continuation/planned-stages.json`、原runner/pins及所有旧件。在同级新目录 **`continuation-v2/`** 创建后继：复制 `run_remaining.py` 和 `sequence.py` **字节不变**（它们以HERE定位manifest/账本、以HERE.parent定位R374 runner，采用同级目录即可保持正确路径），写新 `planned-stages.json`，仅置换上述两个children数组。若需注明来源/解释，另存独立冻结记录，不为此改manifest其他字段。

冻结前用stdlib比较证明：group顺序和预算相同；按child ID映射的完整对象一致；每组node多重集合相同且无重复新增；唯两组数组发生上述稳定置后；所有其他组逐字段相同。新manifest仍引用原源baseline与原未启动集合，不能重新收集或把原started/failed/passed节点放回来。新pins记录旧/新manifest、字节相同脚本、本解释的SHA及有序ID差异。允许一次新脚本`--inspect`作静态运行前核验，不启动测试。新v2账本必须不存在，输出根独立。

原每组预算（01/02各300秒等）、API60秒/其他300秒、清理reserve16秒、group05余额869秒、原八小时起点与最后900秒报告保留均不变。实际有效timeout继续取子项上限、组余额减清理reserve、总墙钟余额减清理reserve之最小值；累计monotonic计费不改变。九个T3的3600/600秒和原双backend600秒验收也不变。

## 只替换等待器，不影响运行中的T3

目前只读观察到旧continuation无 `budget-ledger.jsonl`；执行者必须再次核验。用户/ROOT报告的等待器是session13622、PID222214、starttime_ticks3843748，T3父PID194576/session61481是**不得触碰**的独立运行。PID只是定位线索，不可直接照抄发送信号。

1. 核对旧等待PID的启动时刻、完整cmdline确实是旧`continuation/sequence.py`，并确认它仍在等待、没有子进程、旧预算账本/children执行产物不存在。不要创建R374全局STOP文件，不要发进程组信号。
2. 为消除“检查后恰好exec”的竞态，仅对已核验的等待PID发SIGSTOP，再读取其cmdline/starttime和账本。若已经exec成run_remaining或已有任何续跑消费，**取消本次重排**，不得重置账本；按原安全控制恢复该准确进程并报告已开始，等待进一步裁决。不能误把它当空等待器终止后重新跑。
3. 若冻结后仍是同一空等待器，对**该单PID**发SIGTERM再SIGCONT令其终止；通过原session回收/确认消失，保存新replacement receipt。禁止pkill、killpg、终止共同祖先或影响T3/session61481。
4. 再核验原T3进程未被信号影响、新v2未消费，启动一个新当前环境等待器`continuation-v2/sequence.py`并保存PID/starttime/session和脚本SHA。它沿用十个T3/R223真实结果全部存在且reaped的条件，随后才exec新v2 runner。不能同时留下两个等待器，也不能提前并行跑重测试。当前approvalnever/full-access下不传sandbox_permissions。

如原等待器自然退出，先证明其未启动续跑且无账本，才启动v2；若总墙钟已到则保留NOT_RUN_BUDGET，不能重设时钟。整个顺序替换只在“续跑尚未开始”成立时适用，正常T3事件文件追加不属于input drift。

证据SHA（均为已冻结配置/已终态旧诊断，不锁运行中T3文件）：

- `artifacts/research/process/20261004-ced-development/astra-rounds/round374-diagnostic-runtime-prerequisites-20261101/plan.json`：21499 B；SHA256 `397285e1fbbb2b61ff616e80d821c5322adf96a4ecd76c7db49b7cd818adcf9a`。
- `artifacts/research/process/20261004-ced-development/astra-rounds/round374-diagnostic-runtime-prerequisites-20261101/scope-clarification.md`：3356 B；SHA256 `a60a1867ccf7c542dd9215d2951b5cdb2764d1d2c2dcbbbdcdf4af4f377c3bc0`。
- `artifacts/research/process/20261004-ced-development/astra-rounds/round374-diagnostic-runtime-prerequisites-20261101/continuation/planned-stages.json`：530326 B；SHA256 `bf1bd75644a956c973fff1380399fc095c10e36c62e1fa887b3b2b5999b12ef0`。
- `artifacts/research/process/20261004-ced-development/astra-rounds/round374-diagnostic-runtime-prerequisites-20261101/continuation/run_remaining.py`：6077 B；SHA256 `6b622c7ab368d8be0aae94a4ce301e0d530c59e92fa60175fc24eca6d44ab448`。
- `artifacts/research/process/20261004-ced-development/astra-rounds/round374-diagnostic-runtime-prerequisites-20261101/continuation/sequence.py`：1259 B；SHA256 `af8e0367b5147571c0647ababdd160124a286cd1badb2b797afd0825e38a0379`。
- `artifacts/research/process/20261004-ced-development/astra-rounds/round374-diagnostic-runtime-prerequisites-20261101/continuation/implementation-pins.json`：680 B；SHA256 `0a560be49a90db0c1d0dbbaee4e1335d6e5aeaa47c0ae95aa22daaf59aff2149`。
- `artifacts/research/process/20261004-ced-development/astra-rounds/round374-diagnostic-runtime-prerequisites-20261101/continuation/sequence-pins.json`：359 B；SHA256 `f8d77af84d04db56fce40590529503a6bba04f4270505ec3b113887254f8abb0`。
- `artifacts/research/process/20261004-ced-development/astra-rounds/round373-full-workflow-rerun-20261101/implementation/pytest_software_01/result.json`：581 B；SHA256 `87590ee83560c51175be5c123dbe4e07b6a6bf441e236323c9a69cd1f7ea1f07`。
- `artifacts/research/process/20261004-ced-development/astra-rounds/round373-full-workflow-rerun-20261101/implementation/pytest_software_01/pytest-events.jsonl`：159279 B；SHA256 `4a618a361a896f6a4e1f8329aacd5596a7cda1dec058602e72beb879ffbdcfb1`。
- `artifacts/research/process/20261004-ced-development/astra-rounds/round373-full-workflow-rerun-20261101/implementation/pytest_software_02/result.json`：581 B；SHA256 `0be8fb4fac89e63b9a1d040b9b813d79afcbc60e5f2c4b4d5d9d78e704c97604`。
- `artifacts/research/process/20261004-ced-development/astra-rounds/round373-full-workflow-rerun-20261101/implementation/pytest_software_02/pytest-events.jsonl`：125476 B；SHA256 `4e69ad7e879f2c6604d513151d9727bd33826ff8c2967c5812aefccef02b72ca`。
