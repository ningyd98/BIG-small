# worker 原伺服正控的独占复验

前一定向组 34/35 通过。唯一失败在 `step-05 MOVE_TO_REGION`。原件记录 `CONTROLLER_FAILURE:VISUAL_SERVO_REJECTED`，样本及 IK 耗时 0.113520 s，触发保留的 0.100 s 门限。该次并行 CPU 作业与超限因果仍待定。 [首次原件摘要](../round-p0-worker-exception-types-20261119/egl-attempt1-evidence.json)

与教师协调后持原共享 GPU 锁，源与测试 SHA 一致。使用同一 Python、MuJoCo 和 EGL 配置，停止可控重 I/O 与其他 pytest 后，在新目录仅运行 Astra 批准的原测试节点。旁路采样 9 次，CPU 亲和性为 `0-15`，原始采样记录含负载、进程、GPU 与磁盘活动。保持 100 ms 门限和控制路径。 [计划](plan.md) · [退出与采样回执](exclusive-run-receipt.json)

子进程退出 0，1 项通过，耗时 38.00 s。从 worker 写入的独立 episode 读回 `COMPONENTS_COMPLETED`，执行 9 个动作段、7,707 物理步，最终 `RETREAT`。独立物理结果成功，记录抬升 0.105617 m、持物 3.1875 s、目标区稳定 9.4417 s、安全违规 `false`。该软件夹具使用 1 个云协议替身、4 次 RGB 点位替身，真实供应商调用、本地模型生成和硬件派发均为 0。 [pytest](pytest-egl-exclusive.txt) · [JUnit](junit.xml)

原 episode、commands、物理证据、费用台账、日志、JUnit 和主机采样保存在本机 `cache/local-verification/20261119-worker-docs/exclusive/`，回执记录逐件 SHA256。本次通过限定于该软件夹具和测得的独占运行条件。
