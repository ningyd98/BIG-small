"""隔离启动器必须拒绝依赖漂移并完整转交 CLI 参数。"""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


def launcher():
    path = Path(__file__).with_name("launch_molmo_grounded.py")
    spec = importlib.util.spec_from_file_location("runtime_overlay_fixture", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_forwarding_preserves_arguments_and_exit(monkeypatch):
    module = launcher()
    monkeypatch.setattr(module, "configure_overlay", lambda: {"model_loads": 0})
    seen = []

    def delegated(path, run_name):
        seen.append((path, list(sys.argv), run_name))
        raise SystemExit(7)

    monkeypatch.setattr(module.runpy, "run_path", delegated)
    assert module.main(["--mode", "dry-run", "--output", "unchanged"]) == 7
    assert seen[0][1][1:] == ["--mode", "dry-run", "--output", "unchanged"]
    assert seen[0][2] == "__main__"


def test_wrong_import_origin_is_rejected(tmp_path):
    module = launcher()
    expected = {
        "file": "/validated/torch/__init__.py",
        "version": "2.6.0+cu124",
        "sha256": "0" * 64,
    }
    with pytest.raises(RuntimeError, match="identity"):
        module._verify_import(
            "torch",
            SimpleNamespace(__file__=str(tmp_path / "wrong.py"), __version__="2.6.0+cu124"),
            expected,
        )
