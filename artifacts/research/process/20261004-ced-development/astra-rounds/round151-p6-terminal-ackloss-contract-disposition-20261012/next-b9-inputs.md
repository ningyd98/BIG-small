# 下一实际 B9 计划的必需输入

公开 SQL 任务/attempt/artifact/batch 视图目前呈现提交历史和路径，没有显式区分 confirmed publication 与已撤回的 unconfirmed 文件。B9 必须读取真实生产者、消费者与版本化一致性状态；所有声称已确认结果的消费要有明确拒绝路径。

必须保留真实 terminal SQL、原失败和原始数据；不得无权负覆盖成功，不得把 SQL COMMITTED 当私有 ACTIVE，也不得重置时间原点、任务预算或做跨域换算。service/model 当前仍为保护输入。

若未来合同要求终态消费者确认，应在真实 Astra 精确计划中分别预算最终 COMMIT 后关闭连接、broker 超时/原 bound 到期和正常软件出版对照，本轮没有执行或授权这些 case。源路径及 full SHA 见 next-b9-inputs.json，A 仅租约基础上限，B/C/D 未激活。
