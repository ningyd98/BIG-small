"""Scoped canonical instruction/pixel identity binding without simulator truth.

Unsupported language or ambiguous color remains unavailable. This verifies a
visible chromatic identity, not arbitrary semantic detection or calibrated pose.
"""

import colorsys
import math
from collections.abc import Sequence

_COLORS = {"red": "红色", "yellow": "黄色", "blue": "蓝色", "green": "绿色",
           "purple": "紫色", "orange": "橙色", "cyan": "青色"}
_INSTRUCTIONS = {
    text: color for color, chinese in _COLORS.items() for text in (
        f"Move the {color} block to the green region.",
        f"将{chinese}方块放到绿色区域",
        f"pick the {color} cube and place it in the green target region",
    )
}
_HUE_DEGREES = {"red": (342., 18.), "orange": (18., 42.), "yellow": (42., 78.),
                "green": (90., 162.), "cyan": (162., 198.), "blue": (198., 258.),
                "purple": (258., 318.)}


def _matches(color: str, rgb: Sequence[float]) -> bool:
    if len(rgb) != 3 or any(not math.isfinite(value) or not 0 <= value <= 1 for value in rgb):
        return False
    hue, saturation, value = colorsys.rgb_to_hsv(*rgb)
    if saturation < .25 or value < .1:
        return False
    lower, upper = _HUE_DEGREES[color]
    degrees = hue * 360
    return lower <= degrees <= upper if lower < upper else degrees >= lower or degrees <= upper


def validate_grounded_colors(
    instruction: str, target_rgb: Sequence[float], destination_rgb: Sequence[float]
) -> tuple[str, str]:
    color = _INSTRUCTIONS.get(instruction.strip())
    if color is None:
        raise ValueError("instruction outside the canonical visible-color scope")
    if not _matches(color, target_rgb):
        raise ValueError("observed pixels do not identify the requested target")
    if not _matches("green", destination_rgb):
        raise ValueError("observed pixels do not identify the requested destination")
    return color, "green"
