"""新轮次来源、累计计数及运行参数必须在模型委托前落到冻结证据。"""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PLAN_REL = (
    "artifacts/research/process/20261004-ced-development/astra-rounds/"
    "round569-current-suite-revalidation-20261112/plan.json"
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")


def current_binding(tmp_path, monkeypatch, *, raw_root=None):
    """临时Git来源与测试信任锚；实际CLI没有可覆盖信任锚的参数。"""
    from scripts import probe_molmo_multiscene as module

    original_root = module.ROOT
    plan = json.loads((original_root / PLAN_REL).read_text())
    source = tmp_path / "source"
    source.mkdir()
    for name in plan["required_source_paths"]:
        destination = source / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original_root / name, destination)
    raw_root = raw_root or tmp_path / "run"
    asset_manifest = tmp_path / "assets.json"
    write_json(asset_manifest, {"files": [{"Path": f"stub-{i}"} for i in range(26)]})
    runtime = plan["runtime"]
    runtime.update(
        native_python=sys.executable,
        model_directory=str(tmp_path / "model"),
        model_store=str(tmp_path / "models.db"),
        profile_id="fixture",
        gpu_lock=str(tmp_path / "gpu.lock"),
        new_raw_root=str(raw_root),
    )
    plan["external_inputs"][0].update(
        path=str(asset_manifest), bytes=asset_manifest.stat().st_size,
        sha256=digest(asset_manifest),
    )
    prior_rel = str(Path(plan["prior_evidence"]["path"]).relative_to(original_root))
    plan["prior_evidence"]["path"] = str(source / prior_rel)
    write_json(source / PLAN_REL, plan)
    hashes = {name: digest(source / name) for name in plan["required_source_paths"]}

    def git(*args):
        return subprocess.check_output(
            ["git", "-c", "user.name=CPU Fixture", "-c", "user.email=cpu@example.invalid",
             "-c", "core.hooksPath=/dev/null", "-C", str(source), *args],
            text=True, stderr=subprocess.DEVNULL,
        ).strip()

    git("init", "-q")
    git("add", ".")
    git("commit", "--no-gpg-sign", "-qm", "frozen CPU fixture")
    commit = git("rev-parse", "HEAD")
    monkeypatch.setattr(module, "ROOT", source)
    monkeypatch.setattr(module, "CURRENT_ASTRA_SHA256", digest(source / PLAN_REL), raising=False)
    cases = module.build_cases(hashes["assets/robots/franka_panda/scene.xml"])
    overlay = next(n for n in hashes if n.endswith("implementation/launch_molmo_grounded.py"))
    proof = next(n for n in hashes if n.endswith("planner-r545-import-preflight.stdout"))
    value = {
        "schema": "molmo.execution.r569.v1", "run_id": "r569-current-suite-20261112",
        "source_commit": commit, "worktree_root": str(source), "new_raw_root": str(raw_root),
        "astra_plan": {"path": str(source / PLAN_REL), "sha256": digest(source / PLAN_REL)},
        "prior_evidence": copy.deepcopy(plan["prior_evidence"]),
        "prior": {"loads": 7, "generations": 27, "paid": 4},
        "additional_max": {"loads": 3, "generations": 20, "paid": 3},
        "group_caps": {"G1": 8, "G2": 6, "G3": 6}, "retries": 0,
        "hardware_dispatch": False, "physical_formal": "NOT_RUN",
        "case_digest": hashlib.sha256(module._canonical([c.payload() for c in cases])).hexdigest(),
        "source_hashes": hashes,
        "runtime": {
            **{k: runtime[k] for k in ("native_python", "cpu_python", "model_directory",
                                      "model_store", "profile_id", "gpu_lock")},
            "overlay": {"path": str(source / overlay), "sha256": hashes[overlay]},
            "proof": {"path": str(source / proof), "sha256": hashes[proof]},
            "asset_manifest": {"path": str(asset_manifest), "sha256": digest(asset_manifest),
                               "files": 26},
            "settings_sha256": module.SETTINGS_SHA,
            "roles_sha256": hashes["configs/research/ced_roles.yaml"],
        },
    }
    path = source / "execution-plan.local.json"
    write_json(path, value)
    return module, cases, raw_root, path, value


def register(binding):
    module, cases, root, path, value = binding
    return module.preregister(root, cases, value["source_hashes"], execution_plan=path)


def test_current_registration_seals_exact_seven_true_prior_and_current_sources(
    tmp_path, monkeypatch
):
    binding = current_binding(tmp_path, monkeypatch)
    module, cases, root, path, value = binding
    registry = register(binding)
    assert registry["schema"] == "molmo.interface.r569.v1"
    assert registry["cases"] == [case.payload() for case in cases]
    assert registry["prior"] == {"loads": 7, "generations": 27, "paid": 4}
    assert registry["execution_plan"] == {"path": str(path), "sha256": digest(path)}
    assert registry["source_hashes"]["execution-plan.local.json"] == digest(path)
    module._registry_check(root, registry)
    module._check_sources(registry)
    assert value["source_commit"] != "75f5a991fe16549843177a1fa79c76cf1914e741"


def test_current_cli_registers_from_frozen_map_without_recalculating_drift(tmp_path, monkeypatch):
    module, _, root, path, _ = current_binding(tmp_path, monkeypatch)
    outside = tmp_path / "registry.json"
    assert module.main(["preregister", "--output", str(root), "--registry", str(outside),
                        "--execution-plan", str(path)]) == 0
    assert outside.read_bytes() == (root / "registry.json").read_bytes()


@pytest.mark.parametrize(
    "damage",
    ["prior", "bool_prior", "cap", "extra_cap", "bool_cap", "groups", "case_digest",
     "raw_root", "worktree", "missing_source", "escape", "source_bytes", "source_symlink",
     "astra_ref", "astra_bytes", "prior_bytes", "commit", "asset", "runtime", "duplicate"],
)
def test_bad_current_execution_cannot_create_a_run(tmp_path, monkeypatch, damage):
    binding = current_binding(tmp_path, monkeypatch)
    module, _, root, path, value = binding
    if damage in {"prior", "bool_prior"}:
        value["prior"]["loads"] = True if damage == "bool_prior" else 4
    elif damage in {"cap", "bool_cap"}:
        value["additional_max"]["paid"] = True if damage == "bool_cap" else 4
    elif damage == "extra_cap":
        value["additional_max"]["retry"] = 1
    elif damage == "groups":
        value["group_caps"]["G3"] = 7
    elif damage == "case_digest":
        value["case_digest"] = "0" * 64
    elif damage == "raw_root":
        value["new_raw_root"] = str(tmp_path / "different")
    elif damage == "worktree":
        value["worktree_root"] = str(tmp_path)
    elif damage == "missing_source":
        del value["source_hashes"]["scripts/probe_molmo_multiscene.py"]
    elif damage == "escape":
        value["source_hashes"]["../other.py"] = "0" * 64
    elif damage in {"source_bytes", "source_symlink"}:
        source = module.ROOT / "src/cloud_edge_robot_arm/vision/top_grasp.py"
        if damage == "source_bytes":
            source.write_bytes(source.read_bytes() + b"\n")
        else:
            target = tmp_path / "outside.py"
            target.write_bytes(source.read_bytes())
            source.unlink()
            source.symlink_to(target)
    elif damage == "astra_ref":
        value["astra_plan"]["sha256"] = "0" * 64
    elif damage == "astra_bytes":
        source = Path(value["astra_plan"]["path"])
        source.write_bytes(source.read_bytes() + b" ")
    elif damage == "prior_bytes":
        source = Path(value["prior_evidence"]["path"])
        source.write_bytes(source.read_bytes() + b" ")
    elif damage == "commit":
        value["source_commit"] = "0" * 40
    elif damage == "asset":
        value["runtime"]["asset_manifest"]["sha256"] = "0" * 64
    elif damage == "runtime":
        value["runtime"]["profile_id"] = "other"
    write_json(path, value)
    if damage == "duplicate":
        path.write_text(path.read_text().rstrip()[:-1] + ',"prior":{}}')
    with pytest.raises(ValueError):
        register(binding)
    assert not root.exists()


@pytest.mark.parametrize("argument", ["model_directory", "asset_manifest", "model_store",
                                      "profile_id", "gpu_lock"])
def test_worker_argument_drift_stops_before_any_provider_or_paid_call(
    tmp_path, monkeypatch, argument
):
    binding = current_binding(tmp_path, monkeypatch)
    module, _, root, _, value = binding
    register(binding)

    def forbidden(*args, **kwargs):
        raise AssertionError("unadmitted worker delegated external work")

    monkeypatch.setattr(module, "_profile", forbidden)
    monkeypatch.setattr(module, "MolmoPointProvider", forbidden)
    runtime = value["runtime"]
    kwargs = {k: Path(runtime[k]) for k in ("model_directory", "model_store", "gpu_lock")}
    kwargs.update(asset_manifest=Path(runtime["asset_manifest"]["path"]),
                  profile_id=runtime["profile_id"])
    kwargs[argument] = "other" if argument == "profile_id" else tmp_path / "other"
    with pytest.raises(ValueError):
        module.run_group("G1", registry=root / "registry.json", output=root,
                         allow_paid=True, **kwargs)
    assert not list((root / "reservations").iterdir())


def test_resealed_current_registry_cannot_lower_prior(tmp_path, monkeypatch):
    binding = current_binding(tmp_path, monkeypatch)
    module, _, root, _, _ = binding
    registry = register(binding)
    registry["prior"]["loads"] = 4
    (root / "registry.json").write_bytes(module._canonical(registry))
    write_json(root / "registry.sha256", {"sha256": digest(root / "registry.json")})
    with pytest.raises(ValueError):
        module._registry_check(root, registry)


def test_resealed_current_registry_case_asset_rejected_before_worker_admission(
    tmp_path, monkeypatch
):
    binding = current_binding(tmp_path, monkeypatch)
    module, _, root, execution_path, execution = binding
    execution_sha = digest(execution_path)
    registry = register(binding)
    registry["cases"] = [c.payload() for c in module.build_cases("0" * 64)]
    (root / "registry.json").write_bytes(module._canonical(registry))
    write_json(root / "registry.sha256", {"sha256": digest(root / "registry.json")})
    invoked = []

    def forbidden(*args, **kwargs):
        invoked.append(True)
        raise AssertionError("forged cases reached worker admission")

    monkeypatch.setattr(module, "_profile", forbidden)
    monkeypatch.setattr(module, "MolmoPointProvider", forbidden)
    monkeypatch.setattr(module.RunLedger, "claim", forbidden)
    runtime = execution["runtime"]
    arguments = {k: Path(runtime[k]) for k in ("model_directory", "model_store", "gpu_lock")}
    arguments.update(asset_manifest=Path(runtime["asset_manifest"]["path"]),
                     profile_id=runtime["profile_id"])
    message = "execution registry case matrix changed"
    with pytest.raises(ValueError, match=message):
        module._execution_for_registry(registry)
    with pytest.raises(ValueError, match=message):
        module._registry_check(root, registry)
    with pytest.raises(ValueError, match=message):
        module.run_group("G1", registry=root / "registry.json", output=root,
                         allow_paid=True, **arguments)
    assert not invoked
    assert not (root / "G1").exists()
    assert not list((root / "claims").iterdir())
    assert not list((root / "reservations").iterdir())
    assert digest(execution_path) == execution_sha


def test_legacy_schema_cannot_claim_current_prior(tmp_path):
    from tests.test_molmo_multiscene import setup_run

    module, _, root, registry, ledger = setup_run(tmp_path)
    ledger.close()
    registry["prior"] = {"loads": 7, "generations": 27, "paid": 4}
    (root / "registry.json").write_bytes(module._canonical(registry))
    write_json(root / "registry.sha256", {"sha256": digest(root / "registry.json")})
    with pytest.raises(ValueError):
        module._registry_check(root, registry)


def test_current_workers_preserve_fixed_suite_and_true_cumulative_accounting(tmp_path, monkeypatch):
    from tests.test_molmo_multiscene import recorded_suite

    binding = current_binding(tmp_path, monkeypatch)
    module, _, root, registry, state = recorded_suite(
        tmp_path, monkeypatch, groups=("G1", "G2", "G3"), execution_plan=binding[3]
    )
    assert [r["status"] for r in state.reports] == ["COMPLETED"] * 3
    summary = module.summarize(
        registry, [row for r in state.reports for row in r["results"]], root=root
    )
    assert summary["valid_suite"] and summary["passed_cases"] == 7
    # This fixture returns ABSENT on each negative's first native query.
    started = sum(p.generation_calls_started for p in state.providers)
    completed = sum(p.generation_calls_completed for p in state.providers)
    loads = sum(p.model_loads_started for p in state.providers)
    assert state.calls == started == completed == 16
    assert loads == 3
    durable = [json.loads((root / g / "group-end.json").read_text()) for g in module.GROUPS]
    assert durable == state.reports
    for report, expected in zip(durable, (6, 5, 5), strict=True):
        assert report["actual_counts"] == {
            "loads": 1, "generations_started": expected, "generations_completed": expected,
        }
        observed = report["accounting"]["observed"]
        assert observed["actual_generations"] == expected
        assert observed["actual_generations_completed"] == expected
        assert observed["native_unknown"] == 0
    for key in ("reserved", "delegated_post", "request_observed", "response_observed",
                "parsed_success"):
        assert sum(r["accounting"]["observed"]["paid"][key] for r in durable) == 3
    paid = sum(r["accounting"]["reserved"]["paid"] for r in durable)
    assert paid == 3
    assert registry["prior"]["loads"] + loads == 10
    assert registry["prior"]["generations"] + started == 43
    assert registry["prior"]["paid"] + paid == 7
    assert registry["prior"]["loads"] + registry["additional_max"]["loads"] == 10
    assert registry["prior"]["generations"] + registry["additional_max"]["generations"] == 47
    assert registry["prior"]["paid"] + registry["additional_max"]["paid"] == 7
