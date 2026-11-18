"""Shared local capacity admission for the native Molmo runtime."""

from __future__ import annotations

import fcntl
import shutil
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any


@contextmanager
def admit_resources(model_directory: Path, lock_path: Path | None) -> Iterator[dict[str, Any]]:
    """Hold the existing shared lock and check local capacity before model load."""
    lock_path = lock_path or (
        model_directory.resolve().parents[2]
        / "zdtaichu5-9b-fp8-round473/research/.r468-r469-gpu.lock"
    )
    if not lock_path.is_file():
        raise ValueError("existing shared GPU lock is required")
    with lock_path.open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        apps = subprocess.check_output(
            ["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader"], text=True
        ).strip()
        free = int(
            subprocess.check_output(
                ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                text=True,
            ).strip()
        )
        ram = (
            int(
                next(
                    row.split()[1]
                    for row in Path("/proc/meminfo").read_text().splitlines()
                    if row.startswith("MemAvailable:")
                )
            )
            * 1024
        )
        disk = shutil.disk_usage(model_directory).free
        if apps or free < 12000 or ram < 8 * 1024**3 or disk < 60 * 1024**3:
            raise RuntimeError("local resource admission failed")
        yield {
            "gpu_free_MiB": free,
            "ram_available_bytes": ram,
            "disk_free_bytes": disk,
            "foreign_compute_apps": False,
            "lock_path": str(lock_path),
        }
