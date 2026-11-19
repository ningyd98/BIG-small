"""CPU-only verification of the installed Harness boundary and source bridge."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _cli(*args: str | Path, cwd: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    env.pop("OPENAI_API_KEY", None)
    return subprocess.run(
        [sys.executable, "-B", "-m", "cloud_edge_robot_arm.harness", *map(str, args)],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def _valid_config(cwd: Path) -> dict[str, Any]:
    reply = _cli("validate", cwd=cwd)
    assert reply.returncode == 0, reply.stderr
    return json.loads(reply.stdout)["configuration"]


def test_packaged_example_runs_outside_checkout_without_credentials(tmp_path: Path) -> None:
    reply = _cli("validate", cwd=tmp_path)
    assert reply.returncode == 0, reply.stderr
    data = json.loads(reply.stdout)
    assert data["status"] == "VALIDATED"
    assert data["configuration"]["scenario_id"] == "S01_NORMAL_STATIC"
    assert data["configuration"]["cloud_model"] == "gpt-6.1-sol"
    assert len(data["configuration_sha256"]) == 64

    reply = _cli("doctor", cwd=tmp_path)
    assert reply.returncode == 0, reply.stderr
    data = json.loads(reply.stdout)
    assert data["status"] == "OFFLINE_READY"
    assert data["resources"]["source_checkout"] == "REQUIRED_FOR_PREPARE_OR_SIMULATION"
    assert data["resources"]["native_model_runtime"] == "EXTERNAL_UNVERIFIED"
    assert data["hardware_dispatch"] is False
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "change",
    [
        {"seed": True},
        {"hardware_dispatch": True},
        {"local_recover_enabled": True},
        {"allow_paid": True},
        {"cloud_model": "different-model"},
        {"scene_split": "held-out"},
        {"camera_position_m": [0, 0, 12]},
        {"camera_position_m": [0, 0, True]},
        {"visual_servo": 1},
        {"visual_servo": 1.0},
    ],
)
def test_configuration_rejects_unsupported_scope_and_values(
    tmp_path: Path, change: dict[str, Any],
) -> None:
    config = _valid_config(tmp_path)
    config.update(change)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    reply = _cli("validate", "--config", path, cwd=tmp_path)
    assert reply.returncode == 2
    assert json.loads(reply.stdout)["status"] == "NOT_STARTED"


def test_configuration_rejects_duplicate_keys(tmp_path: Path) -> None:
    config = _valid_config(tmp_path)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config)[:-1] + ',"seed":42002}')
    reply = _cli("validate", "--config", path, cwd=tmp_path)
    assert reply.returncode == 2


def test_prepare_uses_registered_source_and_preserves_original_evidence(tmp_path: Path) -> None:
    output = tmp_path / "episode"
    reply = _cli("prepare", "--source-checkout", ROOT, "--output", output, cwd=tmp_path)
    assert reply.returncode == 0, reply.stderr or reply.stdout
    data = json.loads(reply.stdout)
    assert data["status"] == "PREPARED"
    assert data["source"]["root"] == str(ROOT)
    assert data["episode"]["model_calls"] == data["episode"]["executed_actions"] == 0
    assert data["episode"]["physical_success"] is None
    manifest_path = output / "evidence-manifest.json"
    original_manifest = manifest_path.read_bytes()

    reply = _cli("evidence", output, cwd=tmp_path)
    assert reply.returncode == 0, reply.stderr or reply.stdout
    data = json.loads(reply.stdout)
    assert data["status"] == "VERIFIED"
    assert data["episode"]["mode"] == "dry-run"
    assert data["manifest_sha256"] == hashlib.sha256(original_manifest).hexdigest()
    assert manifest_path.read_bytes() == original_manifest

    reply = _cli("prepare", "--source-checkout", ROOT, "--output", output, cwd=tmp_path)
    assert reply.returncode == 2
    assert manifest_path.read_bytes() == original_manifest


def test_prepare_rejects_incomplete_checkout_before_creating_output(tmp_path: Path) -> None:
    output = tmp_path / "episode"
    reply = _cli("prepare", "--source-checkout", tmp_path, "--output", output, cwd=tmp_path)
    assert reply.returncode == 2
    assert json.loads(reply.stdout)["status"] == "NOT_STARTED"
    assert not output.exists()


def test_simulation_requires_explicit_paid_opt_in_before_startup(tmp_path: Path) -> None:
    output = tmp_path / "episode"
    reply = _cli(
        "run-simulation", "--source-checkout", ROOT, "--output", output,
        "--native-python", tmp_path / "not-a-python", "--profile-id", "profile-fixture",
        "--model-control-db", tmp_path / "database", "--model-directory", tmp_path / "model",
        "--asset-manifest", tmp_path / "manifest", "--gpu-lock", tmp_path / "lock",
        cwd=tmp_path,
    )
    assert reply.returncode == 2
    assert "--allow-paid" in json.loads(reply.stdout)["error"]
    assert not output.exists()


@pytest.mark.parametrize("path", ["../outside", "/etc/passwd", "parent/link", "symlink"])
def test_evidence_rejects_outside_and_symlink_paths(tmp_path: Path, path: str) -> None:
    output = tmp_path / "episode"
    output.mkdir()
    outside = tmp_path / "outside"
    outside.write_bytes(b"evidence")
    (output / "symlink").symlink_to(outside)
    (output / "parent").symlink_to(tmp_path, target_is_directory=True)
    (tmp_path / "link").write_bytes(b"evidence")
    valid_result = b'{"schema_version":"sol-molmo.single-episode-result.v1","mode":"dry-run"}'
    (output / "result.json").write_bytes(valid_result)
    (output / "evidence-manifest.json").write_text(json.dumps({
        "schema_version": "local.files.v1",
        "files": [
            {"path": "result.json", "sha256": hashlib.sha256(valid_result).hexdigest(),
             "bytes": len(valid_result)},
            {"path": path, "sha256": hashlib.sha256(b"evidence").hexdigest(), "bytes": 8},
        ],
    }))
    reply = _cli("evidence", output, cwd=tmp_path)
    assert reply.returncode == 2
    assert json.loads(reply.stdout)["status"] == "NOT_STARTED"


def test_evidence_rejects_changed_result_even_when_size_matches(tmp_path: Path) -> None:
    output = tmp_path / "episode"
    reply = _cli("prepare", "--source-checkout", ROOT, "--output", output, cwd=tmp_path)
    assert reply.returncode == 0, reply.stderr or reply.stdout
    result = output / "result.json"
    result.write_bytes(result.read_bytes().replace(b"PREPARED", b"TAMPERED"))
    reply = _cli("evidence", output, cwd=tmp_path)
    assert reply.returncode == 2
    assert "hash" in json.loads(reply.stdout)["error"]


def test_resource_admission_is_available_as_an_installed_module() -> None:
    assert importlib.util.find_spec("cloud_edge_robot_arm.vision.model_resources") is not None


def test_prepare_distinguishes_planned_development_from_effective_fixed_scene(
    tmp_path: Path,
) -> None:
    config = _valid_config(tmp_path)
    config.update(seed=44101, scene_split="development", camera_position_m=[0.3, 0.1, 1.4])
    path = tmp_path / "planned.json"
    path.write_text(json.dumps(config))
    output = tmp_path / "episode"
    reply = _cli(
        "prepare", "--source-checkout", ROOT, "--output", output, "--config", path, cwd=tmp_path,
    )
    assert reply.returncode == 0, reply.stderr or reply.stdout
    report = json.loads(reply.stdout)
    assert report["planned_configuration"] == config
    assignment = json.loads((output / "scene-assignment.json").read_bytes())
    effective = report["effective_configuration"]
    assert effective["seed"] == assignment["seed"] == 44101
    assert effective["scene_sampling"] == assignment["scene_sampling"] == "FIXED_REGISTERED_SCENE"
    assert effective["scene_split"] is None
    assert effective["visual_servo"] is False
    assert effective["camera_position_m"] is None
    assert set(report["not_applied"]) == {"scene_split", "visual_servo", "camera_position_m"}


@pytest.mark.parametrize(
    ("child_exit", "raw_code", "signal_number", "wrapper_code"),
    [
        ("os._exit(7)", 7, None, 7),
        ("os.kill(os.getpid(), signal.SIGTERM)", -signal.SIGTERM, signal.SIGTERM, 143),
    ],
)
def test_spawned_child_with_only_stage_evidence_keeps_unknown_terminal_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    child_exit: str,
    raw_code: int,
    signal_number: int | None,
    wrapper_code: int,
) -> None:
    from cloud_edge_robot_arm.harness import cli
    from cloud_edge_robot_arm.harness.checkout import ENTRY, SourceCheckout

    entry = tmp_path / ENTRY
    entry.parent.mkdir()
    entry.write_text(
        "import os, signal, sys\n"
        "from pathlib import Path\n"
        "output = Path(sys.argv[sys.argv.index('--output') + 1])\n"
        "output.mkdir()\n"
        "(output / 'scene-assignment.json').write_text('{}')\n"
        f"{child_exit}\n",
    )
    monkeypatch.setattr(cli, "verify_checkout", lambda *_: SourceCheckout(tmp_path, None, {}))
    output = tmp_path / "episode"
    code = cli.main(["prepare", "--source-checkout", str(tmp_path), "--output", str(output)])
    report = json.loads(capsys.readouterr().out)
    assert code == report["wrapper_exit_code"] == wrapper_code
    assert report["status"] == "INCOMPLETE_UNKNOWN"
    assert report["episode_exit_code"] == raw_code
    assert report["signal"] == signal_number
    assert report["costs"] is None
    assert report["present_stage_files"] == ["scene-assignment.json"]
    assert (output / "scene-assignment.json").read_bytes() == b"{}"


def _evidence(tmp_path: Path, result: dict[str, Any]) -> Path:
    output = tmp_path / "episode"
    output.mkdir()
    raw = json.dumps(result).encode()
    (output / "result.json").write_bytes(raw)
    (output / "evidence-manifest.json").write_text(json.dumps({
        "schema_version": "local.files.v1",
        "files": [{"path": "result.json", "sha256": hashlib.sha256(raw).hexdigest(),
                   "bytes": len(raw)}],
    }))
    return output


def _replace_evidence_file(
    output: Path, name: str, raw: bytes, *, size: int | None = None,
    digest: str | None = None,
) -> None:
    (output / name).write_bytes(raw)
    manifest = output / "evidence-manifest.json"
    record = json.loads(manifest.read_bytes())
    row = next(item for item in record["files"] if item["path"] == name)
    row.update(bytes=len(raw) if size is None else size,
               sha256=hashlib.sha256(raw).hexdigest() if digest is None else digest)
    manifest.write_text(json.dumps(record))


@pytest.fixture
def prepared_evidence(tmp_path: Path) -> Path:
    from cloud_edge_robot_arm.harness.config import load_config
    from cloud_edge_robot_arm.research.sol_molmo_single_episode import run_single_episode

    config = load_config()
    output = tmp_path / "episode"
    run_single_episode(output=output, seed=config.seed, marker_family_id=config.marker_family)
    return output


def _pad_result(output: Path, size: int) -> bytes:
    result = json.loads((output / "result.json").read_bytes())
    result["recorded_diagnostics"] = ""
    overhead = len(json.dumps(result).encode())
    result["recorded_diagnostics"] = "a" * (size - overhead)
    return json.dumps(result).encode()


@pytest.mark.parametrize("size", [8 * 1024 * 1024 + 1, 16 * 1024 * 1024])
def test_evidence_accepts_large_manifest_bound_result(
    tmp_path: Path, prepared_evidence: Path, size: int,
) -> None:
    from cloud_edge_robot_arm.harness import cli
    from cloud_edge_robot_arm.harness.checkout import verify_checkout
    from cloud_edge_robot_arm.harness.config import load_config
    from cloud_edge_robot_arm.harness.evidence import EpisodeExpectation

    output = prepared_evidence
    raw = _pad_result(output, size)
    assert len(raw) == size
    _replace_evidence_file(output, "result.json", raw)
    reply = _cli("evidence", output, cwd=tmp_path)
    assert reply.returncode == 0, reply.stderr or reply.stdout
    index = json.loads(reply.stdout)
    assert index["status"] == "VERIFIED"
    assert index["episode"]["status"] == "PREPARED"
    assert index["manifest_sha256"] == hashlib.sha256(
        (output / "evidence-manifest.json").read_bytes()
    ).hexdigest()

    config = load_config()
    expected = EpisodeExpectation(verify_checkout(ROOT, config), config, False)
    code, report = cli._finish_launch(
        {}, config, output, cli._ChildExit(0, "", None), None, expected=expected,
    )
    assert code == report["wrapper_exit_code"] == 0
    assert report["status"] == "PREPARED"
    assert report["evidence"]["status"] == "VERIFIED"


@pytest.mark.parametrize(
    ("problem", "error"),
    [
        ("over_limit", "exceeds 16 MiB"),
        ("small_declaration", "exceeds 16 MiB"),
        ("wrong_size", "differs from manifest size or hash"),
        ("wrong_digest", "differs from manifest size or hash"),
        ("invalid_json", "Expecting property name"),
        ("duplicate_key", "duplicate JSON key"),
        ("nonfinite", "nonfinite JSON literal"),
    ],
)
def test_evidence_rejects_invalid_large_result(
    tmp_path: Path, prepared_evidence: Path, problem: str, error: str,
) -> None:
    output = prepared_evidence
    size_mib = 16 if problem in {"over_limit", "small_declaration"} else 8
    raw = _pad_result(output, size_mib * 1024 * 1024 + 1)
    if problem == "invalid_json":
        raw = b"{" + raw
    elif problem == "duplicate_key":
        raw = b'{"mode":"dry-run",' + raw[1:]
    elif problem == "nonfinite":
        raw = b'{"invalid":NaN,' + raw[1:]
    declared_size = {"small_declaration": 1, "wrong_size": len(raw) - 1}.get(problem)
    claimed_digest = "0" * 64 if problem == "wrong_digest" else None
    _replace_evidence_file(output, "result.json", raw, size=declared_size, digest=claimed_digest)
    reply = _cli("evidence", output, cwd=tmp_path)
    assert reply.returncode == 2
    assert error in json.loads(reply.stdout)["error"]


@pytest.mark.parametrize(
    "name", ["evidence-manifest.json", "scene-assignment.json", "source-hashes.json"],
)
def test_other_evidence_json_keeps_original_limit(
    tmp_path: Path, prepared_evidence: Path, name: str,
) -> None:
    output = prepared_evidence
    oversized = b" " * (8 * 1024 * 1024 + 1)
    if name == "evidence-manifest.json":
        (output / name).write_bytes(oversized)
    else:
        _replace_evidence_file(output, name, oversized)
    reply = _cli("evidence", output, cwd=tmp_path)
    assert reply.returncode == 2
    assert json.loads(reply.stdout)["error"] == "evidence JSON exceeds 8 MiB"


@pytest.mark.parametrize("extra", [{}, {"mode": "dry-run"}])
def test_evidence_rejects_schema_only_and_missing_status(
    tmp_path: Path, extra: dict[str, str],
) -> None:
    output = _evidence(tmp_path, {"schema_version": "sol-molmo.single-episode-result.v1", **extra})
    assert _cli("evidence", output, cwd=tmp_path).returncode == 2


def test_evidence_requires_assignment_and_source_for_complete_prepare(tmp_path: Path) -> None:
    from cloud_edge_robot_arm.research.sol_molmo_single_episode import run_single_episode

    result = run_single_episode(output=tmp_path / "reference-prepare")
    output = _evidence(tmp_path, result)
    assert _cli("evidence", output, cwd=tmp_path).returncode == 2


@pytest.mark.parametrize("failure", ["FAILED", "INTERRUPTED"])
def test_evidence_accepts_original_failed_and_interrupted_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    from cloud_edge_robot_arm.research import sol_molmo_single_episode as original

    output = tmp_path / "episode"
    monkeypatch.setattr(original, "SOURCE_PATHS", ("missing-source.py",))
    if failure == "INTERRUPTED":
        previous = original._sha

        def interrupted(path: Path) -> str:
            if path.name == "missing-source.py":
                raise KeyboardInterrupt
            return previous(path)

        monkeypatch.setattr(original, "_sha", interrupted)
        with pytest.raises(KeyboardInterrupt):
            original.run_single_episode(output=output)
    else:
        original.run_single_episode(output=output)

    reply = _cli("evidence", output, cwd=tmp_path)
    assert reply.returncode == 0, reply.stderr or reply.stdout
    report = json.loads(reply.stdout)
    assert report["status"] == "VERIFIED"
    assert report["episode"]["status"] == failure
    assert report["episode"]["source_snapshot_status"] == "INCOMPLETE"
    assert report["episode"]["physical_success"] is None
    assert report["episode"]["error_type"] in {"FileNotFoundError", "KeyboardInterrupt"}


def test_child_retains_canonical_output_lock_when_wrapper_is_killed(tmp_path: Path) -> None:
    from cloud_edge_robot_arm.harness.checkout import ENTRY

    entry = tmp_path / ENTRY
    entry.parent.mkdir()
    child_pid_path = tmp_path / "child.pid"
    release = tmp_path / "release"
    entry.write_text(
        "import os, time\n"
        "from pathlib import Path\n"
        f"Path({str(child_pid_path)!r}).write_text(str(os.getpid()))\n"
        f"while not Path({str(release)!r}).exists():\n"
        "    time.sleep(0.01)\n",
    )
    canonical_parent = tmp_path / "episodes"
    canonical_parent.mkdir()
    alias_parent = tmp_path / "alias"
    alias_parent.symlink_to(canonical_parent, target_is_directory=True)
    output = canonical_parent / "trial"
    command = [
        sys.executable, "-B", "-c",
        "import sys\nfrom pathlib import Path\n"
        "from cloud_edge_robot_arm.harness import cli\n"
        "from cloud_edge_robot_arm.harness.checkout import SourceCheckout\n"
        "root, output = sys.argv[1:]\n"
        "cli.verify_checkout = lambda *_: SourceCheckout(Path(root), None, {})\n"
        "raise SystemExit(cli.main(['prepare', '--source-checkout', root, '--output', output]))",
        str(tmp_path), str(alias_parent / output.name),
    ]
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    with subprocess.Popen(
        command, cwd=tmp_path, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ) as wrapper:
        try:
            deadline = time.monotonic() + 10
            while not child_pid_path.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            assert child_pid_path.exists()
            wrapper.kill()
            assert wrapper.wait(timeout=5) == -signal.SIGKILL
            collision = _cli("prepare", "--source-checkout", ROOT, "--output", output, cwd=tmp_path)
            assert collision.returncode == 2, collision.stderr or collision.stdout
            assert json.loads(collision.stdout)["status"] == "NOT_STARTED"
            assert not output.exists()
            lock, = canonical_parent.glob("*.lock")
            inode = lock.stat().st_ino
        finally:
            release.touch()
            if wrapper.poll() is None:
                wrapper.kill()

    deadline = time.monotonic() + 10
    while True:
        prepared = _cli("prepare", "--source-checkout", ROOT, "--output", output, cwd=tmp_path)
        if prepared.returncode == 0 or time.monotonic() >= deadline:
            break
        time.sleep(0.02)
    assert prepared.returncode == 0, prepared.stderr or prepared.stdout
    assert lock.stat().st_ino == inode


@pytest.mark.parametrize("mismatch", ["seed", "marker", "mode", "source"])
def test_launched_prepare_does_not_claim_unbound_episode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    mismatch: str,
) -> None:
    from cloud_edge_robot_arm.harness import cli
    from cloud_edge_robot_arm.harness.checkout import ENTRY, verify_checkout
    from cloud_edge_robot_arm.harness.config import load_config
    from cloud_edge_robot_arm.research.sol_molmo_single_episode import run_single_episode

    config = load_config()
    source = verify_checkout(ROOT, config)
    foreign = tmp_path / "foreign"
    run_single_episode(
        output=foreign, seed=config.seed + (mismatch == "seed"),
        marker_family_id="outboard_id7_45mm_v3" if mismatch == "marker" else config.marker_family,
    )
    if mismatch in {"source", "mode"}:
        path = foreign / ("source-hashes.json" if mismatch == "source" else "result.json")
        row = json.loads(path.read_bytes())
        if mismatch == "source":
            row["files"][ENTRY] = "a" * 64
        else:
            row.update(mode="execute", status="BLOCKED")
        raw = json.dumps(row).encode()
        path.write_bytes(raw)
        manifest = foreign / "evidence-manifest.json"
        saved = json.loads(manifest.read_bytes())
        record = next(item for item in saved["files"] if item["path"] == path.name)
        record.update(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
        manifest.write_text(json.dumps(saved))
    entry = tmp_path / ENTRY
    entry.parent.mkdir()
    entry.write_text(
        "import shutil, sys\n"
        f"shutil.copytree({str(foreign)!r}, sys.argv[sys.argv.index('--output') + 1])\n",
    )
    monkeypatch.setattr(cli, "verify_checkout", lambda *_: replace(source, root=tmp_path))
    output = tmp_path / "episode"
    code = cli.main(["prepare", "--source-checkout", str(tmp_path), "--output", str(output)])
    report = json.loads(capsys.readouterr().out)
    assert code == report["wrapper_exit_code"] == 2
    assert report["episode_exit_code"] == 0
    assert report["status"] == "INCOMPLETE_UNKNOWN"
    assert report["costs"] is None
    assert report["present_stage_files"] == []
    assert "episode" not in report and "evidence" not in report


def test_trusted_native_rejection_ignores_existing_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cloud_edge_robot_arm.harness import cli
    from cloud_edge_robot_arm.harness.config import load_config

    output = tmp_path / "outside-episode"
    output.mkdir()

    def unexpected_read(_: Path) -> None:
        pytest.fail("predelegation rejection cannot read another invocation's manifest")

    monkeypatch.setattr(cli, "verify_evidence", unexpected_read)
    child = cli._ChildExit(2, "", None)
    receipt = {"status": "REJECTED_BEFORE_EPISODE", "error_type": "RuntimeError"}
    code, report = cli._finish_launch({}, load_config(), output, child, receipt)
    assert code == 2 and report["status"] == "NOT_STARTED"


def test_file_exists_receipt_with_output_remains_unowned_and_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cloud_edge_robot_arm.harness import cli
    from cloud_edge_robot_arm.harness.config import load_config

    output = tmp_path / "ambiguous-episode"
    output.mkdir()

    def unexpected_read(_: Path) -> None:
        pytest.fail("ambiguous failure has no evidence ownership")

    monkeypatch.setattr(cli, "verify_evidence", unexpected_read)
    child = cli._ChildExit(2, '{"status":"NOT_STARTED","error_type":"FileExistsError"}', None)
    code, report = cli._finish_launch({}, load_config(), output, child, None)
    assert code == 2 and report["status"] == "INCOMPLETE_UNKNOWN"
    assert report["costs"] is None
