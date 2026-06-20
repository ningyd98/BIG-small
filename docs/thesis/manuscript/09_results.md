# 第九章 实验结果与分析

## 9.1 总体结果

clean validation 计划记录数为 {{ expected_run_count }}，实际记录数为 {{ run_count }}。runtime completed 为 {{ runtime_completion_count }}，blocked before runtime 为 {{ blocked_before_runtime_count }}，synthetic sample 为 {{ synthetic_sample_count }}。状态分布为 {'BLOCKED_BY_ENV': 74, 'FAILED': 48, 'SAFETY_STOPPED': 60, 'SUCCESS': 358}。后端分布为 {'ISAAC_SIM': 18, 'MOCK': 324, 'MOVEIT_DRY_RUN': 36, 'MUJOCO': 90, 'PLANNER_DRY_RUN': 36, 'SYNTHETIC_DRY_RUN': 36}；runtime 后端分布为 {'MOCK': 324, 'MUJOCO': 90, 'PLANNER_DRY_RUN': 16, 'SYNTHETIC_DRY_RUN': 36}；结果来源分布为 {'PHASE10_MOVEIT_ENVIRONMENT_CHECK': 36, 'PHASE10_SYNTHETIC_DRY_RUN_ACTUAL': 36, 'PHASE11_2_PLANNER_ACTUAL': 36, 'PHASE11_RUNTIME_ACTUAL': 90, 'PHASE8_ACTUAL_RUN': 198, 'PHASE9_2_ISAAC_ENVIRONMENT_CHECK': 18, 'PHASE9_MUJOCO_ACTUAL_RUN': 126}。

## 9.2 PCSC、ETEAC 与 AUTO

按 control mode 聚合的 validation 数据为：{'AUTO': {'blocked_by_env_count': 0, 'confidence_interval_95': [736.8856112832491, 1059.490932037587], 'effect_size_vs_overall': 0.0025369859457222725, 'excluded_metric_sample_count': 0, 'failed_count': 36, 'maximum': 5800.0, 'mean': 898.1882716604181, 'median': 800.0, 'minimum': 0.010119983926415443, 'p25': 147.0, 'p75': 1100.0, 'p95': 1200.0, 'run_count': 162, 'sample_count': 162, 'standard_deviation': 1047.4733110052462, 'status_counts': {'FAILED': 18, 'SAFETY_STOPPED': 18, 'SUCCESS': 126}, 'success_count': 126, 'success_rate': 0.7777777777777778, 'success_rate_ci95': [0.7077421220280039, 0.8349443932974633], 'valid_metric_sample_count': 162}, 'ETEAC': {'blocked_by_env_count': 0, 'confidence_interval_95': [740.0784758311717, 1065.624928906264], 'effect_size_vs_overall': 0.006910784191144947, 'excluded_metric_sample_count': 0, 'failed_count': 36, 'maximum': 5800.0, 'mean': 902.8517023687178, 'median': 775.0, 'minimum': 0.01121999230235815, 'p25': 142.0, 'p75': 1100.0, 'p95': 1200.0, 'run_count': 160, 'sample_count': 160, 'standard_deviation': 1050.4778325575694, 'status_counts': {'FAILED': 18, 'SAFETY_STOPPED': 18, 'SUCCESS': 124}, 'success_count': 124, 'success_rate': 0.775, 'success_rate_ci95': [0.7042857994110268, 0.8328183304314551], 'valid_metric_sample_count': 160}, 'PCSC': {'blocked_by_env_count': 0, 'confidence_interval_95': [702.7993362840792, 1065.706764369103], 'effect_size_vs_overall': -0.010532758290209675, 'excluded_metric_sample_count': 0, 'failed_count': 36, 'maximum': 5800.0, 'mean': 884.2530503265912, 'median': 825.0, 'minimum': 0.010079995263367891, 'p25': 151.0, 'p75': 951.0, 'p95': 1251.0, 'run_count': 144, 'sample_count': 144, 'standard_deviation': 1110.941106382726, 'status_counts': {'FAILED': 12, 'SAFETY_STOPPED': 24, 'SUCCESS': 108}, 'success_count': 108, 'success_rate': 0.75, 'success_rate_ci95': [0.6734017453693497, 0.8136059709973562], 'valid_metric_sample_count': 144}}。这些数据可作为 validation 级软件/仿真观察事实，但不能替代 full profile 的最终统计结论。当前 verifier-gated authoritative rows 为 466。

## 9.3 安全、恢复和 F20

unsafe_command_execution_count=0。F20 覆盖运行时压力、lease expiration、restart recovery 和 duplicate worker competition；对应 evidence 来自 Phase 11 runtime actual run source evidence。该结论属于 validation 级软件运行证据。

## 9.4 MuJoCo、Isaac 和 MoveIt 边界

MuJoCo runtime 在 validation 中有实际运行记录；Isaac 和 MoveIt 部分样本为环境检查阻塞，不计入 runtime completed。F15 paired summary 显示 expected_pair_count=9，usable_authoritative_pair_count=0，blocked_pair_count=9，paired_backend_experiment_accepted=False。因此当前不能声明 MuJoCo 与 Isaac 的性能趋势一致。

## 9.5 本文方案与仅大模型方案对比

LLM-only 当前状态为 LLM_ONLY_BASELINE_PIPELINE_READY，model_runtime_type=FAKE_PROVIDER_PIPELINE_TEST，runtime_status=PIPELINE_ONLY。仓库当前已经完成仅大模型决策基线的接口设计、实验管线和 fake-provider 流程验证，但尚未形成可用于性能比较的真实大模型运行证据。因此，本文当前版本不报告仅大模型方案与云边协同方案之间的最终数值差异，相关结果将在获得经验证的 OpenAI-compatible 或本地 Ollama 运行环境后补充。

