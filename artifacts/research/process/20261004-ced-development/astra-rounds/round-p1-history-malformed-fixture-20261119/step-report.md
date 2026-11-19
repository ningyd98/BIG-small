# 历史排重中的畸形协议负控

首次预登记扫描因旧 pytest 目录中的一个单字节协议退出 1。原始坏件 SHA256 为 `021fb596…`，旧启动、节点、终态和测试源码共同绑定了该确切路径。原套件登记了故意写入 `{` 以期被拒绝的节点。旧脚本和实际失败证据保留，未占用启动名额。 [首次定位](../round-p1-development-readiness-20261119/development/first-history-invalid-inputs.json) · [首次退出](../round-p1-development-readiness-20261119/development/first-history-freeze-failure.log) · [原脚本](development_plan.first-failure.py.txt)

研究读回仅对这一已知原路径、文件类型、长度、字节和 SHA 使用负控语义，仍写入完整排重向量，贡献 0 个 seed 与 0 个目标位置。异路径同内容、已知路径改内容、新的坏 JSON/JSONL 均拒绝。下一次读回通过该负控后发现独立的教师索引格式问题。该问题单独修订后，实际 9 根和 1,732 文件读回成功，预登记通过。 [故障后的独立修订](../round-p1-history-dataset-formats-20261119/step-report.md) · [全量排重摘要与登记](../round-p1-development-readiness-20261119/development/preallocation/allocation.json)
