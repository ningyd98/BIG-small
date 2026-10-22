# R317：混合 local／legacy outbox 的候选级领取

实际规划模型：**gpt-6-astra**。只读规划，未修改产品／测试或执行验证。精确输入 SHA 与命令见同目录 JSON。

## 问题与原证据

独立报告 `T2-FR-01` 为静态 P1：`protocol._local_target` 将任何 local outbox 行的存在用于拒绝每次无参 public claim。外层 dispatcher 和后端内层 guard 都发生在 legacy 候选选择前，导致无关任务的 `_outbox`／`event_outbox` 消息无法领取，且 local 历史行仍可持续阻断。

报告 SHA：`0ea5533ba5fca934571855294650cfd8349e54233eb1fd7328180a3a085ac7ad`。当前 **Spec Changes required / Quality Incomplete**；原 12 次读取含 3 次预输出拒绝全部耗尽。尚无该缺陷动态 RED；原七个行为 PASS 不覆盖混合共存。

## 精确修复范围

仅改 `protocol.py` 的 claim 分派／目标判断，以及 `memory.py`、`sqlite.py` 的 `claim_outbox_message`：

1. public claim 的外层检查延后到后端实际候选；private scope 分支完全不变。
2. 在原 Memory RLock／SQLite write lock＋BEGIN 内，按原顺序和时间条件选择同一 legacy 候选，传候选给原 local guard，再修改状态。当前候选 task 已有 local binding 必须拒绝。
3. 没有 eligible legacy 候选时仍执行原无参 guard：存在 local outbox 则原错误且不变；否则 None。全局 local 存在回退只用于无候选参数情形。

不复制一套预选逻辑，不移出锁，不改变时间计算、排序、CAS、私有权限、预算或 TTL，不读取或领取 local 消息。

## 必要验证与额度

新节点：`tests/test_mixed_outbox_claim.py::test_mixed_local_legacy_claim[memory/sqlite]`。

| key | 次数 | child / outer | 预期 |
|---|---:|---|---|
| observer_red_memory | 1 | 120s / 240s | mixed legacy 领取断言 RED，原 scope ValueError 完整保存 |
| observer_red_sqlite | 1 | 120s / 240s | 同上 |
| observer_green_memory | 1 | 120s / 240s | 完整新节点 PASS |
| observer_green_sqlite | 1 | 120s / 240s | 完整新节点 PASS |

retry 全为 0，ROOT 逐项 reserve／独立接受／结算。先两个真实 RED，再精确修复、ROOT diff 审阅和两个 GREEN。旧额度全部不重置，原七节点不重跑。

使用真实仓库与 PendingMessage，local 持久化测试状态明确不构成 live authority。覆盖 pure legacy、local-only 拒绝、mixed legacy 领取、local PENDING／SENDING／SENT 历史行、重复 claim、原 RETRY_WAIT 时序、local-key mark 拒绝。每次 claimant 前后保留 **全部 local tasks 和 publication receipts 的原始字符串／字节快照**；只允许期望的 legacy 改变。

另必须验证实际等待后 binding 重查：Memory 真 RLock；SQLite 独立连接持有真 BEGIN，等待期间设置候选任务 binding 后释放／提交，claim 必须拒绝。记录准备变化与 claimant 变化的不同快照，不能把 fixture 写入算作被拒操作。每节点最多一 claimant 线程、SQLite 两同时连接，事件／join 每次限 5s，finally 全清理；不得伪造锁、BEGIN 或权限。

## 独立续读：新 16 批上限

允许实际原 fresh seat 接续；若原 seat 不可恢复，记录真正新建独立 seat，不冒用原身份。单独 `R317.fresh_T2_continuation` 额度，最多 **16 次**，每次最多 600 源行／39,000 UTF-8 展示字节；所有失败亦计数，旧 12 次不动。不得额外运行产品／测试／SQL。

范围只补报告缺口：新 diff／测试／真实结果；原 fixture 指定约 1,300 行和 lifecycle test；完整原 private lease／view／CPU provenance／实际事务路径；七次 native 回执内嵌 payload；真实 seam／resource 样本与分母复算；有限源世代对应。精确路径和行段见 JSON。不重读全部历史，不倾倒巨型原始 case。保持每次原 invocation／return 和覆盖范围；新报告单列 Spec／Quality，未读完仍 Incomplete。

## 七节点复用与出口

保留每个原 PASS 的真实源码世代。新双后端回归若通过，加上候选级锁内判断审阅，可覆盖本次 public outbox 改动，尤其旧 writer “没有 legacy 候选”的拒绝等价；其他 private 路径不变。没有仅因 memo／accessor／本次有限修复而整批重跑七项的理由，但 **只有新 GREEN 和全部剩余 fresh Quality 审阅实际闭合后**，才可认定这些分世代证据足以支持有限 T2 软件出口，不能合成“当前 GREEN7”。

任何意外失败／新缺陷／范围扩大均回 Astra；不得为通过而改门槛。旧 SIGSEGV 原因仍未知，本轮不推进 T3／P6C／native／正式研究验收。ROOT 按已有授权保留证据、显式路径交付及三 SHA 核对。
