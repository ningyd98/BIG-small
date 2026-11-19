# v9 诊断包装调用真实协议读取入口

## 原始证据

- 冻结包装第 83 行向旧 _collection_policy 泛用入口传 v9，原启动在创建物理后端前以 ValueError: registered schema/family pair required 退出 1。冻结产品对 v9 的 read_protocol(current_sources=True) 调用 _registered_teacher_protocol→_registered_collection_protocol_v2，另校验 v9 配置 SHA。

## 实施范围

- 仅修冻结诊断的辅助包装，在新输出目录从同次受控 prepare 的协议目录调用真实 read_protocol(..., current_sources=True)，使用其经核验的 source_hashes 传给 PRE v2。另验证 v9 配置的生产固定 SHA、整包冻结清单和实际加载模块；不得放松旧版本或手造协议。

## 运行前置

- 保留旧包装、stderr、空输出、已准备的协议/资格、旧冻结 checkout。验证错误版本/配置摘要或来源漂移在启动前拒绝。教师独占窗口核对来源、负载与设备，沿原计划恢复同一 zero-model 的 16 帧 PRE/当前真实 proprio 预览与 8s 诊断；此前未消费实际物理或教师 claim。

## 验收

- 验协议、来源 map 与配置分开记录；实际时钟、帧、成本与退出由新回执独立重建。禁止把 16 帧或 8s 片段计为完整八动作；首组按原授权及父轮条件收集。若另一真实失败保全终态再评估。
