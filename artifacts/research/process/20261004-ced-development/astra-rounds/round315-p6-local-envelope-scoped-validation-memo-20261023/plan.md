# R315：局部历史解码的单次调用内验证复用

实际模型：**gpt-6-astra**。只读规划；产品和测试尚未修改或执行。HEAD：`942d82343e97e53dbbd8b96309a393ca6836a496`（ROOT 提供）。精确输入 SHA、命令与前置见同目录 JSON。

## 证据与判断

R313 parent 0、child −15，按原 180s 边界终止；ROOT 已接受诊断证据并将双方额度结算 SPENT。89 样本跨 177.902s，进程 CPU 增 178.400s，采样线程仅 0.04086s。67 个最近测试帧在 adopt_plan，11 个在其后的 bootstrap.to_payload 断言；尚未观察到 34 项 writer inventory。缺失 JUnit／结束侧文件继续标未知。

源码确证重复链：`from_payload → _semantic → _history / _staged_original_body → semantic_projection → from_payload`，之后 `_validate_nested_local` 又验证已处理的子节点。修复假设是消除同一顶层调用中相同完整内容的重复验证。采样未量化全部调用，不能排除 profile 放大，也不能将旧 −11 归因于此。

## 最小产品修改

只改 `src/cloud_edge_robot_arm/vision/local_temporal.py` 的 `LocalEnvelope.from_payload` 及私有支持：

- 顶层同步解码建立 context-local memo，递归共享，正常或异常均 finally 清除；跨顶层、线程／上下文不复用。
- 先按原 `_object` 严格复制，再以 **类身份＋完整 canonical JSON** 为键，包含诊断、原始时间和全部证据。仅所有原校验成功后缓存，不缓存异常或进行中项。
- 命中仍创建对应类的新实例，保存不可变 `_json`；返回对象和可变 payload 不共享。字节、digest、预算、权限语义不变。
- 最多 128 项／8 MiB canonical 文本内容；超过即走原完整验证、不插入。保留 canonical 化本身的成本，不承诺消除所有开销。
- 原语义、历史、嵌套验证及投影规则全部保留；不改 profile、TTL、等待、权限、断言或其他产品模块。

## 执行顺序与有限额度

| 次序 | key | 次数 | child / outer | 出口 |
|---|---|---:|---|---|
| 1 | R315.observer_red | 1 | 120s / 240s | 原源码只在重复成功验证次数断言 RED |
| 2 | R315.observer_green | 1 | 120s / 240s | 新单节点微回归全部通过 |
| 3 | R315.writer_memory | 1 | 原 600s / 900s | 原 writer memory 完整行为和资源证据通过 |
| 4 | R311.writer_sqlite | 原 HELD 1 次 | 原 600s / 900s | 前项独立接受后，源世代映射再执行原命令 |

全部 retry 0，先消费后 dispatch。不重跑旧六项或两项 budget，不重置 SPENT。微回归沿已验证 unit runner 结构，memory 沿 R311 runner，只做精确身份／命令／源世代映射；不新增通用框架或诊断轮。

## 微回归与实际验收

新增 `tests/test_local_temporal_decode_memo.py::test_scoped_decode_memo_contract`。使用已钉住的 R196 完整 promotion golden，真实解码与始终委托原校验的计数 spy。RED 必须是同一顶层相同完整内容重复成功验证的确定性断言，不是缺函数、超时或输入损坏。

GREEN 同时检查完整序列化／digest／独立投影等价；实例与 payload 隔离；cls 分键；跨顶层重新验证；合法后变更／无效嵌套仍拒绝；正常／异常清理与上下文隔离；容量耗尽回退。保留预算、原始时间、权限注册表不变。详细输入和拒绝场景在 plan.json。

ROOT 逐次完整审阅与独立接受。memory 必须实际完成原两个 bootstrap 拒绝、34 个 inventory、合法正向写入和预算断言以及完整资源清理。通过后才允许归档旧 gate／acceptance／roles 全字节并 CAS 映射 R311 SQLite 的 local_temporal SHA，其他旧条目与额度保持。

## 边界

旧通过记录保留其原世代意义；共享 codec 已改，不能声称旧六项／budget 已测新源码。新微回归和后置 fresh T2 review 负责影响分析，若需更多行为验证须另行有限规划。任何意外失败或范围扩大停止受影响工作并回 Astra；不调等待或校验门槛。两 writer 通过仍不自动完成全 T2、T3 或研究验收。ROOT 后续按原授权显式路径交付，保留所有原始失败和数据库边界。
