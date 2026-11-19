# worker 异常字段的静态类型复验

按 GPT-6.2 Astra 窄修订计划核对 11 项输入。CPython 的 `BaseException` 字典保有实际描述符。实现以固定字段名取基类描述符并标明返回类型，读取真实 `args` 和 traceback，绕过子类访问器。负控同时覆盖覆写 `__str__`、`args` 和 `__traceback__` 的异常。 [Astra 计划](plan.md)

同参 mypy 对照移除本轮新增的三项诊断。`--follow-imports=silent` 基点和修后各有 1 项既有 `no-any-return`，仅行号移动。正常导入共 31 个报告文件，修前 806 项，修后与同环境基点各 803 项。旧报告留在本机原件，逐项差异见机器回执。定向 Ruff 和 `git diff --check` 通过。 [类型差异](mypy-comparison.json)

EGL 定向组 34/35 通过，含增强的异常负控。原伺服正控在第 5 步实际触发原 100 ms 样本及 IK 截止，随后按独立 Astra 计划一次独占复验同节点，通过并保存物理终态。保留两次退出与原件。 [首轮失败](egl-attempt1-evidence.json) · [独占复验](../round-p0-worker-types-exclusive-deadline-20261119/step-report.md)
