# R283：失败侧车可选 marker 的 ROOT 元数据门修正计划

实际规划模型：gpt-6-astra。仅计划，等待 ROOT 完整审阅。

原 e7802e 结算门在第 60 行直接索引 `assertions_completed` 而 KeyError，尚未归档或写角色。完整原门及原失败保留。9bf289 的普通物理读取确认：固定 raw 493240 字节、SHA 8acf455034ee7dc54e06131ea3983b9819edc18fbb81c9bd1136535fbd8b1f9d 没有此顶层键，`entered_behavior` 为 true；缺失不等于 false，也不是 PASS。

ROOT 仅在 R283 创建新独立门。原 identity 检查保留 data/PID/node/entered_behavior，只移除错误 marker conjunct；显式记录 presence、value 和 unobserved。对本次固定 raw 严格要求 presence=false、value=null，将事实关联 raw pin/node/PID 写入成功或失败完整报告。其他全部检查、角色重建、归档、mode、CAS 和结算路径不变。旧门不编辑、不重放。

完整 before 已保存到 `before/root-settle-failed-wait-memory.py`，manifest 含完整 base64 和 mode。15 个固定输入及精确新 argv 见 plan.json；不将描述字段当路径，不把带额外属性的记录与三字段文件 pin 整体比较。

新源码须先完整持久保存、native 参数/真实回执、有限 diff、SHA 和 ROOT 全文/输入/argv 门。随后仅一次 ROOT 普通 stdlib 检查，120 秒，stdout ≤6000 UTF-8 字节，完整 actual 先保全；yield 只等待同 session，任何新失败 STOP，不重试。无产品、测试、静态、SQL、Git、审阅或新行为验证额度。

成功仅结算原 wait_memory ROOT RESERVED1/0→SPENT_UNEXPECTED_FAILURE1/0。AUTHOR 保持 SPENT1/0，其他两 key 不释放；原失败和所有 raw 不改。ROOT 完整核验 selected role 前后字节后，R281 才可另门释放源码修正。原测试仍失败，T2/T12/native/formal 不完成。

