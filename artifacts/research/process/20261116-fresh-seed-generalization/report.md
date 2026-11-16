# 新 seed 真实模型组件泛化验证

本轮按用户“重新进行泛化”请求，以提交 `19b30188f104650b52aa2eebaad17c7de42b3fa7` 冻结应用代码，预先固定 45001–45015，在既有 held-out 位姿采样器上各运行一次真实 Sol＋Molmo/MuJoCo 组件流程。没有修改算法、轨迹、39 mm 目标、MSAA 或安全阈值，没有试跑选样、重试或替换。

结果：**6/15 组件抓放成功（40.0%），Wilson 95% 区间 19.8%–64.3%**。15 是预先固定分母；区间由本核验脚本自行计算。完成 15/15，未执行 0；证据完整性为 `PASS`，源码快照种类 1。批次完成、完整性通过与抓放成功分别计算。

| 项目 | 实测 |
|---|---|
| 云模型请求 | 15/15；文本 12，图像回退 3 |
| 本地 Molmo 加载/生成 | 15 次加载，54/54 次生成完成 |
| 技能动作 / 独立物理重评分 | 58 / 15 例 |
| 原安全判据违例病例数 | 3 例；原保护与失败分母保留 |
| 标记前后端点均观测到 | 15/15；不代表连续可见 |
| Token 用量 | {'prompt_tokens': 9651, 'completion_tokens': 1069, 'total_tokens': 10720} |
| 提供方响应模型 | {'gpt-6.1-sol': 15} |
| 批次耗时 | 460.96 秒 |

逐例结果（压力标签仅为采样意图，不认定实测遮挡）：

| seed | 采样条件 | 组件成功 | 动作 | 云请求类型 | 前/后标记 | 终止原因 |
|---|---|---|---|---|---|---|
| 45001 | VISIBLE_POSE | 否 | 2 | 文本/见原件 | OBSERVED/OBSERVED | HARD_FINGER_LIMIT |
| 45002 | VISIBLE_POSE | 是 | 8 | 文本/见原件 | OBSERVED/OBSERVED | — |
| 45003 | VISIBLE_POSE | 否 | 2 | 文本/见原件 | OBSERVED/OBSERVED | HARD_FINGER_LIMIT |
| 45004 | ARM_OCCLUSION_STRESS | 否 | 0 | 图像回退 | OBSERVED/OBSERVED | RGBDModelCallFailed |
| 45005 | VISIBLE_POSE | 是 | 8 | 文本/见原件 | OBSERVED/OBSERVED | — |
| 45006 | VISIBLE_POSE | 是 | 8 | 文本/见原件 | OBSERVED/OBSERVED | — |
| 45007 | VISIBLE_POSE | 是 | 8 | 文本/见原件 | OBSERVED/OBSERVED | — |
| 45008 | ARM_OCCLUSION_STRESS | 否 | 0 | 图像回退 | OBSERVED/OBSERVED | RGBDModelCallFailed |
| 45009 | VISIBLE_POSE | 是 | 8 | 文本/见原件 | OBSERVED/OBSERVED | — |
| 45010 | VISIBLE_POSE | 是 | 8 | 文本/见原件 | OBSERVED/OBSERVED | — |
| 45011 | VISIBLE_POSE | 否 | 2 | 文本/见原件 | OBSERVED/OBSERVED | CONTROLLER_FAILURE:TIMED_OUT |
| 45012 | ARM_OCCLUSION_STRESS | 否 | 0 | 文本/见原件 | OBSERVED/OBSERVED | RGBDModelCallFailed |
| 45013 | VISIBLE_POSE | 否 | 2 | 文本/见原件 | OBSERVED/OBSERVED | HARD_FINGER_LIMIT |
| 45014 | VISIBLE_POSE | 否 | 0 | 图像回退 | OBSERVED/OBSERVED | RGBDModelCallFailed |
| 45015 | VISIBLE_POSE | 否 | 2 | 文本/见原件 | OBSERVED/OBSERVED | CONTROLLER_FAILURE:TIMED_OUT |

失败原因计数：`{'HARD_FINGER_LIMIT': 3, 'RGBDModelCallFailed': 4, 'CONTROLLER_FAILURE:TIMED_OUT': 2}`。基础设施/完整性错误：`[]`。任务失败保留为失败，未以新 seed 替换。没有在查看本轮结果后调参并重新计分。

四例视觉拒绝中，45004、45012、45014 的最后规划门均为 `boundary_depth_in_front_of_observed_top`，45008 为 `target_depth_incomplete`；见 [只读阶段摘要](evidence/failure-stage-summary.json)。这只是本批结果的描述，没有据此修改深度判据，也没有证明 MSAA 因果。两个控制器 TIMED_OUT 属于任务终止，外层进程超时为 0。

未见范围的依据是运行前对三个既有研究输出根目录中的 12,784 份身份 JSON 审计无 seed 命中，完整路径及 SHA 索引保留本地。这不证明全磁盘或模型训练语料从未出现这些场景。

**解释边界：**这批结果只检验同一注册资产、相机、控制器和既有位姿采样分布内的新 seed 组件泛化。它不证明跨物体/资产、跨域、真实硬件、连续可见性或正式研究验收；formal_research 仍为 NOT_ACCEPTED，hardware_dispatch=false。旧 held-out 已参与诊断，其 8/15 与旧 27/40 不与本批合并，也不把不同采样构成直接当作配对提升。

本轮源码与协议在请求前逐文件冻结，云配置逐例核对，原 REQUEST observer 保持每例最多一次且无自动重试。核验复用了旧 verifier 的六个原函数，格式化后 AST 相同：包括云载荷/原始 RGB/裁剪来源核对，以及按原 CompletionCriteria 的物理样本独立重评分；六个函数没有重写判据。新批次控制及核验脚本的 Ruff 无问题，来源/云配置漂移负控在无调用检查中拒绝。

运行后再校验 Molmo 注册的 26 个本地资产文件及旧 V3 的全部 7,041 份冻结证据，均保持原字节，见 [后置检查](evidence/postflight.json)。本轮产生 2,235 个证据文件、262,285,396 字节，原始数据库、图像和模型请求/响应仅留本地。

可核对文件：[冻结协议](protocol.json)、[运行前计划](plan.md)、[源清单](source-freeze.json)、[历史身份审计](evidence/history-audit.json)、[当前模型只读复核](evidence/pre-run-review.json)、[最终核验](verification.json)、[批次原始结果（仅本地）](raw-local/run-01/batch-result.json)。计划为运行前冻结原件，其复选框未按事后结果改写；实际状态以本报告和回执为准。

完整 raw、图像、请求/响应及运行数据库留在忽略目录 raw-local；仅提交协议、脚本、清单和派生报告，不称为完整远端复现包。公开推送仍暂缓。
