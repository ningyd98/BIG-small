# R318：Memory 原锁名称澄清

实际模型：`gpt-6-astra`。只读核对回执 `c022f9`（exit 0）；未实施或运行。

## 问题和证据

R317 多处把 Memory 锁称为 RLock，这是规划名称错误。冻结 `memory.py:113` 实际为 `self._lock = threading.Lock()`。`protocol.py` 外层 `with lock` 退出后才调用 original；后端再获取同一个真实非可重入 Lock。没有该问题的运行失败。

## 唯一澄清

R317 的所有 “Memory RLock” 均按 **仓库原真实 threading.Lock()** 执行；保留 R317 冻结原件，不覆盖。不得改锁类型／构造／获取边界，不得在测试替换为 RLock，也不得把外层锁持有跨越 original 调用。

测试观察可委托同一个真实 Lock 的 acquire／release，但不能绕过阻塞、增加重入或改变参数；不得依赖 RLock 专用 `_is_owned`。holder 持锁时，已授权 fixture 准备和快照直接读取已持锁的原存储，不递归调用会再次获取锁的公共方法。claimant 仍在原限定线程中等待真实锁释放。

## 接续与边界

ROOT 按本计划和 R317 核对适用性后继续原准备／source gate。产品仍仅原三文件候选级领取修复；SQLite、快照、权限、排序和时序要求不变。

新增运行／测试／审阅额度均为 **0**。沿用 R317 四个 once keys 和最多 16 批 fresh 续读；旧 12 批耗尽状态不变。不新增 probe，不重置额度。无关独立审阅可继续。若需要更广锁实现变化，停止受影响工作并回 Astra。

精确输入 SHA256 见 `plan.json`；本轮不宣称行为通过或 T2 验收。
