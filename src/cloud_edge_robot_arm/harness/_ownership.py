"""Stable output reservation shared by a Harness wrapper and its child."""

from __future__ import annotations

import fcntl
import hashlib
import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


def canonical_output(path: Path) -> Path:
    """Resolve parent aliases without following the episode leaf itself."""
    if not path.name or path.name == "..":
        raise ValueError("episode output must name a new directory")
    return path.parent.resolve() / path.name


@contextmanager
def reserve_output(output: Path) -> Iterator[int]:
    """Hold an exclusive output lease with a descriptor the child can inherit."""
    output.parent.mkdir(parents=True, exist_ok=True)
    name_hash = hashlib.sha256(os.fsencode(output.name)).hexdigest()
    sidecar = output.parent / f".bigsmall-harness-{name_hash}.lock"
    descriptor = os.open(
        sidecar, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, 0o600,
    )
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("episode output lease must be a regular file")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("episode output is owned by a running invocation") from None
        if os.path.lexists(output):
            raise ValueError("episode output directory already exists")
        yield descriptor
    finally:
        # An inherited descriptor keeps the same lock alive if the wrapper exits first.
        os.close(descriptor)
