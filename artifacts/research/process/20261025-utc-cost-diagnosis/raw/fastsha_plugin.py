"""Diagnostic probe: regex-based SHA validation only (semantics identical)."""
import re
from cloud_edge_robot_arm.vision import local_temporal as lt
_re = re.compile(r"[0-9a-f]{64}\Z")

def fast_sha(value):
    if type(value) is not str or _re.fullmatch(value) is None:
        raise ValueError("SHA256 required")
    return value

lt._sha = fast_sha
