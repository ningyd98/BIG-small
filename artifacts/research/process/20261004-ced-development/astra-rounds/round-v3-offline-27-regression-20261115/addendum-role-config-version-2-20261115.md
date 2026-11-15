# 阶段3配置前置补充：role_config_version = 2

实际规划模型：**gpt-6-astra**。本补充只追加配置约束，原 `plan.md`、`plan.json`及原哈希清单字节不变；不扩大三个新增文件的实施范围。

已独立核对V3全部40例。历史 `cloud_model_snapshot` digest可精确还原；在整数版本1..1024中，仅 **2** 使完整 `configuration_hash(cloud_request_settings(...))`匹配各例历史值：

- 历史/版本2：`eb31dd5eb394646e1a09a0116c7d8d58c954a8c200f2443d12b5ce3ef972362d`
- 默认版本1：`29a01c7a0e7930df38425f06a69854da80fabbc955402cfc324bb63fe3b63ad8`

实际构造 `MolmoGroundedPlannerAdapter` 与 `MolmoWorkerPlanner`的只读探针确认：cloud设置为2时，worker构造器继承2，worker完整设置哈希也匹配。探针只使用实际RGBDPlannerAdapter配置和构造器，尚未实施的FrozenCloudReplayAdapter仍需以下断言；未调用plan/point、加载模型、联网或读取凭据。

实施必须按以下顺序：

1. 构造FrozenCloudReplayAdapter后立刻设置 `role_config_version = 2`，**在**构造MolmoGroundedPlannerAdapter、MolmoWorkerPlanner或角色binding之前完成。grounded构造器会缓存cloud配置hash，不能事后修改版本再手工修缓存。
2. 每例先核对snapshot digest，再检查 `configuration_hash(cloud_request_settings(frozen_cloud)) == historical_role.request_config_hash`；保留所有请求设置字段。
3. 正常构造真实grounded和worker；再次断言 `worker.role_config_version == 2`及worker完整配置hash与该例历史值一致，再调用make_worker_binding/run_worker_episode。
4. 任一不符停止并保存证据，不修改期望hash、不忽略version、不删字段、不改容差、不在运行时搜索其它版本。完整请求体/RGB/query、源码固定、零真实模型/网络要求继续有效。

**版本2是历史配置的精确恢复，不是请求容差或hash放松。** 原计划和本补充仍为计划/前置约束；27新闭环尚未由本任务执行。

独立证据：`addendum-role-config-version-2-20261115.evidence.json`（40例逐项哈希、snapshot与构造器结果）。本补充自有 `.SHA256SUMS`，不覆写原计划的SHA256SUMS。
