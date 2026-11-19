# 1803 原 worker 终止字段复验

两次旧归档读回均退出 0。旧身份派生字段读取外层结果里不存在的 `error_type`，其 null 容易被理解为原始记录没有终止原因。旧脚本、两次输出的清单、旧报告及首次失败原样保留。 [旧回执 SHA](../round-p0-archived-three-20261119/successful-readbacks.json) · [旧脚本](read_archived.pre-worker-reason.py.txt)

新脚本从归档清单验证 `worker/result.json`、`component/episode.json` 和外层 `result.json`，逐项要求 `terminal_reason` 键实际存在，并核对三者一致。1803 三份原件均为 `ValueError`，1802 三份均为原有 null。1803 原在线消息、栈均未保存，冻结构造器的护栏复现已另列。 [新身份结果](../round-p0-archived-three-20261119/derived-v2/1803-identity-v2.json)

测试在旧脚本上实际退出 1，在新脚本上 8/8 通过，覆盖三份原件各自缺字段或与另外两份冲突。Ruff 退出 0。在相同冻结输入上，两个新的独立全流程读回退出 0，9 个确定性输出一致。与旧版相比，7 个无关输出和全部叠图逐字节一致，身份几何逐字段一致。来源核验新增两个 worker 结果及各自 SHA，合计核对 103 个实际归档原件。新增模型、云、试次和硬件派发为 0。 [复验 SHA 与逐来源读回](v2-readbacks.json) · [P0 最新报告](../round-p0-archived-three-20261119/step-report-v2.md)
