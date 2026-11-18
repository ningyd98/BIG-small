# Phase 12 软件生命周期补充

按实际 Astra 总计划新增默认关闭的 `Phase11RuntimeAdapter(lifecycle_only=True)` 和独立入口 `scripts/run_phase12_runtime_lifecycle.py`。仅显式软件探测选择 `LEGACY_PIPELINE`，默认适配器、主 Phase 12 runner/validator、Mock/RGB-D 拒绝及历史 18 条 F20 均保持。

首次接口 RED：4 failed / 1 passed，均因新参数尚未实现；实现后 5 passed。补充 CLI 的 4 项 RED 为入口不存在；实现后 9 passed。最终加入内部 hash、恢复转换、终态原件、竞争身份、clean provenance 不抵缺口和重复运行新数据库回归，共 17 passed。原日志和 JUnit 位于本地 `experiments/results/phase9/real-harness-20261118/`。

单条初测完成后，按旧 F20 的 18 个 run ID、场景、控制模式、seed 和 repetition 新建独立软件探测，共 18/18 完成，144.576 秒，0 付费模型调用。每条均有真实 SQLite job/lease/attempt、恢复至少两次 attempt 和原转换链、两个不同竞争 worker、恰好一次执行器调用及终态文件 hash。使用既有验证函数逐条核验，旧 raw_runs.jsonl 的 SHA256 与启动前相同。

[补充结果](supplement-summary.json)关联旧 run ID 和新 run ID；[复核与来源指纹](verification.json)记录测试及实现。完整数据库与原件留在本地 `experiments/results/phase9/real-harness-20261118/phase12/`。这是软件生命周期证据；默认 RGB-D F20 的物理执行缺口、完整 full profile、正式研究及真机均未因此通过。

终审补充：来源门先后以原始字节 RED 覆盖重复ID/非阻塞/已执行、profile缺失或非validation、未登记场景、否定或未知阶段错误码、重复JSON键和非有限JSON值。最终纯来源/身份/计数检查24 passed；原18条实际validation行以新门只读重验，ID顺序和原字节SHA一致，未新增实际lifecycle运行。源码身份固定到脚本ROOT，并记录实际导入的adapter与registry字节；从源码树外调用结果不变。原四次RED和中间GREEN均保留。见[最终严格来源复核](strict-source-final-verification.json)及[独立闭合审查](../software-review-closure-addendum.md)。
