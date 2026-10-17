# R157 — T12 启动路径元数据恢复计划

规划者：实际 gpt-6-astra（/root/astra_status_plan），2026-10-13。状态：冻结后等待 ROOT 适用性复核及激活。

## 问题与证据

ROOT 工具 4ee63f 在已知 R156 目录之外猜测不存在的 R151 目录，rg 实际退出 2。原精确命令、cwd 和 combined 工具输出保存在 /home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round157-t12-resumption-path-discovery-20261013/original-failure.json；独立 stdout/stderr 没有捕获，不能补造。这是路径假设错误，不是产品、测试或 Git 失败。原命令不得重跑。

实际权威链为 R156 plan.inputs → R155 plan.payload.static_manifest → 冻结 selected-manifest 的精确记录。实际 R151 目录为 /home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round151-p6-terminal-ackloss-contract-disposition-20261012，后续输入为 /home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round151-p6-terminal-ackloss-contract-disposition-20261012/next-b9-inputs.json。B 合同在 /home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round113-p6-operational-runtime-closure-20261008/design.md，第 102 行标题为“### B: full local temporal schema and publication, nine nodes”。Astra 已核对十二份元数据权威的实际字节；记录在 /home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round157-t12-resumption-path-discovery-20261013/planning-discovery.json。七个当前源码候选仅为后续字节核对对象，不代表已读产品内容或完成验证。

## 限定恢复

ROOT 先全文读取本计划及 JSON，复核二十个元数据输入、解释器存在性；撰写新 discover-authorities.py 并在执行前全文审阅、保存完整脚本 SHA。仅运行一次：

`/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python /home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round157-t12-resumption-path-discovery-20261013/discover-authorities.py`

在 /home/ningyd/文档/ChatGPT/BIGsmall 工作目录，以标准库 JSON/bytes/hash/text 核对本计划的精确路径、二十个元数据 pin 和七个当前源码字节 pin。按实际类型读取 manifest、R113/B 合同和 R151 输入；不递归重扫 A raw/fixtures，不读取产品文件内容。安全 slice/enumerate，每块最多 600 行，未知 schema 或不一致立即停止。历史 R113 pins 与后来的 A source authority 分开，不能将合法版本演进误报为漂移。

新报告独立保存 implementation/discovery.json，stdout 仅短摘要（少于 1500 字符）；真实 stdout、stderr、exit、invocation 及返回对象分别保留。不对带工具前缀的 output 做 JSON.parse。所有输出必须新建，准确允许路径和全部输入 SHA256 见 plan.json。

## 次数与前置

新元数据 reader 额度 1 次，尚未使用；产品、AST/import/compile/collect、SQL、测试、静态、probe、独审批次、Git、网络及真实运行新增额度全部为 0。所有旧 A 额度及 R155 的 28/28 Git 均已耗用，不能刷新。任何新失败保留原件并停止相关恢复，提交下一实际 Astra 计划。

不得修改旧报告、状态/阶段/状态文档、源码、测试或历史回执。现有 original-failure.json 和 planning-discovery.json 保持原字节。ROOT 只在本轮新增适用性、激活、脚本 gate、执行与步骤报告。

## 验收与后续

唯一通过条件是实际单次 reader exit 0，全部精确 pin 有效，真实路径/schema 可供后续规划；不以元数据核对替代软件验收。已记录的推送 b8ef6e2708e1a9ea28ae4addbe8aeffa066e55d7 是 R155 当时记录，不是本轮远端查询。Stage A 保持 LEASE_FOUNDATION_WITH_LEGACY_UTC_VETO；B9 OPEN、完整 P6/T12 未完成，native/actual/formal 均不提升，CPU 正向控制不是物理证据。

R157 ROOT 实际成功后，R158 才能冻结依赖明确的完整 B 九节点实现计划。公共 SQL 历史/私有确认发布区别只是其中一项；版本化本地时间、grounding、预算及外部 UTC 约束均须保留。下一轮独立核当前公共服务、artifact、batch、Memory/SQLite 生产消费路径并制定新有限验证，绝不重跑耗尽的 A40。当前不授权产品修复或 Git；保留主树脏改及所有历史。

