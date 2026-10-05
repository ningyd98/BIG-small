"""Artifact-local passive capture diagnosis; preparation never loads a model."""

import numpy as np


def copy_arrays(value):
    return {
        name: getattr(value, name)
        for name in sorted(dir(value))
        if not name.startswith("_") and isinstance(getattr(value, name), np.ndarray)
    }
