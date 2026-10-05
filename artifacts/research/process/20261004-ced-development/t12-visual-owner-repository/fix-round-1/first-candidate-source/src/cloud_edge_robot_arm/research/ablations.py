"""冻结三个核心消融，只关闭目标组件，保留感知和安全设置。"""

from collections.abc import Mapping
from typing import Any

ABLATION_COMPONENTS = {
    "NO_UNCERTAINTY": "uncertainty_gate",
    "NO_TIME_VALIDITY": "completion_age_gate",
    "NO_LOCAL_REPAIR": "local_repair",
}


def apply_ablation(base: Mapping[str, Any], method_id: str) -> dict[str, Any]:
    """复制共同设置并关闭唯一注册组件，不静默修改其他参数。"""
    if method_id not in ABLATION_COMPONENTS:
        raise ValueError("unregistered research ablation")
    component = ABLATION_COMPONENTS[method_id]
    if base.get(component) is not True or base.get("safety_shield") is not True:
        raise ValueError("ablation requires the enabled common component and SafetyShield")
    result = dict(base)
    result[component] = False
    return result
