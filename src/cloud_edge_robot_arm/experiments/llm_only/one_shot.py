"""LLM-Only One-Shot 基线说明。

B01 只在任务开始前请求一次模型生成完整 TaskContract；异常后任务失败或整体重试。
"""

B01_DESCRIPTION = "任务开始时一次性生成完整 TaskContract，不使用本地恢复和局部重规划。"
