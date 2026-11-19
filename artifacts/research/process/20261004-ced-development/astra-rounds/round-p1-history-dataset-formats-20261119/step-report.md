# 普通 RGB-D 与教师历史索引复验

第二次实际 freeze 通过已知畸形夹具后，在读取不存在的教师 samples.jsonl 时退出 1。无批次注册、BEGIN、模型调用或仿真。保留该次日志、源码和四份真实教师 manifest 的原 SHA。 [失败回执](../round-p1-development-readiness-20261119/development/second-history-freeze-failure.log) · [四源原件核对](../round-p1-development-readiness-20261119/development/teacher-history-format-readback.json) · [该次源码](development_plan.pre-dataset-formats.py.txt)

按七个具名目录读取实际原件。三个普通 RGB-D JSONL 各有 100、100、1,000 条，逐行校验 ID、schema、来源、scene/group、seed 和世界目标位置。四个教师 manifest 的 42、20、20、20 个 assignment 均保留，四组独立数值 seed 分别为 41、19、19、19。较早的教师版本没有 protocol 字段，其配置按当时的原哈希格式解析。其余版本同时校验协议、配置和逐场景内容哈希。目标坐标取明示的世界位置，已知重复不减原组分母。

22 个定向测试通过，包含畸形索引、来源/格式、错 seed 或 NaN、重复教师实例及确认冲突的负控。最终同版预登记通过历史 9 根、1,732 个索引、102 条历史教师分配、9 个当前教师保留 seed 和六个下游池的 3,260 个实际组核验。历史向量摘要 `57866076…`。正式预登记含 20 个独立位姿及两个预声明的 1802 实例，记录前已执行 0，两个 Wilson 区间均无样本。 [预登记与排重摘要](../round-p1-development-readiness-20261119/development/preallocation/allocation.json) · [运行前计数](../round-p1-development-readiness-20261119/development/preallocation/results-before-any-run.json)
