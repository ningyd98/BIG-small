"""LLM-only 指标说明。

当前模块只定义指标名称，后续真实 provider runtime accepted 后再扩展统计检验。
"""

LLM_ONLY_METRICS = [
    "task_success_rate",
    "total_completion_time_ms",
    "model_request_count",
    "valid_contract_rate",
    "schema_validation_failure_count",
    "semantic_validation_failure_count",
    "repair_count",
    "refusal_rate",
    "unsafe_proposed_action_count",
    "unsafe_command_execution_count",
    "average_model_latency_ms",
    "p95_model_latency_ms",
    "token_usage",
    "estimated_cost",
]
