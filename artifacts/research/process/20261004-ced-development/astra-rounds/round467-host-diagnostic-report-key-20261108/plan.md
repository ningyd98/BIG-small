# R467：已保存主机诊断报告的 JSON key 修复

实际规划模型 `gpt-6-astra`，仅计划，未实施。ROOT 的 stdlib 后处理返回1，原始错误：

```text
Traceback (most recent call last):
  File "<stdin>", line 5, in <module>
StopIteration
```

原表达式的成员判断在已解析字典中查找包含双引号的字面字符串 `\"result\"`，实际 key 是 `result`，因此过滤全部记录并耗尽 `next()`。主机诊断已成功，不属于此次故障。输入路径、字节数和 SHA256 全部列于 `plan.json.inputs`，不复制或改写原件。

ROOT 使用 `.venv/bin/python`，只读取已保存 `exec-result.json["output"]`；不创建 runner。精确替换为一次解析并验证唯一 result：

```python
rows = [json.loads(line) for line in out.splitlines() if line.strip()]
assert all(isinstance(row, dict) for row in rows)
results = [row["result"] for row in rows if "result" in row]
assert len(results) == 1, "expected exactly one saved diagnostic result"
result = results[0]
```

限定产物为 R466 `implementation/host-gpu-diagnostic/decoded/` 三命令 stdout/stderr 原字节、R466 `implementation/step-report.md/json` 及 R467 `implementation/` 报告/校验收据。新输出不得覆盖已有文件；出现冲突先停。一次后处理、一次校验，总墙钟≤60秒；stdlib only，不 import 产品、不跑测试、不执行 subprocess 或任何诊断。

实施前核对全部输入 SHA。校验外层 rc0、output UTF-8 字节等于保存 jsonl、仅一个 result、三 command 与 result.commands 逐项相等、标签与冻结 argv 一致且各 rc0。用 `base64.b64decode(..., validate=True)` 解码六项，要求与原 text UTF-8 相等，写入后读回比对长度与 SHA。GPU原值 total16376/used513/free15431 MiB 原样保留，不强求 used+free=total、不修改其记账值。compute 空且 count0/ownership_complete=true；Qwen loaded/inactive/dead、MainPID/ControlPID0。报告写完重新核对输入未变及产物一致。

报告资源结论为 `RESOURCE_CLEAR_AT_SNAPSHOT`，时间 `2026-11-08T07:00:01.082347+00:00`；与原受限 rc9 并列。它只是该时点观察，不是未来独占预约，也不证明具体 sandbox 机制。保留原 `reporting-failure.json`，不得将失败改 PASS。R467修复完成和R466原诊断完成分开记录。

本轮新增 GPU诊断/API/physics/render/model startup/service mutation/软件测试全部0；full NOT_RUN，native UNKNOWN，formal NOT_ACCEPTED。任何新失败或证据不符先停，交实际 Astra 下一轮。后续 P1/P2 新来源、精确 runner 和额度另行冻结，不增加用户确认循环。
