# R144：Astra 可选 schema 文本读取路径恢复

实际规划模型：gpt-6-astra；规划者 /root/astra_status_plan；2026-10-12。状态：冻结待 ROOT 激活。

R143 规划中额外核验 event repository 的关闭字段时，错误猜测平铺文件 `src/cloud_edge_robot_arm/repositories/event_autonomy.py`。前三个文件的文字返回成功，第四个 read_text 触发 FileNotFoundError；没有产品命令、源码写入或预算消费。此原因独立于 R143 测试映射和 R142 ROOT reader。原始提交代码及 shell 字符串完整写入 plan.json。

捕获限制：原 wrapper 仅打印 nested output；当前压缩上下文未保留 nested exit/chunk，也未保留完整 combined 内容。因此 exit/chunk 记 null，仅保留可得原命令与非 raw 观察摘要；不得编造 traceback、stdout/stderr 或重新执行重建旧输出。

ROOT 激活前不恢复读取。激活后仅允许核下列 pin，再用现有 protected index 已给出的完整绝对 sqlite.py 路径，有限读取连接初始化与 close 相邻定义；使用长度有界切片和 .venv stdlib。不得重试旧命令、猜其它目录、运行 AST/import/compile/collect/static/test/probe/Git/actual。发现新问题暂停相关读取另规划。

输入：
- /home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round141-p6-positive-publication-control-20261012/plan.json — 2bb2e3e28c15e10f0af1d05b9f7815ac0e87b9f76c8536b8b755a77c58b9b6c5，59385 B。
- /home/ningyd/文档/ChatGPT/BIGsmall/src/cloud_edge_robot_arm/repositories/event_autonomy/sqlite.py — 92bc23b61ee7867547a8f4b6304d813f0caec5d3d338371b7bc1dcd1975eae2d，140339 B。

允许本轮保存 original-observation.json、input-check.json、root-activation.json、read-observation.json、step-report.json。所有旧原件不动。将真实文字结论返回 R143；本轮不授予产品或测试修改，不改变 R141 四项预算和原四终门，不宣称软件、真实运行或正式验收。ROOT 需先复核本计划，随后才激活上述唯一读取。

