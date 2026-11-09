# 按序小模型筛选（进行中）

依据用户“从上到下依次测试筛选”，固定 R501 v1 DEV16：12有目标、4缺目标，320×240。真实GPU串行；无 heldout、3D、控制或实机验收。源数据151文件冻结。通用合约23 PASS；Molmo接口测试8 PASS；R506序列化测试27 PASS，共58项（R506执行时55项，当时尚未新增Molmo3项）。

|顺序|候选|实际结果|单查询暖态p50|状态|
|---|---|---|---|---|
|1|WeVisOne-VL-4B|官方MS同名404、HF物理直连失败；0调用|未测|DOWNLOAD_DEFERRED|
|2|WeVisOne-VL-2B|同上；0调用|未测|DOWNLOAD_DEFERRED|
|3|Xiaomi-Lens-0 BF16|mask联合12/12、缺目标拒答1/4；box联合7/12；JSON格式16/16但联合3/12、缺目标0/4|原生0.978秒；JSON4.621秒|未过缺目标门槛|
|4|Molmo2-ER BF16|point联合12/12、缺目标拒答4/4；34调用；原system JSON不支持|0.727秒|首轮DEV筛选信号通过|
|5|RynnBrain1.1-2B|完整权重已校验|未测|待测|
|6|GroundingPI|完整权重已校验|未测|待测|
|7|GroundAnything DLM|完整权重已校验|未测|待测|
|8|MiniCPM-V-4.7-1B|完整权重已校验|未测|待测|

原生定位要分别查询target与destination，单任务耗时应计两次调用；以上p50为单查询。Lens掩膜点从预测前景自身质心派生，不用GT；GT仅离线评分。Molmo是新的ER checkpoint，不能与旧Molmo2-4B混同。

R506实际Astra修复离线NumPy标量JSON输出；旧score-01部分JSON及stderr原样保留。R508实际Astra修复测试harness路径绑定。旧/新计算语义相等（仅scorer SHA不同），486个Lens raw文件未改，新增Lens模型调用0。score-02为有效派生结果。成功harness在补充报告命名/provenance断言前产生verification.json，后续只读核验到verification-02.json；不冒称第二次重跑。

R507实际Astra将Molmo独立运行时只读绑定至真实TF4.57.1隔离层，保留原TF5注册冲突。单图及RGB+depth双图processor 16场景通过，但官方模板不支持原system角色，JSON_RGB/JSON_DUAL记UNSUPPORTED_SYSTEM_ROLE、0调用。双图CPU通过不代表使用深度或完整接口通过。

完整raw、模型、SDK、venv/JIT仅保留本地；远端研究代码/清单/派生报告不构成完整复现包。产品默认与硬件方案未改。
