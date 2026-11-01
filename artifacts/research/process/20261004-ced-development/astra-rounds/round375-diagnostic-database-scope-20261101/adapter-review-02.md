# R375 adapter review 02

实际复核者：`gpt-6-astra`（`/root/astra_r371_utc_plan`）。结论：**READY，但必须满足原运行前置后才可启动**。parent 报告 R374 仍运行 software06，因此现在不能启动 R375。

已只读核验两个修正版、实际启动规格和原计划。两个 Python 文件 AST 可解析；19 项输入及 1050 个源文件 SHA 均匹配，未发现漂移。未执行 adapter、测试、产品导入或信号操作。

- `run_comparison.py`：`bf74fdf9135aa50b8ee62a699c8b333e9f485c47b48afef33c7eda5f34d0e6cc`。
- `supervise_comparison.py`：`3644985f62dbbd5471e7a18ac07484b7d736b8ad6b1d8b2fddd72477586d00a5`。

## 前次三项复核结果

1. **已解决。** `Popen` 成功后立即进入 `try/finally`，身份采集、落盘和等待均被清理保护；supervisor 同样保护自己的子进程。
2. **已解决。** 证据读取/解析异常记录到错误列表并使验收失败；缺失结果由 supervisor 写基础设施错误回执兜底。只有已回收且无活成员时才清点静止 DB/WAL/SHM，否则明确跳过。旧日志不修复、不覆盖。
3. **已解决。** supervisor 实际在 75 秒停止 launcher，并将最终 15 秒留给所属 launcher 与独立 pytest 进程组的身份核对、TERM/KILL、回收及回执，使用同一 90 秒截止。工具 yield 不承担超时控制。静态复核不能替代运行后的实际清理证据。

## 唯一实际启动入口

```sh
.venv/bin/python -u artifacts/research/process/20261004-ced-development/astra-rounds/round375-diagnostic-database-scope-20261101/supervise_comparison.py --run
```

工作目录：`/home/ningyd/文档/ChatGPT/BIGsmall`。`bounded-launch-spec.json` 中 argv 是 supervisor 的内部 launcher 命令，顶层执行须用上面的 supervisor，不直接调用 adapter 绕过外层约束。

原完整 continuation 终态、父退出、所有子清理、无其他产品测试、运行时重新核验 pins、全新输出目录、原报告截止前至少剩余 90 秒等前置保持有效。不得因本次 READY 提前启动或重置预算。

验收须同时检查 outer 与 inner：outer 无超时/错误/活进程且 launcher 已回收、退出 0；inner 存在且 `comparison_acceptance=true`。外层退出 0、NOT_RUN 或本次静态 READY 都不代表测试通过。仍是原 7 节点同序、一次 60 秒、无重试，仅移除 SIMULATION_RUNTIME_DB 语义覆盖并迁移输出路径。旧失败保留，比较结果分别追加。

本记录不修改产品、测试、旧计划、冻结输入或 R374 清单；没有扩大 R375 范围。
