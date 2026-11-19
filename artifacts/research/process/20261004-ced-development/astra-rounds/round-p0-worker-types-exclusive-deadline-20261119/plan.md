# worker 正控同版独占复验

## 原始证据

- 原定向运行 34/35，新增描述符滑动覆盖通过，原伺服正控在 step-05 MOVE_TO_REGION 返回 CONTROLLER_FAILURE:VISUAL_SERVO_REJECTED，实际 sample/IK 0.113520s 超过原 0.100s。存在并行 CPU 作业，根因待定。

## 实施范围

- 仅对原完整 pytest 节点 tests/test_sol_molmo_worker_integration.py::test_real_worker_runs_explicit_component_diagnostic_with_safety_and_physical_evidence[True-False-None-True-None] 进行一次同版复验。使用原 Python、EGL、原参数/源码/夹具及路径绑定，从新 basetemp/JUnit/输出目录运行；仅旁路采集系统状态，不插桩控制环或调门。

## 运行前置

- 与教师约定互斥时段并取得实际同一 EGL 锁；mypy、批量哈希/数据池重建/冻结迁移、并行 MuJoCo 和其他可控重 I/O 均收尾或暂停。在运行前/期间记录系统负载、CPU 核数与主要任务、GPU 进程及磁盘活动，没有可控竞争后开跑；不新发明运行时数值门。冻结被测组件、servo/控制器/worker、测试、解释器及依赖版本哈希，避免并行修改。

## 验收

- 归档原 34/35 与新单节点的 child exit、日志、JUnit、实际 episode、原命令/成本/物理终态及检测到的安全违规；完整正控实际达成后方可支持此次软件发布冻结。独占通过只支持该条件下可达；未通过保留同版终态，交 Astra，不自动反复尝试或放宽 100ms。
