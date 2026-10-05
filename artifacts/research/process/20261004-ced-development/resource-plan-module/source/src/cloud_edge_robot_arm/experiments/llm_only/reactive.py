"""LLM-Only Reactive 基线说明。

B02 每一步或异常后重新请求模型生成下一步动作，但输出仍必须经过契约校验和 SafetyShield。
"""

B02_DESCRIPTION = "每一步或异常后调用模型，不使用确定性本地恢复、局部重规划和技能缓存。"
