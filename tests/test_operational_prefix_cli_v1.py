"""Real default CLI/import and read-only policy checks, without runtime construction."""

import json
import os
import subprocess
import sys
from importlib import util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def cli():
    source = ROOT / "scripts/run_operational_prefix_v1.py"
    assert source.is_file(), "Task1 operational CLI interface is missing"
    spec = util.spec_from_file_location("oc2_task1_cli", source)
    assert spec is not None and spec.loader is not None
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_default_cli_is_inputs_only_without_effects(tmp_path, capsys, monkeypatch):
    module = cli()

    def forbidden(*args, **kwargs):
        pytest.fail("default main constructed an application")

    monkeypatch.setattr(module.OperationalPrefixApplicationV1, "from_startup", forbidden)
    output = tmp_path / "fresh"
    assert module.main(["--output", str(output)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["scope"] == "INPUTS_ONLY" and result["actual_execution"] == "NOT_RUN"
    assert result["inputs"]["config"]["ordinary_max_age_ns"] == 5_000_000_000
    assert not output.exists()
    inventory = result["inputs"]["source_inventory"]
    for source in (
        "scripts/run_operational_prefix_v1.py",
        "src/cloud_edge_robot_arm/research/operational_prefix_schema_v1.py",
        "src/cloud_edge_robot_arm/research/operational_capture_v1.py",
        "src/cloud_edge_robot_arm/research/operational_prefix_v1.py",
        "src/cloud_edge_robot_arm/research/operational_time_v1.py",
        "src/cloud_edge_robot_arm/simulation_runtime/worker.py",
        "src/cloud_edge_robot_arm/simulation_runtime/sqlite_repository.py",
        "assets/robots/franka_panda/scene.xml",
    ):
        assert inventory[source]["bytes"] > 0 and len(inventory[source]["sha256"]) == 64


def test_real_default_import_has_no_runtime_or_network_effects(tmp_path):
    assert (ROOT / "scripts/run_operational_prefix_v1.py").is_file(), "Task1 CLI is missing"
    program = """import importlib.abc, importlib.util, sys
from pathlib import Path
class DenyRuntime(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in {
            "cloud_edge_robot_arm.research.operational_time_v1",
            "cloud_edge_robot_arm.simulation_runtime.sqlite_repository",
            "cloud_edge_robot_arm.simulation_runtime.worker",
            "cloud_edge_robot_arm.simulation.mujoco.backend", "mujoco", "sqlite3"
        }:
            raise AssertionError("runtime import: " + fullname)
sys.meta_path.insert(0, DenyRuntime())
def audit(event, args):
    if event in {"os.mkdir", "sqlite3.connect", "socket.__new__", "socket.connect"}:
        raise AssertionError("runtime effect: " + event)
sys.addaudithook(audit)
spec = importlib.util.spec_from_file_location("real_cli", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
raise SystemExit(module.main(["--output", sys.argv[2]]))
"""
    output = tmp_path / "never-created"
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            program,
            str(ROOT / "scripts/run_operational_prefix_v1.py"),
            str(output),
        ],
        cwd=ROOT,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": "src:."},
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["actual_execution"] == "NOT_RUN"
    assert completed.stderr == "" and not output.exists()


@pytest.mark.parametrize(
    "change",
    [
        ("settle_steps", True),
        ("settle_steps", 120.0),
        ("settle_steps", 119),
        ("ordinary_max_age_ns", True),
        ("ordinary_max_age_ns", 5_000_000_000.0),
        ("ordinary_max_age_ns", 0),
        ("max_attempts", 2),
        ("worker_authority", True),
        ("preregistered", True),
        ("endpoint", "local"),
        ("group_inventory", {}),
    ],
)
def test_malformed_or_caller_authority_policy_rejects_without_output(tmp_path, change, capsys):
    module = cli()
    policy = json.loads((ROOT / "configs/research/operational_prefix_v1.json").read_bytes())
    policy[change[0]] = change[1]
    config = tmp_path / "policy.json"
    config.write_text(json.dumps(policy))
    output = tmp_path / "fresh"
    assert module.main(["--config", str(config), "--output", str(output)]) == 1
    captured = capsys.readouterr()
    assert captured.out == "" and json.loads(captured.err)["scope"] == "INPUTS_ONLY"
    assert not output.exists()


@pytest.mark.parametrize("kind", ["missing", "symlink", "duplicate", "malformed"])
def test_invalid_original_inputs_reject_without_effects(tmp_path, kind, capsys):
    module = cli()
    config = tmp_path / "config.json"
    if kind == "symlink":
        config.symlink_to(ROOT / "configs/research/operational_prefix_v1.json")
    elif kind == "duplicate":
        source = (ROOT / "configs/research/operational_prefix_v1.json").read_text()
        config.write_text(source.replace("{", '{"seed":0,', 1))
    elif kind == "malformed":
        config.write_text("{")
    output = tmp_path / "fresh"
    assert module.main(["--config", str(config), "--output", str(output)]) == 1
    assert json.loads(capsys.readouterr().err)["scope"] == "INPUTS_ONLY"
    assert not output.exists()


def test_execute_once_cli_real_worker_no_retry(tmp_path, capsys, monkeypatch):
    from cloud_edge_robot_arm.research import operational_prefix_v1 as api
    from tests.test_operational_capture_v1 import cpu_components, require_task2

    require_task2()
    main = cli()
    original = api._new_prefix_backend_v1
    from tests.test_operational_prefix_v1 import application

    app = application(tmp_path / "owned")
    cpu_components(monkeypatch, app)
    # CLI receives this actual startup-owned application; final verdict is real.
    calls = []

    def factory(config, *, output):
        calls.append("startup")
        return app

    monkeypatch.setattr(main.OperationalPrefixApplicationV1, "from_startup", factory)
    assert main.main(["--output", str(tmp_path / "unused"), "--execute-once"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert calls == ["startup"]
    assert result["receipt"]["source_prefix_complete"] is True
    assert original is not None
