"""Private native bootstrap that verifies R545 and delegates in the same process."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import runpy
import sys
from pathlib import Path


def _bound_bytes(binding: dict[str, str]) -> bytes:
    path = Path(binding["path"])
    if path.resolve() != path:
        raise RuntimeError("native source binding left the selected checkout")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != binding["sha256"]:
        raise RuntimeError("native source binding changed")
    return data


def _write_receipt(path: Path, payload: dict[str, object]) -> None:
    staging = path.with_suffix(".tmp")
    with staging.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, allow_nan=False)
    staging.replace(path)


def main() -> int:
    """Run the registered overlay and then the original single-episode CLI."""
    receipt = Path(sys.argv[1])
    bindings = json.loads(sys.argv[2])
    flags = sys.argv[3:]
    try:
        overlay_path = bindings["overlay"]["path"]
        namespace = {"__file__": overlay_path, "__name__": "_bigsmall_registered_r545"}
        exec(compile(_bound_bytes(bindings["overlay"]), overlay_path, "exec"), namespace)
        proof = namespace["configure_overlay"]()
        if (
            proof.get("status") != "IMPORT_AND_CPU_ABI_PASS"
            or proof.get("cuda_initialized") is not False
            or any(
                type(proof.get(key)) is not int or proof[key] != 0
                for key in ("model_loads", "generation_calls", "paid_calls")
            )
        ):
            raise RuntimeError("registered R545 overlay admission failed")
        for name, binding in bindings["modules"].items():
            module = importlib.import_module(name)
            if getattr(module, "__file__", None) != binding["path"]:
                raise RuntimeError("native project import did not use the selected checkout")
            _bound_bytes(binding)
        entry = bindings["entry"]["path"]
        _bound_bytes(bindings["entry"])
        with Path(sys.executable).open("rb") as stream:
            executable_sha256 = hashlib.file_digest(stream, "sha256").hexdigest()
    except Exception as error:
        _write_receipt(receipt, {
            "status": "REJECTED_BEFORE_EPISODE",
            "executable": sys.executable,
            "error_type": type(error).__name__,
        })
        return 2

    _write_receipt(receipt, {
        "status": "READY_TO_DELEGATE",
        "pid": os.getpid(),
        "executable": sys.executable,
        "executable_sha256": executable_sha256,
        "prefix": sys.prefix,
        "version": list(sys.version_info[:3]),
        "registered_overlay": bindings["overlay"],
        "project_modules": bindings["modules"],
        "entry": bindings["entry"],
        "r545_admission": proof,
    })
    sys.argv = [entry, *flags]
    runpy.run_path(entry, run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
