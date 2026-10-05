"""Bounded legacy aggregate semantics adapter for qualified SOFTWARE_ONLY RED."""
import hashlib
import json
from types import SimpleNamespace

import numpy as np


class StateGuardError(ValueError):
    pass


class MujocoStateContract:
    def __init__(self, **kwargs):
        self.inputs = kwargs


def snapshot_data_arrays(data, model, *, contract, runtime_version):
    digest = hashlib.sha256()
    for name in sorted(dir(data)):
        if not name.startswith("_"):
            member = getattr(data, name)
            if isinstance(member, np.ndarray):
                digest.update(json.dumps((name, list(member.shape), member.dtype.str)).encode())
                digest.update(member.tobytes(order="C"))
    return SimpleNamespace(digest=digest.hexdigest())
