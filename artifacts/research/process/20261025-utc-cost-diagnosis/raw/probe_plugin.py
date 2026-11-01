"""Diagnostic probe (NOT a product patch): measures the ceiling of removing
per-access re-parse + deep copy + per-character hash validation."""
import json, re
from cloud_edge_robot_arm.vision import local_temporal as lt

_sha_re = re.compile(r"[0-9a-f]{64}\Z")

def fast_sha(value):
    if type(value) is not str or _sha_re.fullmatch(value) is None:
        raise ValueError("SHA256 required")
    return value

lt._sha = fast_sha
_orig = lt.LocalEnvelope.to_payload

def cached_to_payload(self):
    try:
        return object.__getattribute__(self, "_probe_payload")
    except AttributeError:
        value = _orig(self)
        object.__setattr__(self, "_probe_payload", value)
        return value

def cached_semantic(self):
    try:
        return object.__getattribute__(self, "_probe_semantic")
    except AttributeError:
        value = cached_to_payload(self)["payload"]
        object.__setattr__(self, "_probe_semantic", value)
        return value

lt.LocalEnvelope.to_payload = cached_to_payload
lt.LocalEnvelope.semantic = property(cached_semantic)
