# V10 仿真教师 Phase 2 软件集成

两个采集合约 builder 根据 protocol_settings 里的 timeout_basis 选择动作窗口。v10 使用 V2 horizon，合约 metadata 标记 PHYSICS_STEPS。每个步骤的 metadata 包含控制器截止步和保持后的终步。采集应用在 PRE 与 POST 分别获取当时的物理步。软件工作流测试记录了 120 与 2,041 两个不同计数。

TaskContract 和 TaskStep 的序列化省略值为 None 的 metadata，保留空字典和值。两个模型的 validation 与 serialization JSON schema 和实施前逐项相等。使用生产原件解码器只读核对了正式 v9 首组与开发复测的两份 original-plan.json。两份载荷的 canonical SHA256 及源文件 SHA256 均一致。[验证摘要](validation.public.json)

交付工作树的 104 项回归通过，语法、导入、metadata 检查和 Phase 2 Ruff 通过。相邻回归中的 33 项失败在 Phase 1 基线上逐项复现，均来自 SQLite 测试夹具的数据库身份检查。三个生产文件的 mypy 前后各有 53 条既有诊断。[验证摘要](validation.public.json)

v10 全流程还依赖读写协议接入、以动作起点计算相对步数、控制器截止以及终步判定。本阶段验收结果仅覆盖软件组件。正式 v9 资格记录为 0/9，v10 正式资格待验收。

交付从 7e44e865 重建，以特定路径引入 Phase 1 的源码依赖和本轮改动。原始失败日志和冻结原件由项目本地保管。公开文件提供源码、校验值和软件验证摘要。[源码清单](source-manifest.public.json) · [交付计划](plan.md)
