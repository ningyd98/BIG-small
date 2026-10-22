# R319：Session 构造完成的观察器记账

实际规划模型：**gpt-6-astra**。仅规划；不改产品 authority，不执行验证。**实施最早在 R317 四个 runtime keys 全部结算后。**

## 原证据与根因

Fresh finding `T2-FR-02` SHA：`e9f766dfee402196123d6d1149377a095109ca7374a8a030686586209b2f72d3`。原七份资源中 15 个 lease_session 均被 `_sealed` 判据标成 false／IncompleteConstructor；真实 OperationalLeaseSession 构造器不设置该属性。

Astra 已只读复核七份原 raw SHA 和全部 15 个 session→worker→唯一正常 poll 链接。分配 5708、原 recorded_initialized 5693、cleanup 5708 均保留。问题是观察器分类错误，不是 15 次实际构造异常或产品 lease 故障。历史没有显式正常构造器返回 trace。

## 限定修复

只改 `_b_t2_observe` 及针对性微回归：

- 用现有透明 `init_wrapper` 包装真实 `OperationalLeaseSession.__init__`，原样调用／返回／重抛；只有正常 else 才 initialized=true，except 记录实际异常。可新增小型 constructor_outcome 字段。
- `session_code` **必须在 patch 前捕获原构造器代码**。保留原 call／return 采样和 owner 关联，删除 `_sealed` 分类及其合成错误。profile 的 return/None 本身不证明正常返回。
- 使用原 patch／methods 恢复机制，不改产品源码、权限判据、TTL、采样选择、事件转发或旧七节点正文。
- 旧 partial 模拟只有人工 profile 事件：保持未确认初始化，error=None／outcome 未观察；不得把它伪造成真实异常。保留原 unrelated-event 主断言及全部选择性观察／转发／恢复检查，另做明确模拟标签的 wrapper 异常委托检查。

## 新有限验证

| key | 次数 | child / outer | 内容 |
|---|---:|---|---|
| session_init_red | 1 | 120s / 240s | 新节点一次真实软件 poll；旧记账误判为唯一合法 RED |
| session_init_green | 1 | 120s / 240s | 同节点，真实正常构造、记账与完整清理 PASS |
| observer_selective_green | 1 | 120s / 240s | 旧 selective lifecycle micro 的限定适配，零真实 poll |

retry 全为 0。这是三个新预算，不复用旧 SPENT，不重跑七行为节点。

新真实节点使用原 `_b_t2_attempt`／`_b_t2_observe`／`_b_t2_exercise`，memory 后端、仅一个原软件 poll；回调只读实际 session/record，不 adopt、规划、注入故障或跑 writer inventory。先让 poll 和清理完成，再检健康 session 误分类，原 RED 错误完整保留。GREEN 必须确认真实 constructor 返回、无初始化错误、正常 poll、原线程／连接／clock／session 清理及 hook 恢复。

真实 poll 不能被 unit_only 丢弃资源。沿用 compact runner 和严格索引／DB归档；如原 parser 仅缺新节点的 scenario cap，只允许局部派生 helper 加该节点 cap=1，其他源码保持，不改冻结 helper 或真实 nodeid。RED 完成标志 false 与捕获完整性分开，不能称行为 PASS。

## 历史解释 overlay

另存每个原 resource_id 的 raw false/error、源 SHA、worker／poll 链接和清理事实。原 recorded_initialized=5693 永远保留。ROOT／独立 reviewer 核对旧 worker 在真实构造返回后才赋值、且关联唯一正常 poll 的完整源世代路径后，才可单列 **推断成功 session=15、解释性 initialized=5708**；不得冒充原记录的正常 return trace。不足者仍 unknown，不强凑总数。

allocation／cleanup 的独立分母仍可按原证据审阅，不补造丢失字节，不改旧 resource/result/coverage/report，不把该分类错误当资源泄漏或旧 SIGSEGV 原因。

## 时序和复核

R317 活跃 gate 期间只保存本轮计划／元数据，不新增 test 或改 fixture。四 keys 结算后，ROOT 用单独 applicability 记录其实际新源世代；Sol 单写、ROOT 独立审阅／reserve／结算。

另给 fresh reviewer **R319 独立 4 次**限定读取，每次最多 600 源行／39,000 UTF-8 字节，只审新 diff／结果／十五行 overlay 与构造赋值路径。原 12 次和 R317 16 次不重置；R317 剩余额度至少保留 3 次给 outbox，不能隐式借用。任何新失败或扩大范围回 Astra。

本轮不自动批准 T2；仍须 outbox 修复及完整 fresh Spec／Quality 实际闭合。精确输入／命令／额度见 JSON。
