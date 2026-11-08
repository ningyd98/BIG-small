# R450 资源释放执行报告（2026-11-08）

用户明确要求“GPU 无关进程都关闭”。本次确认唯一 GPU 计算进程是旧 Qwen 服务的 strata（PID2296，父PID1592，UID1000，服务cgroup一致），与当前官方 GPT API 测试无关。沿用 R450 已有资源诊断和停止方式，执行一次 `systemctl --user stop --no-block qwen38-flash-strata.service`。

服务现为 inactive/dead、MainPID0，18201监听已关闭，计算进程列表为空；随后复核仍保持停止。停止完成约9.1秒，没有另行kill、disable、mask或配置修改。当前用户要求关闭并保持停止，故没有执行旧临时采集方案的自动恢复；原 authorization-pending.json 保留为历史，不表示本次仍待授权。

显存占用由 15,646 MiB 降至复核时 530 MiB，可用 15,413 MiB（约 15.1 GiB）。桌面和图形应用保留。这里只证明本次观测时计算任务为空，不保证未来持续独占。

阶段进展：Qwen常驻显存占用这个资源障碍已解除。R460真实GPT旧图回放4/4通过结论保持；当前v2新采集、完整物理流程与独立校准尚未运行。后续先处理Sol证据reader兼容和新source generation，再按研究主线执行。软件源码、GPU模型推理、renderer、physics与dispatch新增次数均为0，正式研究仍NOT_ACCEPTED。

原始命令与状态转移见 commands.jsonl；停止结果见 result.json；后续独立状态快照见 verification.json。没有读取环境、凭据、请求正文或服务日志内容。
