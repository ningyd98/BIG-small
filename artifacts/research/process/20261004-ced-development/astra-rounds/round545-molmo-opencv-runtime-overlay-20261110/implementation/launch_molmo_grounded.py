"""仅在末尾追加既有应用依赖，保持 Molmo 推理包身份并原样转交诊断参数。"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import runpy
import sys
from pathlib import Path
from typing import Any

ROUND = Path(__file__).resolve().parents[1]
WORKTREE = ROUND.parents[5]
ORIGINAL = Path("/home/ningyd/文档/ChatGPT/BIGsmall")
EXPECTED_PYTHON = ORIGINAL / (
    "datasets/model-cache/ordered-small-vlm-20261109/runtimes/molmoer-r505/bin/python"
)
CLI = WORKTREE / "scripts/probe_molmo_grounded_planner.py"
PROOF_SHA256 = "654de3974d33c6519bf7c211c6a76d1c0f1ec943d7435f595f6ee7dbb9d9bedc"


def _verify_import(name: str, module: Any, expected: dict[str, Any]) -> dict[str, Any]:
    path = Path(module.__file__)
    if (
        path != Path(expected["file"])
        or getattr(module, "__version__", None) != expected["version"]
    ):
        raise RuntimeError(f"{name} import identity drift")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != expected["sha256"]:
        raise RuntimeError(f"{name} import identity hash drift")
    return {"file": str(path), "version": expected["version"], "sha256": digest}


def configure_overlay() -> dict[str, object]:
    """核对原有推理环境并执行 CPU ABI 检查；不创建处理器或模型。"""
    if Path(sys.executable) != EXPECTED_PYTHON:
        raise RuntimeError("use the validated Molmo r505 interpreter with -B")
    os.environ.update(PYTHONDONTWRITEBYTECODE="1", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    sys.dont_write_bytecode = True
    proof_path = ROUND / "planner-r545-import-preflight.stdout"
    raw = proof_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != PROOF_SHA256:
        raise RuntimeError("original runtime preflight proof drift")
    expected = json.loads(raw)["modules"]
    app = str(ORIGINAL / ".venv/lib/python3.12/site-packages")
    baseline = EXPECTED_PYTHON.parent.parent / "lib/python3.12/site-packages/baseline.pth"
    if hashlib.sha256(baseline.read_bytes()).hexdigest() != (
        "c27799d1447657bb728396e8a7df833ee725b483943faf5724f73904805920b1"
    ):
        raise RuntimeError("validated baseline.pth drift")
    if app not in sys.path:
        sys.path.append(app)
    for name in ("torch", "transformers"):
        site = str(Path(expected[name]["file"]).parent.parent)
        if site not in sys.path or sys.path.index(site) >= sys.path.index(app):
            raise RuntimeError("validated runtime must precede app dependencies")
    sys.path.insert(0, str(WORKTREE))
    sys.path.insert(0, str(WORKTREE / "src"))
    modules = {}
    for name in ("torch", "transformers", "numpy", "cv2", "pydantic", "cryptography"):
        modules[name] = _verify_import(name, importlib.import_module(name), expected[name])
    import cv2
    import numpy as np
    import torch
    from transformers import AutoModelForImageTextToText, AutoProcessor

    assert AutoProcessor is not None and AutoModelForImageTextToText is not None
    rgb = np.zeros((4, 4, 3), dtype=np.uint8)
    rgb[1:3, 1:3] = 255
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    count, _, stats, _ = cv2.connectedComponentsWithStats((gray > 0).astype(np.uint8))
    if count != 2 or stats[1, cv2.CC_STAT_AREA] != 4:
        raise RuntimeError("OpenCV CPU ABI check failed")
    if not np.array_equal(torch.from_numpy(gray).numpy(), gray) or torch.cuda.is_initialized():
        raise RuntimeError("CPU ABI or zero-CUDA-initialization check failed")
    for name in (
        "cloud_edge_robot_arm.vision.molmo_pointing",
        "cloud_edge_robot_arm.vision.grounded_planner",
        "scripts.probe_molmo_grounded_planner",
    ):
        module = importlib.import_module(name)
        path = Path(module.__file__)
        modules[name] = {"file": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    return {
        "status": "IMPORT_AND_CPU_ABI_PASS",
        "modules": modules,
        "model_loads": 0,
        "generation_calls": 0,
        "paid_calls": 0,
        "cuda_initialized": False,
        "hardware_dispatch": False,
    }


def main(argv: list[str] | None = None) -> int:
    """只消费 --preflight；其他参数交给当前受审 CLI，保留其退出码。"""
    args = list(sys.argv[1:] if argv is None else argv)
    result = configure_overlay()
    if args == ["--preflight"]:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    previous = sys.argv
    sys.argv = [str(CLI), *args]
    try:
        runpy.run_path(str(CLI), run_name="__main__")
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 1
    finally:
        sys.argv = previous
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
