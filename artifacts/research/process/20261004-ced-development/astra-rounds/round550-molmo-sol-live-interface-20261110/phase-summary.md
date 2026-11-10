# R550 真实云端规划与接口校验阶段总结

2026-11-10。沿用已公开分支 `codex/molmo-opencv-grounded-planner-20261110`，生产代码基线 `4c21a91746b412ddc01dc56f60c8c71b086f46e9`。这是 R542–R549 本地集成的后续真实云端验证；旧阶段总结与失败原件不改写。

**真实云端已返回，技能内容离线校验通过；实际管线因观测过期拒绝生成合同。** 本轮完成一次有界实验，不能记作端到端 PLANNED 或实机成功。

|层次|实际结果|
|---|---|
|新鲜输入|模型加载后重新采集 MuJoCo S01 RGB与对齐 optical-z float32 深度；实际 captured_at 07:27:43.863287 UTC；不是归档帧改时间。|
|真实 Molmo2-ER|BF16；1次加载、2次生成均完成，两查询约1.210/0.805秒；原生目标像素(179,109)，有界唯一红区域关联至(179,119)，区域原生点(130,72)；原预测与关联证据分别保存。|
|OpenCV与深度|初始几何 READY，沿用原抓取和跟踪检查；extent_complete=false、depth_error_bound_m=null，仍只是开发几何估计。|
|真实云端|现有官方接口实际调用1次并收到完整回复，请求与返回模型均为gpt-6.1-sol；low/4096/json_object/30秒均未改；finish_reason=stop。|
|内容接口|真实原文经现有严格解析器离线校验：JSON/额外字段/技能白名单通过，非空10步，核心顺序符合现有构造器；标记 OFFLINE_CONTENT_CHECK。|
|实际管线|REQUEST_MORE_OBSERVATION；reason=capture_time_not_fresh；contract=null；dispatch=null；0次修复。返回的validation.passed=true只确认重观测哨兵，不代表可执行合同通过。|
|时间门|定位合计2.015秒；云端含本地开销往返5.796秒；云端开始时帧龄2.161秒，返回时7.957秒；原5秒门保持，过期拒绝正确生效。|
|证据|CLI raw29份、独立观测9份、联合清单47份全部字节/SHA256通过；独立观测0捕获缺口；旧两轮各26份raw及报告/清单未变。|
|软件验证|本轮观测器4项CPU检查PASS；3个implementation脚本Ruff通过；生产源码/测试/运行时未修改。历史322项回归是上一交付证据，本轮不重复声称重跑；既有全量测试失败状态仍保留。|
|真实执行边界|0次硬件派发；PHYSICAL与FORMAL_RESEARCH均NOT_PERFORMED。相机输入来自仿真，云端与本地模型推理是真实调用。|

原CLI粗粒度字段real_cloud_status=FAILED保留原样，指该次诊断没有PLANNED；独立分层结果确认传输收到真实回复，失败层为观测TTL。没有重试、重采样旧输入、调宽TTL或重建假合同。

API实际返回usage计数为输入555、输出125、总计680，其中reasoning_tokens=58。仅派生计数写入本报告，token IDs、完整原文和wire正文留在本地。客户端未捕获数值HTTP状态，记NOT_CAPTURED；金额未暴露，不能推断成本为0。

## 原因与下一轮边界

当前实现把同一帧的5秒有效期覆盖了本地感知及整个云端往返。开始云调用时剩余约2.84秒，本次云端单次往返已需5.80秒，因此即使技能答案正确也到不了合同构建。单样本只能证明本次延迟冲突，不能估算稳定性或模型排名。

下一轮建议由实际Astra先规划“云端技能意图 + 新帧本地几何复核/绑定 + 原合同校验”的流程：在云端返回后获取真正的新观测，重新核对目标身份、场景变化及原安全边界，符合条件才生成新合同；过期或变化仍拒绝。本轮未实施此行为变化，也没有简单增大TTL。

## 过程与交付

R550实际Astra计划限定追加1load/2gen/1paid、无重试；实施前22项输入/模板哈希和全部26项模型资产匹配，资源准入通过。R551第一次import分组假设不符实际Ruff配置，失败保留；R552根据原始diff准确修正，仅观测脚本导入顺序变化，CPU与静态检查随后通过。

累积真实计数为3次加载、6次生成启动且6完成、1次云端启动并收到回复；当前本轮预算已耗尽，不追加调用。严格保留原选定profile、加密密钥存储与官方路由，未激活或修改profile，未安装或改变运行时/SDK/模型资产。

本地原始目录：`datasets/model-cache/molmo-sol-r550-20261110/`，其中`live-01`保留CLI证据，`probe-01`保留实际完整InitialPlanningResponse及时间，`execution-01`保留进程原日志。联合原始清单SHA256为d672b91934677a62f832d7d07dace7d3186dbb0a5439d1d5642ae40a2553babd，47份文件共932330字节。清单与派生报告不等于完整远端复现包。

可公开交付仅本轮计划、观测/离线核验源码、CPU/静态检查及派生结论；完整raw、模型输出、token IDs、权重、SDK、DB与密钥留在本地。精确命令见[execution-command.json](execution-command.json)，机器可读结果见[execution-result.json](execution-result.json)。

API配置沿用已核对的[官方模型说明](https://developers.openai.com/api/docs/models/gpt-6.1-sol)；[官方JSON模式说明](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=chat)说明JSON模式不替代应用层schema检查，本轮保留了现有严格校验。
