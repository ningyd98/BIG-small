# 旧成功→现行T12公开差异

| 项目 | 原成功公开值 | 现行或边界 |
|---|---|---|
| 模型 | qwen3.8-max，35真实请求/独立valid | 别名仍Max；不猜服务端不可变权重 |
| RGB-D | 两图320×240 | ced.roles相同，未新实际调用 |
| 坐标 | normalized_1000 | ced.roles为pixel，待实施 |
| 温度/token | 0/512 | 原工厂消费既有profile；未打开实际profile |
| thinking | wire enable_thinking=false | compatible wire字段缺失，超出四owned，NEEDS_ASTRA |
| 抓取域 | mujoco_upright_box_v1 | 当前v2；旧成功不能当v2实证 |
| source/角色 | 历史source索引 | 当前source逐项差异见JSON，旧成功不当新冻结 |
| 成本 | invoice null | ledger只读，sent/timeout/retry不能删，未新发送 |
| 角色actual | 历史连接/操作成功 | cold+3warm需P8源静止与ROOT后续实际调度 |
