"""仅大模型决策基线实验包。

本包只实现 simulation-only 的对照基线框架，不注册真实硬件 runner，也不会自动调用
真实收费模型或下载本地模型。
"""

from cloud_edge_robot_arm.experiments.llm_only.runner import (
    LLMOnlyProfile,
    LLMOnlyProvider,
    run_llm_only_baseline,
)

__all__ = ["LLMOnlyProfile", "LLMOnlyProvider", "run_llm_only_baseline"]
