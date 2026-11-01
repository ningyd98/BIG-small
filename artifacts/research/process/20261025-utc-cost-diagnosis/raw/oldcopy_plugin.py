"""Diagnostic probe: restore the pre-R365 _copy predicate to measure its timing effect."""
from collections.abc import Mapping
from math import isfinite
from cloud_edge_robot_arm.vision import local_temporal as lt

def old_copy(value):
    if value is None or type(value) in (bool, str):
        if isinstance(value, (bool, str)) or value is None:
            return value
    if type(value) is int:
        if not -(2**63) < value < 2**63:
            raise ValueError("bounded integral JSON required")
        return value
    if type(value) is float:
        if not isfinite(value):
            raise ValueError("finite JSON required")
        return value
    if isinstance(value, Mapping):
        result = {}
        for key, item in value.items():
            if type(key) is not str or key in result:
                raise ValueError("unique strict JSON keys required")
            result[key] = old_copy(item)
        return result
    if type(value) is list:
        return [old_copy(item) for item in value]
    raise ValueError("detached JSON data required; live objects are forbidden")

lt._copy = old_copy
